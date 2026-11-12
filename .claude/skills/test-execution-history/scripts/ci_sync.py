"""Sync recent GitHub Actions or Azure Pipelines run history into a suite's
execution-history file, so trends.py can surface pass-rate/duration/flaky
trends for suites that only ever run in CI — the ones no local
`record_run.py` call ever recorded.

Agents can already read live CI/pipeline status ad hoc via `gh run list` /
`gh pr checks` or `az pipelines runs list`. That answers "is the last run
green" but not
"is this suite flaky over the last 15 runs" — there was no surface turning
that live status into history. This script is that surface: it writes the
same <history-dir>/<suite>.jsonl shape record_run.py writes, so every trend
in references/trend-metrics.md works for CI-synced runs exactly like it
does for locally-recorded ones.

Two fidelity levels per run, chosen automatically by whether a JUnit
artifact is found:
  - "ci-junit"  — a JUnit XML artifact was downloaded and parsed (same
    parser as record_run.py): full per-test detail, real flaky-test
    detection.
  - "ci-status" — no JUnit artifact available: one pass/fail data point per
    CI run (total=1), from the run's conclusion/result alone. Coarser, but
    still enough for pass-rate/duration trend and run-level flakiness (a
    workflow that intermittently goes red) when nothing publishes per-test
    results.

Idempotent: runs already present in the history file (matched by
`ciRunId`) are skipped, so this can be called on every CI trigger or on a
schedule without duplicating history. Keep --limit <= the history's
--retain (see references/history-schema.md) so a sync never re-inserts a
run that has already aged out of the file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import record_run

SCHEMA_VERSION = record_run.SCHEMA_VERSION

_GITHUB_PASSED = {"success"}
_GITHUB_FAILED = {"failure", "timed_out"}
_AZURE_PASSED = {"succeeded"}
_AZURE_FAILED = {"failed", "partiallySucceeded"}


def _run_cli(args: list[str], tool: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        print(f"ERROR: '{tool}' CLI not found on PATH — install/authenticate it first", file=sys.stderr)
        sys.exit(1)
    except subprocess.SubprocessError as exc:
        print(f"ERROR: '{' '.join(args)}' failed to run: {exc}", file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"ERROR: '{' '.join(args)}' exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _existing_ci_run_ids(history_path: Path) -> set[str]:
    """Dedup key set from the history file's `ciRunId` fields.

    Skips (with a warning) any line that fails to parse, rather than
    crashing: this feeds a "should I sync this run again" check that must
    keep working on every CI trigger — one corrupted historical line must
    not permanently block all future syncs for the suite the way it would
    trends.py's report, where failing loud is the right call instead.
    """
    if not history_path.exists():
        return set()
    ids = set()
    for line_number, line in enumerate(history_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"WARNING: skipping malformed history record at {history_path}:{line_number}: {exc}", file=sys.stderr)
            continue
        ci_run_id = record.get("ciRunId")
        if ci_run_id is not None:
            ids.add(str(ci_run_id))
    return ids


def _fetch_github_runs(workflow: str, repo: str | None, branch: str | None, limit: int) -> list[dict]:
    args = [
        "gh", "run", "list",
        "--workflow", workflow,
        "--limit", str(limit),
        "--json", "databaseId,conclusion,status,createdAt,updatedAt,headSha,headBranch,displayTitle,url",
    ]
    if repo:
        args += ["--repo", repo]
    if branch:
        args += ["--branch", branch]
    runs = json.loads(_run_cli(args, "gh"))
    return [run for run in runs if run.get("status") == "completed"]


def _github_totals(conclusion: str) -> dict | None:
    if conclusion in _GITHUB_PASSED:
        return {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0}
    if conclusion in _GITHUB_FAILED:
        return {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0}
    return None


def _download_and_parse_junit(build_args: Callable[[str], list[str]]) -> tuple[dict, list[dict]] | None:
    """Download and merge whatever JUnit XML the artifact contains.

    A file that fails to parse is skipped with a warning rather than
    raised: this runs against artifacts published by past CI runs the
    caller doesn't control, and one malformed file must not crash the
    whole sync — the caller (`_github_record`/`_azure_record`) already
    falls back to coarse `ci-status` totals for `None`, exactly the
    fallback this takes when every file in the artifact is unparseable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(build_args(tmpdir), capture_output=True, text=True, timeout=120, check=True)
        except (OSError, subprocess.SubprocessError):
            return None
        xml_paths = sorted(Path(tmpdir).rglob("*.xml"))
        if not xml_paths:
            return None
        totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        duration_seconds = 0.0
        test_cases: list[dict] = []
        parsed_any = False
        for path in xml_paths:
            try:
                summary, cases = record_run._parse_junit_file(path)
            except ET.ParseError as exc:
                print(f"WARNING: skipping malformed JUnit artifact '{path.name}': {exc}", file=sys.stderr)
                continue
            parsed_any = True
            totals = record_run._merge_totals(totals, summary["totals"])
            duration_seconds += summary["durationSeconds"]
            test_cases.extend(cases)
        if not parsed_any:
            return None
        return {"totals": totals, "durationSeconds": duration_seconds}, test_cases


