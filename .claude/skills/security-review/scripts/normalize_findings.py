"""Convert SARIF 2.1.0 findings into the SecurityResults JSON schema, optionally
merging in triage classifications from a triaged-findings.json file.

When invoked with --sarif only, emits an intermediate normalized-findings.json
suitable for LLM triage agent input. When invoked with both --sarif and --triaged,
merges triage classifications and produces the final security-results.json.

The SecurityResults schema adds three fields to the existing shape:
  - repository: { owner, name, path }
  - sarifPath: relative path to the SARIF file
  - scannerVersions: { [tool]: version }
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

SARIF_LEVEL_TO_SEVERITY = {
    "error": "HIGH",
    "warning": "MEDIUM",
    "note": "LOW",
    "none": "NOTE",
}

OWASP_CATEGORY_TAGS = {
    "A01": "BROKEN_ACCESS_CONTROL",
    "A02": "CRYPTOGRAPHIC_FAILURES",
    "A03": "INJECTION",
    "A04": "INSECURE_DESIGN",
    "A05": "SECURITY_MISCONFIGURATION",
    "A06": "VULNERABLE_COMPONENTS",
    "A07": "AUTHN_FAILURES",
    "A08": "INTEGRITY_FAILURES",
    "A09": "LOGGING_FAILURES",
    "A10": "SSRF",
}


def _get_repo_info(repo_path: Path) -> dict:
    owner = ""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, cwd=str(repo_path),
        )
        remote = result.stdout.strip()
        match = re.search(r"[:/]([^/]+)/[^/]+(?:\.git)?$", remote)
        if match:
            owner = match.group(1)
    except Exception:
        pass
    return {"owner": owner, "name": repo_path.name, "path": str(repo_path)}


def _extract_scanner_versions(sarif_docs: list[dict]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for doc in sarif_docs:
        for run in doc.get("runs", []):
            driver = run.get("tool", {}).get("driver", {})
            name = driver.get("name", "")
            version = driver.get("version", "unknown")
            if name:
                versions[name] = version
    return versions


def _infer_owasp_category(rule_id: str, tags: list[str]) -> str:
    for tag in tags:
        for owasp_code, category in OWASP_CATEGORY_TAGS.items():
            if owasp_code in tag.upper():
                return category
    if "secret" in rule_id.lower() or "token" in rule_id.lower() or "key" in rule_id.lower():
        return "CRYPTOGRAPHIC_FAILURES"
    if "sql" in rule_id.lower() or "inject" in rule_id.lower() or "xss" in rule_id.lower():
        return "INJECTION"
    if "auth" in rule_id.lower() or "access" in rule_id.lower():
        return "BROKEN_ACCESS_CONTROL"
    if "dep" in rule_id.lower() or "cve" in rule_id.lower() or "vuln" in rule_id.lower():
        return "VULNERABLE_COMPONENTS"
    return "SECURITY_MISCONFIGURATION"


def _sarif_to_normalized(sarif_path: Path, repo_path: Path) -> list[dict]:
    try:
        data = json.loads(sarif_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot read SARIF '{sarif_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    findings: list[dict] = []
    for run in data.get("runs", []):
        tool_name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
        rules_by_id: dict[str, dict] = {r.get("id", ""): r for r in run.get("tool", {}).get("driver", {}).get("rules", [])}

        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            rule = rules_by_id.get(rule_id, {})
            tags = rule.get("properties", {}).get("tags", []) + result.get("properties", {}).get("tags", [])
            level = result.get("level", "warning")
            severity = SARIF_LEVEL_TO_SEVERITY.get(level, "MEDIUM")
            message = result.get("message", {}).get("text", "")
            fingerprint = result.get("fingerprints", {}).get("primaryLocation", "")

            locations = result.get("locations", [])
            filepath = ""
            line_num = None
            if locations:
                phys = locations[0].get("physicalLocation", {})
                filepath = phys.get("artifactLocation", {}).get("uri", "")
                line_num = phys.get("region", {}).get("startLine")

            code_snippet = None
            if filepath and line_num:
                candidate = repo_path / filepath
                if candidate.exists():
                    try:
                        lines = candidate.read_text(errors="replace").splitlines()
                        idx = line_num - 1
                        snippet_lines = lines[max(0, idx - 1): idx + 2]
                        code_snippet = "\n".join(snippet_lines)
                    except OSError:
                        pass

            cwe_id = result.get("properties", {}).get("cwe", "")
            if not cwe_id:
                for prop_source in (rule.get("properties", {}), result.get("properties", {})):
                    for k, v in prop_source.items():
                        if "cwe" in k.lower():
                            cwe_id = str(v)
                            break

            owasp_category = _infer_owasp_category(rule_id, tags)
            is_suppressed = bool(result.get("suppressions"))

            findings.append({
                "id": f"{tool_name.upper()}-{fingerprint[:8].replace('/', '-') if fingerprint else rule_id}",
                "ruleId": rule_id,
                "cweId": cwe_id,
                "category": owasp_category,
                "severity": severity,
                "classification": "TP" if not is_suppressed else "FP",
                "issue": message[:200],
                "file": filepath,
                "line": line_num,
                "details": message,
                "codeSnippet": code_snippet,
                "sarifFingerprint": fingerprint,
                "tool": tool_name,
                "fixInstructions": None,
                "testSuggestion": None,
                "references": [rule.get("helpUri", "")],
                "suppressed": is_suppressed,
            })

    return findings


def _merge_triage(normalized: list[dict], triaged_path: Path) -> list[dict]:
    try:
        triaged = json.loads(triaged_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARN: Cannot read triaged findings '{triaged_path}': {exc}; using normalized only", file=sys.stderr)
        return normalized

    triage_by_fingerprint: dict[str, dict] = {
        t.get("sarifFingerprint", ""): t for t in triaged if t.get("sarifFingerprint")
    }

    merged = []
    for finding in normalized:
        fp = finding.get("sarifFingerprint", "")
        if fp in triage_by_fingerprint:
            triage = triage_by_fingerprint[fp]
            finding = dict(finding)
            finding["classification"] = triage.get("classification", finding.get("classification", "uncertain"))
            finding["severity"] = triage.get("severity", finding.get("severity", "MEDIUM"))
            finding["fixInstructions"] = triage.get("fixInstructions", finding.get("fixInstructions"))
            finding["testSuggestion"] = triage.get("testSuggestion", finding.get("testSuggestion"))
        merged.append(finding)
    return merged


def _severity_to_bucket(severity: str) -> str:
    if severity in ("CRITICAL", "HIGH"):
        return "blocking"
    if severity == "MEDIUM":
        return "major"
    return "minor"


def _build_security_results(
    findings: list[dict],
    repo_path: Path,
    jira_key: str,
    sarif_path: Path,
    artifacts_dir: Path,
    scanner_versions: dict[str, str],
) -> dict:
    repo_info = _get_repo_info(repo_path)

    try:
        sarif_rel = str(sarif_path.relative_to(artifacts_dir))
    except ValueError:
        sarif_rel = str(sarif_path)

    owasp_compliance: dict[str, str] = {cat: "PASS" for cat in OWASP_CATEGORY_TAGS.values()}
    buckets: dict[str, list[dict]] = {"blocking": [], "major": [], "minor": []}
    secrets_found = 0

    for f in findings:
        if f.get("classification") == "FP":
            continue
        bucket = _severity_to_bucket(f.get("severity", "MEDIUM"))
        buckets[bucket].append(f)
        cat = f.get("category", "")
        if cat in owasp_compliance and owasp_compliance[cat] != "CRITICAL":
            owasp_compliance[cat] = "CRITICAL" if bucket == "blocking" else "WARN"
        if f.get("tool", "").lower() in ("gitleaks", "trufflehog"):
            secrets_found += 1

    blocking_count = len(buckets["blocking"])
    major_count = len(buckets["major"])
    minor_count = len(buckets["minor"])
    total = blocking_count + major_count + minor_count

    overall_status = "FAIL" if blocking_count > 0 else "PASS"
    summary = f"Found {blocking_count} blocking, {major_count} major, {minor_count} minor findings."

    next_steps: dict = {
        "action": "TRIGGER_REVIEW_LOOP" if blocking_count > 0 else "PASS",
        "reason": summary,
    }
    if blocking_count > 0:
        next_steps["blockingIssueIds"] = [f.get("id", "") for f in buckets["blocking"]]

    scanner_results: dict[str, dict] = {}
    for tool, version in scanner_versions.items():
        tool_findings = [f for f in findings if f.get("tool") == tool]
        is_missing = any(f.get("ruleId") == "scanner-missing" for f in tool_findings)
        scanner_results[tool] = {
            "tool": tool,
            "version": version,
            "issuesFound": len(tool_findings),
            "scanCompleted": not is_missing,
        }

    languages_detected: list[str] = []
    stack_file = artifacts_dir / "scanner-outputs" / "stack.json"
    if not stack_file.exists():
        stack_file = artifacts_dir.parent / "scanner-outputs" / "stack.json"
    if stack_file.exists():
        try:
            languages_detected = json.loads(stack_file.read_text()).get("languages", [])
        except Exception:
            pass

    for f in findings:
        f.pop("tool", None)
        f.pop("suppressed", None)

    return {
        "jiraKey": jira_key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "languages": languages_detected,
        "overallStatus": overall_status,
        "summary": summary,
        "repository": repo_info,
        "sarifPath": sarif_rel,
        "scannerVersions": scanner_versions,
        "findings": buckets,
        "metrics": {
            "totalFindings": total,
            "blockingCount": blocking_count,
            "majorCount": major_count,
            "minorCount": minor_count,
            "secretsFound": secrets_found,
            "filesScanned": 0,
            "linesScanned": 0,
        },
        "scannerResults": scanner_results,
        "owaspCompliance": owasp_compliance,
        "recommendations": [
            "Address all blocking findings before merging.",
            "Review scanner-missing findings and install recommended tools.",
        ],
        "nextSteps": next_steps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize SARIF findings to SecurityResults JSON schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sarif", required=True, help="Path to the SARIF file (filtered or consolidated)")
    parser.add_argument("--out", required=True, help="Output path for normalized-findings.json or security-results.json")
    parser.add_argument("--triaged", help="Path to triaged-findings.json from LLM triage agent")
    parser.add_argument("--repo-path", help="Absolute path to the repository root")
    parser.add_argument("--jira-key", default="adhoc", help="Jira ticket key for artifact namespacing")
    args = parser.parse_args()

    sarif_path = Path(args.sarif).resolve()
    out_path = Path(args.out).resolve()
    repo_path = Path(args.repo_path).resolve() if args.repo_path else Path.cwd()

    if not sarif_path.exists():
        print(f"ERROR: --sarif '{sarif_path}' does not exist", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        sarif_data = json.loads(sarif_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot read SARIF '{sarif_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    sarif_docs = [sarif_data]
    scanner_versions = _extract_scanner_versions(sarif_docs)
    normalized = _sarif_to_normalized(sarif_path, repo_path)

    if args.triaged:
        normalized = _merge_triage(normalized, Path(args.triaged).resolve())
        result = _build_security_results(
            normalized,
            repo_path,
            args.jira_key,
            sarif_path,
            out_path.parent,
            scanner_versions,
        )
        out_path.write_text(json.dumps(result, indent=2))
        print(f"SecurityResults written to {out_path}", file=sys.stderr)
    else:
        out_path.write_text(json.dumps(normalized, indent=2))
        print(f"Normalized findings written to {out_path} ({len(normalized)} findings)", file=sys.stderr)


if __name__ == "__main__":
    main()
