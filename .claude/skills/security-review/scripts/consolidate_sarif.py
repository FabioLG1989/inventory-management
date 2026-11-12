"""Merge multiple SARIF 2.1.0 files into one, deduplicate by fingerprint, apply
suppressions, and remove findings that match a baseline.

Reads all *.sarif.json files from --sarif-dir. When --baseline is provided, any
finding whose fingerprints.primaryLocation is present in the baseline is removed
(only new fingerprints remain). Suppressions encoded in-source via nosec, noqa,
nosem, or gitleaks:allow markers are preserved as SARIF suppression entries.

Emits a single merged SARIF 2.1.0 document to --out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

SUPPRESSION_COMMENTS = [
    "# nosec",
    "# noqa: S",
    "// nosem",
    "gitleaks:allow",
]


def _load_sarif_files(sarif_dir: Path) -> list[dict]:
    sarif_files = list(sarif_dir.glob("*.sarif.json")) + list(sarif_dir.glob("*.sarif"))
    results = []
    for f in sarif_files:
        try:
            data = json.loads(f.read_text())
            if data.get("version") == "2.1.0":
                results.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARN: Could not parse {f}: {exc}", file=sys.stderr)
    return results


def _extract_baseline_fingerprints(baseline_path: Path) -> set[str]:
    if not baseline_path.exists():
        print(f"WARN: Baseline file '{baseline_path}' not found; continuing without baseline diff", file=sys.stderr)
        return set()
    try:
        data = json.loads(baseline_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARN: Could not read baseline '{baseline_path}': {exc}; continuing without baseline diff", file=sys.stderr)
        return set()

    fingerprints: set[str] = set()
    for run in data.get("runs", []):
        for result in run.get("results", []):
            fp = result.get("fingerprints", {}).get("primaryLocation", "")
            if fp:
                fingerprints.add(fp)
    return fingerprints


def _is_suppressed_in_source(result: dict, repo_path: Path | None) -> bool:
    for location in result.get("locations", []):
        artifact_uri = location.get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")
        start_line = location.get("physicalLocation", {}).get("region", {}).get("startLine")
        if not (artifact_uri and start_line and repo_path):
            continue
        candidate = repo_path / artifact_uri
        if not candidate.exists():
            continue
        try:
            lines = candidate.read_text(errors="replace").splitlines()
            line_content = lines[start_line - 1] if start_line <= len(lines) else ""
            for marker in SUPPRESSION_COMMENTS:
                if marker in line_content:
                    return True
        except OSError:
            pass
    return False


def _merge_runs(sarif_docs: list[dict], baseline_fingerprints: set[str], repo_path: Path | None) -> list[dict]:
    merged_runs: list[dict] = []
    seen_fingerprints: set[str] = set()

    for doc in sarif_docs:
        for run in doc.get("runs", []):
            tool = run.get("tool", {"driver": {"name": "unknown", "version": "unknown"}})
            filtered_results = []

            for result in run.get("results", []):
                fingerprint = result.get("fingerprints", {}).get("primaryLocation", "")

                if fingerprint and fingerprint in baseline_fingerprints:
                    continue

                if fingerprint and fingerprint in seen_fingerprints:
                    continue

                if _is_suppressed_in_source(result, repo_path):
                    suppressed_result = dict(result)
                    suppressed_result["suppressions"] = result.get("suppressions", []) + [
                        {"kind": "inSource", "state": "accepted", "justification": "suppression comment in source"}
                    ]
                    filtered_results.append(suppressed_result)
                    if fingerprint:
                        seen_fingerprints.add(fingerprint)
                    continue

                filtered_results.append(result)
                if fingerprint:
                    seen_fingerprints.add(fingerprint)

            if filtered_results:
                merged_runs.append({"tool": tool, "results": filtered_results})

    return merged_runs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge SARIF 2.1.0 files, deduplicate by fingerprint, and apply baseline diff.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sarif-dir", required=True, help="Directory containing *.sarif.json files")
    parser.add_argument("--out", required=True, help="Output path for the merged SARIF file")
    parser.add_argument("--baseline", help="Path to a previous security-results.json or SARIF for baseline diff")
    parser.add_argument("--repo-path", help="Repository root for in-source suppression checks")
    args = parser.parse_args()

    sarif_dir = Path(args.sarif_dir).resolve()
    out_path = Path(args.out).resolve()
    repo_path = Path(args.repo_path).resolve() if args.repo_path else None

    if not sarif_dir.is_dir():
        print(f"ERROR: --sarif-dir '{sarif_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    baseline_fingerprints: set[str] = set()
    if args.baseline:
        baseline_fingerprints = _extract_baseline_fingerprints(Path(args.baseline).resolve())
        print(f"Baseline loaded: {len(baseline_fingerprints)} known fingerprints", file=sys.stderr)

    sarif_docs = _load_sarif_files(sarif_dir)
    if not sarif_docs:
        print("WARN: No SARIF files found in --sarif-dir; emitting empty SARIF", file=sys.stderr)

    merged_runs = _merge_runs(sarif_docs, baseline_fingerprints, repo_path)

    total_results = sum(len(run.get("results", [])) for run in merged_runs)
    print(f"Consolidated {len(sarif_docs)} SARIF files into {total_results} unique findings", file=sys.stderr)

    merged_sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": merged_runs,
    }
    out_path.write_text(json.dumps(merged_sarif, indent=2))
    print(f"Merged SARIF written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