def _download_github_junit(run_id: str, pattern: str, repo: str | None) -> tuple[dict, list[dict]] | None:
    def build_args(tmpdir: str) -> list[str]:
        args = ["gh", "run", "download", run_id, "-p", pattern, "-D", tmpdir]
        if repo:
            args += ["-R", repo]
        return args

    return _download_and_parse_junit(build_args)


def _github_record(run: dict, suite: str, junit_pattern: str | None, repo: str | None) -> dict | None:
    run_id = str(run["databaseId"])
    duration = (_parse_iso(run["updatedAt"]) - _parse_iso(run["createdAt"])).total_seconds()
    base = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": uuid.uuid4().hex[:12],
        "suite": suite,
        "timestamp": _parse_iso(run["updatedAt"]).astimezone(timezone.utc).isoformat(),
        "commit": run.get("headSha"),
        "branch": run.get("headBranch"),
        "ci": True,
        "label": run.get("displayTitle"),
        "provider": "github",
        "ciRunId": run_id,
        "ciRunUrl": run.get("url"),
    }

    if junit_pattern:
        parsed = _download_github_junit(run_id, junit_pattern, repo)
        if parsed:
            summary, test_cases = parsed
            return {
                **base, "source": "ci-junit",
                "totals": summary["totals"],
                "durationSeconds": round(summary["durationSeconds"], 3),
                "testCases": test_cases,
            }

    totals = _github_totals(run.get("conclusion", ""))
    if totals is None:
        return None
    return {**base, "source": "ci-status", "totals": totals, "durationSeconds": round(duration, 3), "testCases": []}


def _fetch_azure_runs(pipeline_id: str, branch: str | None, limit: int, organization: str | None, project: str | None) -> list[dict]:
    args = [
        "az", "pipelines", "runs", "list",
        "--pipeline-ids", pipeline_id,
        "--top", str(limit),
        "--query", "[].{id:id, result:result, status:status, startTime:startTime, finishTime:finishTime, sourceBranch:sourceBranch, sourceVersion:sourceVersion}",
        "-o", "json",
    ]
    if organization:
        args += ["--organization", organization]
    if project:
        args += ["--project", project]
    if branch:
        args += ["--branch", branch]
    runs = json.loads(_run_cli(args, "az"))
    return [run for run in runs if run.get("status") == "completed"]


def _azure_totals(result: str) -> dict | None:
    if result in _AZURE_PASSED:
        return {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0}
    if result in _AZURE_FAILED:
        return {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0}
    return None


def _download_azure_junit(run_id: str, artifact_name: str, organization: str | None, project: str | None) -> tuple[dict, list[dict]] | None:
    def build_args(tmpdir: str) -> list[str]:
        args = [
            "az", "pipelines", "runs", "artifact", "download",
            "--run-id", run_id, "--artifact-name", artifact_name, "--path", tmpdir,
        ]
        if organization:
            args += ["--organization", organization]
        if project:
            args += ["--project", project]
        return args

    return _download_and_parse_junit(build_args)


def _strip_ref_prefix(ref: str | None) -> str | None:
    if not ref:
        return None
    prefix = "refs/heads/"
    return ref[len(prefix):] if ref.startswith(prefix) else ref


