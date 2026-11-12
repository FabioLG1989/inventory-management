"""Append one normalized test-run record to a suite's execution-history file.

Reads one or more JUnit XML reports (the common denominator most test runners
can emit — Jest via jest-junit, pytest via --junitxml, PHPUnit via --log-junit,
Go via gotestsum --junitfile, .NET via the JunitXml.TestLogger logger, Maven
Surefire natively, Playwright/Mocha/RSpec via their junit reporters) and merges
them into one run record. When no runner in the stack can emit JUnit XML, the
--total/--passed/--failed/--skipped/--duration-seconds flags record a generic
summary instead.

Each run is appended as one line of JSON to <history-dir>/<suite>.jsonl and the
file is pruned to the last --retain runs (default 15 — enough for trends.py's
default --last window without letting the file grow unbounded). See
references/history-schema.md for the record shape and references/trend-metrics.md
for how trends.py consumes it.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import json
import math
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

SCHEMA_VERSION = "1"
STATUSES = ("passed", "failed", "skipped", "error")


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, cwd=str(cwd),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _testcase_status(node: ET.Element) -> str:
    if node.find("failure") is not None or node.find("error") is not None:
        return "failed" if node.find("failure") is not None else "error"
    if node.find("skipped") is not None:
        return "skipped"
    return "passed"


def _parse_duration(value: str | None) -> float | None:
    """Parse a JUnit `time` attribute value.

    None when absent or empty. Also None — with a warning, not a crash —
    when present but not a valid, finite, non-negative number: some
    runner across the many this skill targets occasionally emits a
    malformed `time` (e.g. a literal "NaN"), and one wonky duration field
    must not lose an entire test run's pass/fail data over it. float()
    itself accepts "NaN"/"Infinity"/"-Infinity" without raising — those
    are checked explicitly, since a non-finite value written to the
    history file produces a `NaN`/`Infinity` token that isn't valid JSON
    per RFC 8259 (only readable back because Python's own json module is
    lenient about it) and silently breaks trend math downstream (NaN
    fails every threshold comparison, so a stalled/hung-looking duration
    reads as "stable" instead of flagging the anomaly it is). Callers
    supply their own fallback for None.
    """
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        print(f"WARNING: non-numeric JUnit time attribute {value!r}, treating as unavailable", file=sys.stderr)
        return None
    if not math.isfinite(parsed) or parsed < 0:
        print(f"WARNING: invalid JUnit time attribute {value!r} (must be finite and non-negative), treating as unavailable", file=sys.stderr)
        return None
    return parsed


def _parse_junit_file(path: Path) -> tuple[dict, list[dict]]:
    tree = ET.parse(path)
    root = tree.getroot()
    suites = list(root.iter("testsuite"))

    totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    duration_seconds = 0.0
    test_cases: list[dict] = []

    for suite in suites:
        suite_case_duration = 0.0
        for case in suite.findall("testcase"):
            status = _testcase_status(case)
            case_duration = _parse_duration(case.attrib.get("time")) or 0.0
            suite_case_duration += case_duration
            totals["total"] += 1
            totals["errors" if status == "error" else status] += 1
            test_cases.append({
                "name": case.attrib.get("name", "unknown"),
                "classname": case.attrib.get("classname", ""),
                "status": status,
                "durationSeconds": case_duration,
            })

        parsed_suite_time = _parse_duration(suite.attrib.get("time"))
        duration_seconds += parsed_suite_time if parsed_suite_time is not None else suite_case_duration

    return {"totals": totals, "durationSeconds": duration_seconds}, test_cases


def _resolve_junit_paths(patterns: list[str]) -> list[Path]:
    """Expand every --junit pattern/path to files, de-duplicated by resolved
    path so overlapping patterns (a glob and a literal path it already
    matches, or the same file passed twice) can't silently double-count
    that file's tests into the merged totals."""
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        matches = sorted(glob.glob(pattern, recursive=True))
        if not matches and Path(pattern).exists():
            matches = [pattern]
        for match in matches:
            resolved = Path(match).resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(Path(match))
    return paths


def _merge_totals(a: dict, b: dict) -> dict:
    return {key: a.get(key, 0) + b.get(key, 0) for key in ("total", "passed", "failed", "skipped", "errors")}


def _duplicate_test_keys(test_cases: list[dict]) -> list[str]:
    """classname::name keys that appear more than once in one merged run.

    Expected when the same file matches twice (already deduped upstream by
    `_resolve_junit_paths`) or, legitimately, when two different --junit
    files each contain a test with the same classname+name — common with
    JS runners that leave `classname` blank or set it to a repeated
    `describe` title. trends.py collapses such duplicates to one status
    per run rather than misreading them as separate runs of the same
    test; this just tells the caller it happened."""
    seen: set[str] = set()
    dupes: set[str] = set()
    for case in test_cases:
        key = f"{case.get('classname', '')}::{case['name']}"
        (dupes if key in seen else seen).add(key)
    return sorted(dupes)


