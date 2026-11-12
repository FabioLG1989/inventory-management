"""Compute pass/fail and duration trends, plus flaky-test detection, from a
suite's execution-history file written by record_run.py.

Reads the last --last runs (default 15, matching record_run.py's default
--retain) from <history-dir>/<suite>.jsonl and splits them into a "recent
half" and a "prior half" to compare. See references/trend-metrics.md for the
exact formulas and thresholds used below, and references/history-schema.md
for the run-record shape being read.

Emits JSON to stdout by default (--format json); --format markdown for a
human-readable report suitable for a PR comment or Slack message; --format
pdf writes a self-contained PDF report to --output (required for this format
— PDF is binary and cannot go to stdout). The PDF writer has no third-party
dependency: it emits raw PDF 1.4 syntax directly, matching this framework's
stdlib-only convention for scripts, so it needs nothing installed beyond
Python itself on any of the 6000+ machines this may run on.

IMPORTANT — do not wire this script to run automatically after every
recorded run. SKILL.md requires asking the user before generating a report;
this script only computes/renders on explicit request.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import record_run

DEFAULT_REGRESSION_THRESHOLD = 0.20
DEFAULT_TREND_THRESHOLD_PP = 1.0
DEFAULT_DURATION_TREND_THRESHOLD_PCT = 10.0
DEFAULT_LAST = 15

_REQUIRED_RUN_FIELDS = ("runId", "timestamp", "totals", "durationSeconds")
_REQUIRED_TOTALS_FIELDS = ("total", "passed")
_REQUIRED_CASE_FIELDS = ("name", "status", "durationSeconds")
_NUMERIC = (int, float)
_STATUS_PRIORITY = {"skipped": 0, "passed": 1, "failed": 2, "error": 2}


def _run_record_problems(run: dict) -> list[str]:
    """Field-level problems that would otherwise crash a trend computation
    below with a raw TypeError/KeyError — not just missing fields, but the
    wrong *type* on a field every computation dereferences unconditionally
    (a `totals.total` that's a string, a `testCases` entry that isn't even
    an object). Returns them in the same dotted-path style the caller
    prints; empty means the record is safe to use as-is."""
    missing = [field for field in _REQUIRED_RUN_FIELDS if field not in run]
    if missing:
        return missing

    totals = run["totals"]
    if not isinstance(totals, dict):
        return ["totals (not an object)"]
    missing = [f"totals.{field}" for field in _REQUIRED_TOTALS_FIELDS if field not in totals]
    missing += [
        f"totals.{field} (not a number)" for field in _REQUIRED_TOTALS_FIELDS
        if field in totals and not isinstance(totals[field], _NUMERIC)
    ]
    if missing:
        return missing

    if not isinstance(run["durationSeconds"], _NUMERIC):
        return ["durationSeconds (not a number)"]

    test_cases = run.get("testCases", [])
    if not isinstance(test_cases, list):
        return ["testCases (not an array)"]
    for i, case in enumerate(test_cases):
        if not isinstance(case, dict):
            return [f"testCases[{i}] (not an object)"]
        missing = [f"testCases[{i}].{field}" for field in _REQUIRED_CASE_FIELDS if field not in case]
        if not missing and not isinstance(case["durationSeconds"], _NUMERIC):
            missing = [f"testCases[{i}].durationSeconds (not a number)"]
        if not missing and case["status"] not in _STATUS_PRIORITY:
            missing = [f"testCases[{i}].status (must be one of {sorted(_STATUS_PRIORITY)}, got {case['status']!r})"]
        if missing:
            return missing
    return []


def _parse_timestamp(value: object) -> datetime:
    """Best-effort parse of a run's `timestamp` for chronological sorting.

    An unparsable or missing value sorts first (oldest) rather than
    raising — one bad timestamp shouldn't crash the whole report, only
    leave that run's relative order to whatever line position it already
    has. Always returns a timezone-aware value so it never raises
    comparing against the (aware) timestamps `record_run.py`/`ci_sync.py`
    actually write."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _load_runs(history_path: Path, last: int) -> list[dict]:
    """Parse and validate every non-blank line of the history file as one run record.

    Fails fast with the offending file and 1-based line number on the first
    line that either isn't valid JSON or has a problem (missing or
    wrong-typed field) every trend computation below dereferences
    unconditionally, instead of letting a raw JSONDecodeError, KeyError or
    TypeError — with no file or line context — crash every future trends.py
    call for this suite until someone manually finds and fixes the bad line.

    Re-sorts by `timestamp` before returning: `ci_sync.py` can discover and
    append a CI run that finished before ones already on disk (e.g. a wider
    --limit reaching further back than a previous sync), and every trend
    below — halves-comparison, the flaky-test sequence, the previous-run
    diff — assumes file order is chronological order. Sorting here makes
    that true regardless of write order, instead of every caller of this
    file needing to maintain it.
    """
    if not history_path.exists():
        return []
    runs = []
    for line_number, line in enumerate(history_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"ERROR: malformed history record at {history_path}:{line_number}: {exc}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(run, dict):
            print(
                f"ERROR: history record at {history_path}:{line_number} is not a JSON object (got {type(run).__name__})",
                file=sys.stderr,
            )
            sys.exit(1)
        problems = _run_record_problems(run)
        if problems:
            print(
                f"ERROR: history record at {history_path}:{line_number} is missing required field(s): {', '.join(problems)}",
                file=sys.stderr,
            )
            sys.exit(1)
        runs.append(run)
    runs.sort(key=lambda r: _parse_timestamp(r["timestamp"]))
    return runs[-last:] if last > 0 else []


def _pass_rate(run: dict) -> float:
    totals = run["totals"]
    return (totals["passed"] / totals["total"] * 100) if totals["total"] else 0.0


def _split_halves(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    half = max(1, len(runs) // 2)
    recent = runs[-half:]
    prior = runs[:-half][-half:] if len(runs) > half else []
    return recent, prior


def _direction(delta: float, threshold: float, up_word: str, down_word: str) -> str:
    if delta > threshold:
        return up_word
    if delta < -threshold:
        return down_word
    return "stable"


def _pass_rate_trend(runs: list[dict], threshold_pp: float) -> dict:
    recent, prior = _split_halves(runs)
    recent_mean = statistics.fmean(_pass_rate(r) for r in recent)
    if not prior:
        return {
            "recentMeanPct": round(recent_mean, 2),
            "priorMeanPct": None,
            "deltaPp": None,
            "direction": "insufficient-data",
        }
    prior_mean = statistics.fmean(_pass_rate(r) for r in prior)
    delta = recent_mean - prior_mean
    return {
        "recentMeanPct": round(recent_mean, 2),
        "priorMeanPct": round(prior_mean, 2),
        "deltaPp": round(delta, 2),
        "direction": _direction(delta, threshold_pp, "improving", "degrading"),
    }


def _duration_trend(runs: list[dict], threshold_pct: float, regression_threshold: float) -> dict:
    recent, prior = _split_halves(runs)
    recent_mean = statistics.fmean(r["durationSeconds"] for r in recent)
    result: dict = {"recentMeanSeconds": round(recent_mean, 2)}

    if prior:
        prior_mean = statistics.fmean(r["durationSeconds"] for r in prior)
        pct_change = ((recent_mean - prior_mean) / prior_mean * 100) if prior_mean else None
        result["priorMeanSeconds"] = round(prior_mean, 2)
        result["percentChange"] = round(pct_change, 2) if pct_change is not None else None
        result["direction"] = (
            _direction(pct_change, threshold_pct, "slower", "faster") if pct_change is not None else "insufficient-data"
        )
    else:
        result["priorMeanSeconds"] = None
        result["percentChange"] = None
        result["direction"] = "insufficient-data"

    latest = runs[-1]
    previous_runs = runs[:-1]
    if previous_runs:
        baseline_mean = statistics.fmean(r["durationSeconds"] for r in previous_runs)
        result["latestVsBaselinePct"] = (
            round((latest["durationSeconds"] - baseline_mean) / baseline_mean * 100, 2) if baseline_mean else None
        )
        result["regression"] = bool(
            baseline_mean and latest["durationSeconds"] > baseline_mean * (1 + regression_threshold)
        )
    else:
        result["latestVsBaselinePct"] = None
        result["regression"] = False

    return result


def _test_key(case: dict) -> str:
    return f"{case.get('classname', '')}::{case['name']}"


def _collapse_run_statuses(run: dict) -> dict[str, str]:
    """One status per classname::name key for this run.

    `record_run.py --junit` merges multiple report files into one run
    record, and two different tests across those files can share the
    same classname+name (record_run.py warns about this at record time).
    Without collapsing, a key repeated within one run would either read
    as an extra, artificial flip between "runs" (in `_flaky_tests`, which
    walks one status per occurrence) or have all but the last occurrence
    silently dropped (in `_diff_since_previous`'s old last-write-wins
    dict build) — both misreport a same-run duplicate as if it were
    information about a different run. Collapsing to the single worst
    status (error/failed > passed > skipped) keeps one entry per key per
    run, which is what both consumers assume."""
    best: dict[str, str] = {}
    for case in run.get("testCases", []):
        key, status = _test_key(case), case["status"]
        if key not in best or _STATUS_PRIORITY[status] > _STATUS_PRIORITY[best[key]]:
            best[key] = status
    return best


def _flaky_tests(runs: list[dict]) -> list[dict]:
    history: dict[str, list[str]] = {}
    for run in runs:
        for key, status in _collapse_run_statuses(run).items():
            if status not in ("passed", "failed", "error"):
                continue
            history.setdefault(key, []).append(status)

    flaky = []
    for key, statuses in history.items():
        flips = sum(1 for a, b in zip(statuses, statuses[1:]) if (a == "passed") != (b == "passed"))
        if flips >= 1 and len(statuses) >= 2:
            flaky.append({
                "test": key,
                "flipCount": flips,
                "occurrences": len(statuses),
                "lastStatus": statuses[-1],
            })
    return sorted(flaky, key=lambda f: f["flipCount"], reverse=True)


def _diff_since_previous(runs: list[dict]) -> dict:
    if len(runs) < 2:
        return {"newlyFailing": [], "newlyFixed": []}

    previous, latest = _collapse_run_statuses(runs[-2]), _collapse_run_statuses(runs[-1])
    newly_failing = [
        key for key, status in latest.items()
        if status in ("failed", "error") and previous.get(key) not in ("failed", "error")
    ]
    newly_fixed = [
        key for key, status in latest.items()
        if status == "passed" and previous.get(key) in ("failed", "error")
    ]
    return {"newlyFailing": sorted(newly_failing), "newlyFixed": sorted(newly_fixed)}


def _top_slowest(run: dict, limit: int) -> list[dict]:
    """Top `limit` slowest test cases. `limit <= 0` means none — guarded
    explicitly rather than sliced with a bare `[:limit]`, the same
    negative-slice trap `--last`/`--retain` had (`cases[:-1]` silently
    means "all but the last", not "none")."""
    cases = sorted(run.get("testCases", []), key=lambda c: c["durationSeconds"], reverse=True)
    return [{"test": _test_key(c), "durationSeconds": c["durationSeconds"]} for c in cases[:max(limit, 0)]]


def _build_report(runs: list[dict], args: argparse.Namespace) -> dict:
    latest = runs[-1]
    return {
        "suite": args.suite,
        "runsAnalyzed": len(runs),
        "latestRun": {
            "runId": latest["runId"],
            "timestamp": latest["timestamp"],
            "totals": latest["totals"],
            "durationSeconds": latest["durationSeconds"],
            "passRatePct": round(_pass_rate(latest), 2),
        },
        "passRateTrend": _pass_rate_trend(runs, args.pass_rate_threshold_pp),
        "durationTrend": _duration_trend(runs, args.duration_threshold_pct, args.regression_threshold),
        "flakyTests": _flaky_tests(runs),
        **_diff_since_previous(runs),
        "topSlowestLatestRun": _top_slowest(latest, args.top_slowest),
    }


def _report_sections(report: dict) -> list[dict]:
    """Shared content model rendered by both _render_markdown and _render_pdf,
    so the two formats never drift out of sync with each other."""
    prt = report["passRateTrend"]
    dur = report["durationTrend"]

    sections = [
        {
            "heading": f"Test execution trends — {report['suite']}",
            "lines": [f"Runs analyzed: {report['runsAnalyzed']}"],
        },
        {
            "heading": "Latest run",
            "lines": [
                f"Pass rate: {report['latestRun']['passRatePct']}% "
                f"({report['latestRun']['totals']['passed']}/{report['latestRun']['totals']['total']})",
                f"Duration: {report['latestRun']['durationSeconds']}s",
            ],
        },
        {
            "heading": "Pass-rate trend",
            "lines": [
                f"Recent mean: {prt['recentMeanPct']}% | Prior mean: {prt['priorMeanPct']}%",
                f"Delta: {prt['deltaPp']} pp — {prt['direction']}",
            ],
        },
        {
            "heading": "Duration trend",
            "lines": [
                f"Recent mean: {dur['recentMeanSeconds']}s | Prior mean: {dur['priorMeanSeconds']}s",
                f"Change: {dur['percentChange']}% — {dur['direction']}",
                f"Regression vs. baseline: {dur['regression']}",
            ],
        },
    ]

    if report["newlyFailing"]:
        sections.append({"heading": "Newly failing since previous run", "lines": [f"- {t}" for t in report["newlyFailing"]]})
    if report["newlyFixed"]:
        sections.append({"heading": "Newly fixed since previous run", "lines": [f"- {t}" for t in report["newlyFixed"]]})
    if report["flakyTests"]:
        sections.append({
            "heading": "Flaky tests",
            "lines": [f"- {f['test']} — flipped {f['flipCount']}x over {f['occurrences']} runs" for f in report["flakyTests"]],
        })
    if report["topSlowestLatestRun"]:
        sections.append({
            "heading": "Slowest tests (latest run)",
            "lines": [f"- {t['test']} — {t['durationSeconds']}s" for t in report["topSlowestLatestRun"]],
        })

    return sections


def _render_markdown(report: dict) -> str:
    sections = _report_sections(report)
    lines = [f"# {sections[0]['heading']}", "", *sections[0]["lines"], ""]
    for section in sections[1:]:
        lines += [f"## {section['heading']}", *section["lines"], ""]
    return "\n".join(lines).rstrip() + "\n"


# --- Minimal, dependency-free PDF writer -----------------------------------
#
# Raw PDF 1.4 objects only (catalog, pages, page, font, content stream) —
# no third-party library. Text-only, single built-in font (Helvetica /
# Helvetica-Bold, WinAnsiEncoding), one or more Letter pages with simple
# top-down flow and word-wrap. Sufficient for a text report; not a general
# PDF layout engine.

_PDF_PAGE_WIDTH = 612
_PDF_PAGE_HEIGHT = 792
_PDF_MARGIN = 54
_PDF_WRAP_WIDTH = 95


def _pdf_escape(text: str) -> bytes:
    normalized = (
        text.replace("—", "-").replace("–", "-")
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
    )
    encoded = normalized.encode("cp1252", errors="replace")
    escaped = encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return escaped


class _PdfDoc:
    def __init__(self) -> None:
        self._objects: dict[int, bytes] = {}
        self._next_id = 1

    def reserve(self) -> int:
        obj_id = self._next_id
        self._next_id += 1
        return obj_id

    def put(self, obj_id: int, body: bytes) -> None:
        self._objects[obj_id] = body

    def add_stream(self, body: bytes) -> int:
        obj_id = self.reserve()
        self.put(obj_id, b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        return obj_id

    def render(self) -> bytes:
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict[int, int] = {}
        max_id = self._next_id - 1
        for obj_id in range(1, max_id + 1):
            offsets[obj_id] = len(out)
            out += b"%d 0 obj\n" % obj_id + self._objects[obj_id] + b"\nendobj\n"

        xref_offset = len(out)
        out += b"xref\n0 %d\n" % (max_id + 1)
        out += b"0000000000 65535 f \n"
        for obj_id in range(1, max_id + 1):
            out += b"%010d 00000 n \n" % offsets[obj_id]
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (max_id + 1, xref_offset)
        return bytes(out)


def _pdf_wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=_PDF_WRAP_WIDTH, break_long_words=False, break_on_hyphens=False) or [""]


def _render_pdf(report: dict) -> bytes:
    doc = _PdfDoc()
    catalog_id, pages_id = doc.reserve(), doc.reserve()
    font_regular_id, font_bold_id = doc.reserve(), doc.reserve()
    doc.put(font_regular_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    doc.put(font_bold_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    sections = _report_sections(report)
    blocks: list[tuple[str, int, str]] = []
    blocks.append(("title", 16, sections[0]["heading"]))
    for line in sections[0]["lines"]:
        for wrapped in _pdf_wrap(line):
            blocks.append(("body", 10, wrapped))
    blocks.append(("spacer", 0, ""))
    for section in sections[1:]:
        blocks.append(("heading", 12, section["heading"]))
        for line in section["lines"]:
            for wrapped in _pdf_wrap(line):
                blocks.append(("body", 10, wrapped))
        blocks.append(("spacer", 0, ""))

    leading = {"title": 22, "heading": 17, "body": 13, "spacer": 8}
    page_ids: list[int] = []
    y = 0.0
    stream_lines: list[bytes] = []

    def flush_page() -> None:
        content = b"BT\n" + b"\n".join(stream_lines) + b"\nET" if stream_lines else b""
        content_id = doc.add_stream(content)
        page_id = doc.reserve()
        doc.put(page_id, (
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
        ) % (pages_id, _PDF_PAGE_WIDTH, _PDF_PAGE_HEIGHT, font_regular_id, font_bold_id, content_id))
        page_ids.append(page_id)

    def start_page() -> float:
        nonlocal stream_lines
        stream_lines = []
        return _PDF_PAGE_HEIGHT - _PDF_MARGIN

    y = start_page()
    for kind, size, text in blocks:
        if y < _PDF_MARGIN + leading[kind]:
            flush_page()
            y = start_page()
        if kind == "spacer":
            y -= leading[kind]
            continue
        font = b"/F2" if kind in ("title", "heading") else b"/F1"
        stream_lines.append(b"%s %d Tf 1 0 0 1 %d %d Tm (%s) Tj" % (
            font, size, _PDF_MARGIN, int(y), _pdf_escape(text),
        ))
        y -= leading[kind]
    flush_page()

    doc.put(pages_id, b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % pid for pid in page_ids), len(page_ids),
    ))
    doc.put(catalog_id, b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    return doc.render()


def _write_output(path: Path, content: str | bytes, kind: str) -> None:
    """Write a rendered report to --output with a clear error instead of a
    raw traceback when the path is bad (parent directory missing, no write
    permission, etc.) — a --output typo shouldn't read as a Python crash."""
    try:
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
    except OSError as exc:
        print(f"ERROR: cannot write {kind} report to {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute pass/fail and duration trends from execution history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--suite", required=True, help="Logical suite name to analyze")
    parser.add_argument("--history-dir", default=".qa/test-history", help="Directory holding per-suite history files")
    parser.add_argument("--last", type=int, default=DEFAULT_LAST, help="Number of most recent runs to analyze (default 15)")
    parser.add_argument("--format", choices=["json", "markdown", "pdf"], default="json")
    parser.add_argument("--output", help="File path to write the report to. Required for --format pdf; optional otherwise (defaults to stdout)")
    parser.add_argument("--top-slowest", type=int, default=5, help="How many slowest tests to report")
    parser.add_argument(
        "--regression-threshold", type=float, default=DEFAULT_REGRESSION_THRESHOLD,
        help="Fractional increase over baseline mean duration that counts as a regression (default 0.20 = 20%%)",
    )
    parser.add_argument(
        "--pass-rate-threshold-pp", type=float, default=DEFAULT_TREND_THRESHOLD_PP,
        help="Percentage-point delta below which the pass-rate trend is 'stable' (default 1.0)",
    )
    parser.add_argument(
        "--duration-threshold-pct", type=float, default=DEFAULT_DURATION_TREND_THRESHOLD_PCT,
        help="Percent change below which the duration trend is 'stable' (default 10.0)",
    )
    args = parser.parse_args()

    if args.last <= 0:
        print(f"ERROR: --last must be a positive integer, got {args.last}", file=sys.stderr)
        sys.exit(1)
    if args.format == "pdf" and not args.output:
        print("ERROR: --format pdf requires --output <path.pdf> (PDF is binary, it cannot go to stdout)", file=sys.stderr)
        sys.exit(1)

    history_path = record_run._suite_history_path(Path(args.history_dir), args.suite)
    runs = _load_runs(history_path, args.last)

    if not runs:
        print(f"No execution history found for suite '{args.suite}' at {history_path}", file=sys.stderr)
        sys.exit(1)
    if len(runs) < 2:
        print(f"Only {len(runs)} run recorded for suite '{args.suite}' — trends need at least 2", file=sys.stderr)

    report = _build_report(runs, args)

    if args.format == "pdf":
        _write_output(Path(args.output), _render_pdf(report), "PDF")
        print(f"PDF report written to {args.output}", file=sys.stderr)
        return

    rendered = _render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        _write_output(Path(args.output), rendered, args.format)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