def _azure_record(run: dict, suite: str, junit_artifact_name: str | None, organization: str | None, project: str | None) -> dict | None:
    run_id = str(run["id"])
    start, finish = _parse_iso(run["startTime"]), _parse_iso(run["finishTime"])
    base = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": uuid.uuid4().hex[:12],
        "suite": suite,
        "timestamp": finish.astimezone(timezone.utc).isoformat(),
        "commit": run.get("sourceVersion"),
        "branch": _strip_ref_prefix(run.get("sourceBranch")),
        "ci": True,
        "label": f"azure-run-{run_id}",
        "provider": "azure",
        "ciRunId": run_id,
        "ciRunUrl": None,
    }

    if junit_artifact_name:
        parsed = _download_azure_junit(run_id, junit_artifact_name, organization, project)
        if parsed:
            summary, test_cases = parsed
            return {
                **base, "source": "ci-junit",
                "totals": summary["totals"],
                "durationSeconds": round(summary["durationSeconds"], 3),
                "testCases": test_cases,
            }

    totals = _azure_totals(run.get("result", ""))
    if totals is None:
        return None
    return {**base, "source": "ci-status", "totals": totals, "durationSeconds": round((finish - start).total_seconds(), 3), "testCases": []}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync GitHub Actions / Azure Pipelines run history into a suite's execution-history file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--provider", required=True, choices=["github", "azure"])
    parser.add_argument("--suite", required=True, help="Logical suite name, e.g. unit, e2e, backend-api")
    parser.add_argument("--limit", type=int, default=15, help="How many recent completed CI runs to consider (default 15)")
    parser.add_argument("--branch", help="Filter to one branch (recommended — trends assume one branch's history)")
    parser.add_argument("--history-dir", default=".qa/test-history", help="Directory holding per-suite history files")
    parser.add_argument("--retain", type=int, default=15, help="Max runs kept per suite (oldest pruned, default 15)")

    parser.add_argument("--workflow", help="[github] Workflow name or filename")
    parser.add_argument("--repo", help="[github] owner/repo (default: gh's current repo)")
    parser.add_argument("--junit-artifact-pattern", help="[github] Artifact name/pattern with JUnit XML (gh run download -p) — enables per-test ci-junit records")

    parser.add_argument("--pipeline-id", help="[azure] Pipeline id")
    parser.add_argument("--organization", help="[azure] Org URL (default: az devops configured default)")
    parser.add_argument("--project", help="[azure] Project (default: az devops configured default)")
    parser.add_argument("--junit-artifact-name", help="[azure] Published pipeline artifact name with JUnit XML — enables per-test ci-junit records")
    args = parser.parse_args()

    if args.provider == "github" and not args.workflow:
        print("ERROR: --provider github requires --workflow", file=sys.stderr)
        sys.exit(1)
    if args.provider == "azure" and not args.pipeline_id:
        print("ERROR: --provider azure requires --pipeline-id", file=sys.stderr)
        sys.exit(1)
    if args.retain <= 0:
        print(f"ERROR: --retain must be a positive integer, got {args.retain}", file=sys.stderr)
        sys.exit(1)

    history_dir = Path(args.history_dir)
    record_run._ensure_history_dir(history_dir)
    history_path = record_run._suite_history_path(history_dir, args.suite)
    already_recorded = _existing_ci_run_ids(history_path)

    if args.provider == "github":
        runs = _fetch_github_runs(args.workflow, args.repo, args.branch, args.limit)
        runs.sort(key=lambda r: r["updatedAt"])
        new_records = [
            _github_record(run, args.suite, args.junit_artifact_pattern, args.repo)
            for run in runs if str(run["databaseId"]) not in already_recorded
        ]
    else:
        runs = _fetch_azure_runs(args.pipeline_id, args.branch, args.limit, args.organization, args.project)
        runs.sort(key=lambda r: r["finishTime"])
        new_records = [
            _azure_record(run, args.suite, args.junit_artifact_name, args.organization, args.project)
            for run in runs if str(run["id"]) not in already_recorded
        ]

    records_to_write = [record for record in new_records if record is not None]
    written = len(records_to_write)
    dropped = record_run._append_records(history_path, records_to_write, args.retain) if written else 0
    print(f"Synced {written} new {args.provider} run(s) into suite '{args.suite}' -> {history_path}", file=sys.stderr)
    if dropped:
        print(f"Pruned {dropped} run(s) beyond --retain={args.retain}", file=sys.stderr)


if __name__ == "__main__":
    main()