def _build_record(args: argparse.Namespace, repo_root: Path) -> dict:
    if args.junit:
        if any(
            getattr(args, name) is not None
            for name in ("total", "passed", "failed", "skipped", "duration_seconds")
        ):
            print(
                "WARNING: --junit given; ignoring --total/--passed/--failed/--skipped/--duration-seconds",
                file=sys.stderr,
            )

        junit_paths = _resolve_junit_paths(args.junit)
        if not junit_paths:
            print(f"ERROR: no files matched --junit pattern(s): {args.junit}", file=sys.stderr)
            sys.exit(1)

        totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        duration_seconds = 0.0
        test_cases: list[dict] = []
        for path in junit_paths:
            try:
                summary, cases = _parse_junit_file(path)
            except ET.ParseError as exc:
                print(f"ERROR: cannot parse JUnit XML '{path}': {exc}", file=sys.stderr)
                sys.exit(1)
            totals = _merge_totals(totals, summary["totals"])
            duration_seconds += summary["durationSeconds"]
            test_cases.extend(cases)
        source = "junit-xml"

        duplicates = _duplicate_test_keys(test_cases)
        if duplicates:
            print(
                f"WARNING: {len(duplicates)} test(s) share a classname::name across the merged "
                f"--junit files, e.g. {duplicates[:3]} — trends.py treats each as one test per run",
                file=sys.stderr,
            )
    else:
        required = ("total", "passed", "failed")
        missing = [f"--{name}" for name in required if getattr(args, name) is None]
        if missing:
            print(f"ERROR: --junit not given; generic mode requires {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
        if args.duration_seconds is not None and (not math.isfinite(args.duration_seconds) or args.duration_seconds < 0):
            print(f"ERROR: --duration-seconds must be a finite, non-negative number, got {args.duration_seconds}", file=sys.stderr)
            sys.exit(1)
        counts = {"total": args.total, "passed": args.passed, "failed": args.failed, "skipped": args.skipped or 0}
        negative = [f"--{name}" for name, value in counts.items() if value < 0]
        if negative:
            print(f"ERROR: {', '.join(negative)} must be non-negative", file=sys.stderr)
            sys.exit(1)
        accounted = counts["passed"] + counts["failed"] + counts["skipped"]
        if accounted > counts["total"]:
            print(
                f"ERROR: --passed + --failed + --skipped ({accounted}) exceeds --total ({counts['total']})",
                file=sys.stderr,
            )
            sys.exit(1)
        totals = {**counts, "errors": 0}
        duration_seconds = args.duration_seconds or 0.0
        test_cases = []
        source = "generic"

    branch = args.branch or _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    commit = args.commit or _git(["rev-parse", "HEAD"], repo_root)

    record = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": uuid.uuid4().hex[:12],
        "suite": args.suite,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "branch": branch,
        "ci": bool(args.ci),
        "label": args.label,
        "source": source,
        "totals": totals,
        "durationSeconds": round(duration_seconds, 3),
        "testCases": test_cases,
        "scope": args.scope,
    }
    if args.scope == "impacted":
        record["impactedFiles"] = args.impacted_files or []
        record["baseRef"] = args.base_ref
    return record


def _suite_history_path(history_dir: Path, suite: str) -> Path:
    """Resolve <history-dir>/<suite>.jsonl, rejecting a --suite value that
    would escape history_dir (a path separator, a '..' segment, an
    absolute path) or is empty. --suite is documented as a bare logical
    name (unit, e2e, backend-api), never a path — without this check it
    silently is one, and a suite name from an untrusted or templated
    source (CI workflow config, for instance) can read or write anywhere
    the process has access to."""
    if not suite:
        print("ERROR: --suite must not be empty", file=sys.stderr)
        sys.exit(1)
    candidate = history_dir / f"{suite}.jsonl"
    if candidate.resolve().parent != history_dir.resolve():
        print(f"ERROR: --suite {suite!r} is not a valid suite name (must not contain path separators)", file=sys.stderr)
        sys.exit(1)
    return candidate


@contextlib.contextmanager
def _history_lock(history_path: Path):
    """Exclusive, blocking, cross-process lock guarding one suite's history file.

    Wrap every append-then-prune sequence in this (record_run.py's own and
    ci_sync.py's, which reuses it) so two writers — e.g. parallel CI jobs
    recording the same suite at once — can't interleave: without it, one
    process can read the file for pruning right as another finishes
    appending to it, then overwrite the file with its own outdated copy,
    silently dropping the other process's just-recorded run. Locks a
    sibling `<file>.lock` file rather than the history file itself, so it
    never blocks a concurrent reader (trends.py, ci_sync.py's dedup scan).

    POSIX only (fcntl.flock) — on platforms without it (Windows) this is a
    no-op and that race still applies; see references/history-schema.md.
    """
    if fcntl is None:
        yield
        return
    lock_path = history_path.with_name(history_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _prune(history_path: Path, retain: int) -> int:
    """Keep only the newest `retain` lines. Both CLI entry points reject
    `--retain <= 0` before ever calling this, but guard it here too —
    `lines[-retain:]` with `retain == 0` is `lines[0:]` (everything, since
    `-0 == 0`), which would otherwise silently disable pruning instead of
    erroring for any future caller that skips the CLI-level check."""
    if retain <= 0:
        return 0
    lines = [line for line in history_path.read_text().splitlines() if line.strip()]
    if len(lines) <= retain:
        return 0
    kept = lines[-retain:]
    dropped = len(lines) - len(kept)
    history_path.write_text("\n".join(kept) + "\n" if kept else "")
    return dropped


def _ensure_history_dir(history_dir: Path) -> None:
    """Create history_dir if needed, failing clean instead of with a raw
    traceback when the path already exists as something other than a
    directory (a stray file left there, a --history-dir typo, etc.)."""
    try:
        history_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"ERROR: cannot create history directory {history_dir}: {exc}", file=sys.stderr)
        sys.exit(1)


def _append_records(history_path: Path, records: list[dict], retain: int) -> int:
    """Append records under the cross-process lock, then prune — failing
    clean instead of with a raw traceback for any I/O error along the way
    (permission denied on the file or the lock, a full disk, etc.), the
    same guarantee `_ensure_history_dir` gives directory creation. Returns
    the number of runs pruned. Shared by record_run.py's own single-record
    write and ci_sync.py's multi-record one, so both fail the same way."""
    try:
        with _history_lock(history_path):
            with history_path.open("a") as fh:
                for record in records:
                    fh.write(json.dumps(record) + "\n")
            return _prune(history_path, retain)
    except OSError as exc:
        print(f"ERROR: cannot write history file {history_path}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record one test run into the suite's execution-history file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--suite", required=True, help="Logical suite name, e.g. unit, e2e, backend-api")
    parser.add_argument("--junit", nargs="+", help="One or more JUnit XML paths or glob patterns")
    parser.add_argument("--total", type=int, help="Generic mode: total test count")
    parser.add_argument("--passed", type=int, help="Generic mode: passed count")
    parser.add_argument("--failed", type=int, help="Generic mode: failed count")
    parser.add_argument("--skipped", type=int, help="Generic mode: skipped count")
    parser.add_argument("--duration-seconds", type=float, help="Generic mode: total run duration in seconds")
    parser.add_argument("--history-dir", default=".qa/test-history", help="Directory holding per-suite history files")
    parser.add_argument("--retain", type=int, default=15, help="Max runs kept per suite (oldest pruned, default 15)")
    parser.add_argument("--commit", help="Override auto-detected git commit SHA")
    parser.add_argument("--branch", help="Override auto-detected git branch")
    parser.add_argument("--label", help="Free-text label, e.g. CI job id or environment")
    parser.add_argument("--ci", action="store_true", help="Mark this run as CI-sourced")
    parser.add_argument("--repo-root", help="Repository root used for git auto-detection (default: cwd)")
    parser.add_argument(
        "--scope", choices=["full", "impacted"], default="full",
        help="Whether this run covered the whole suite or only files impact_analysis.py selected (default: full)",
    )
    parser.add_argument(
        "--impacted-files", nargs="+",
        help="Test file(s) actually run — only meaningful with --scope impacted (from impact_analysis.py's impactedTestFiles)",
    )
    parser.add_argument("--base-ref", help="Git ref impact_analysis.py diffed against — only meaningful with --scope impacted")
    args = parser.parse_args()

    if args.retain <= 0:
        print(f"ERROR: --retain must be a positive integer, got {args.retain}", file=sys.stderr)
        sys.exit(1)

    if args.scope != "impacted" and (args.impacted_files or args.base_ref):
        print("ERROR: --impacted-files/--base-ref only apply with --scope impacted", file=sys.stderr)
        sys.exit(1)
    if args.scope == "impacted" and not args.impacted_files:
        print("ERROR: --scope impacted requires --impacted-files (otherwise the record can't be told apart from a run that executed nothing)", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
    record = _build_record(args, repo_root)

    history_dir = Path(args.history_dir)
    _ensure_history_dir(history_dir)
    history_path = _suite_history_path(history_dir, args.suite)
    dropped = _append_records(history_path, [record], args.retain)

    totals = record["totals"]
    pass_rate = (totals["passed"] / totals["total"] * 100) if totals["total"] else 0.0
    print(
        f"Recorded run {record['runId']} for suite '{args.suite}': "
        f"{totals['passed']}/{totals['total']} passed ({pass_rate:.1f}%), "
        f"{record['durationSeconds']:.1f}s -> {history_path}",
        file=sys.stderr,
    )
    if dropped:
        print(f"Pruned {dropped} run(s) beyond --retain={args.retain}", file=sys.stderr)


if __name__ == "__main__":
    main()
