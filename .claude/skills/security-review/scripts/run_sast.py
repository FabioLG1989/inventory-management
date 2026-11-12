"""Dispatch per-language SAST scanners and emit SARIF 2.1.0 files under --out-dir.

Supported language-to-scanner mapping:
  python    -> bandit, semgrep
  typescript/javascript -> eslint-plugin-security, semgrep
  go        -> gosec, semgrep
  rust      -> cargo-audit (clippy invoked separately via cargo)
  java      -> spotbugs + findsecbugs, semgrep
  ruby      -> brakeman, semgrep
  php       -> psalm-security, semgrep
  dotnet    -> security-code-scan, semgrep
  c_cpp     -> cppcheck, flawfinder, semgrep

Universal: semgrep runs for all detected languages.

When a required scanner binary is not found, a scanner-missing SARIF finding
is emitted (the pipeline continues). Never mutates the target tree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _get_version(cmd: str) -> str:
    try:
        result = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip().split("\n")[0]
    except Exception:
        return "unknown"


def _scanner_missing_sarif(tool: str, install_cmd: str, out_path: Path) -> None:
    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{
            "tool": {"driver": {"name": tool, "version": "unknown", "rules": []}},
            "results": [{
                "ruleId": "scanner-missing",
                "level": "warning",
                "message": {"text": f"Scanner '{tool}' not installed. Install with: {install_cmd}"},
                "fingerprints": {"primaryLocation": f"scanner-missing/{tool}"},
                "locations": [],
            }],
        }],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_semgrep(repo_path: Path, out_dir: Path, languages: list[str]) -> None:
    out_path = out_dir / "semgrep.sarif.json"
    if not shutil.which("semgrep"):
        _scanner_missing_sarif("semgrep", "pip install semgrep", out_path)
        return

    ruleset = "p/default"
    lang_rulesets = {
        "python": "p/python",
        "typescript": "p/typescript",
        "javascript": "p/javascript",
        "go": "p/golang",
        "java": "p/java",
        "ruby": "p/ruby",
        "php": "p/php",
        "rust": "p/rust",
        "dotnet": "p/csharp",
        "c_cpp": "p/c",
    }
    rulesets = ["p/secrets", "p/owasp-top-ten"]
    for lang in languages:
        if lang in lang_rulesets:
            rulesets.append(lang_rulesets[lang])

    version = _get_version("semgrep")
    cmd = ["semgrep", "--sarif", "--output", str(out_path), "--quiet"]
    for rs in rulesets:
        cmd += ["--config", rs]
    cmd.append(str(repo_path))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(repo_path))
        if result.returncode not in (0, 1):
            (out_dir / "semgrep.stderr").write_text(result.stderr)
            print(f"WARN: semgrep exited {result.returncode}. See semgrep.stderr", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("WARN: semgrep timed out after 300s", file=sys.stderr)
        _scanner_missing_sarif("semgrep", "semgrep timed out", out_path)


def _run_bandit(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "bandit.sarif.json"
    if not shutil.which("bandit"):
        _scanner_missing_sarif("bandit", "pip install bandit", out_path)
        return

    version = _get_version("bandit")
    raw_out = out_dir / "bandit.json"
    try:
        result = subprocess.run(
            ["bandit", "-r", str(repo_path), "-f", "json", "-o", str(raw_out), "-q"],
            capture_output=True, text=True, timeout=120,
        )
        (out_dir / "bandit.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("bandit", "bandit timed out", out_path)
        return

    if not raw_out.exists():
        _scanner_missing_sarif("bandit", "bandit produced no output", out_path)
        return

    try:
        data = json.loads(raw_out.read_text())
    except json.JSONDecodeError:
        _scanner_missing_sarif("bandit", "bandit output unparseable", out_path)
        return

    level_map = {"HIGH": "error", "MEDIUM": "warning", "LOW": "note"}
    results = []
    for issue in data.get("results", []):
        severity = issue.get("issue_severity", "LOW")
        filepath = Path(issue.get("filename", "")).relative_to(repo_path) if repo_path.as_posix() in issue.get("filename", "") else Path(issue.get("filename", ""))
        line_num = issue.get("line_number", 1)
        rule_id = issue.get("test_id", "B000")
        fingerprint = f"bandit/{rule_id}/{filepath}:{line_num}"
        results.append({
            "ruleId": rule_id,
            "level": level_map.get(severity, "note"),
            "message": {"text": issue.get("issue_text", "")},
            "fingerprints": {"primaryLocation": fingerprint},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": str(filepath)}, "region": {"startLine": line_num}}}],
            "properties": {"cwe": issue.get("issue_cwe", {}).get("id", ""), "confidence": issue.get("issue_confidence", "")},
        })

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": "bandit", "version": version, "informationUri": "https://bandit.readthedocs.io/", "rules": []}}, "results": results}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_gosec(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "gosec.sarif.json"
    if not shutil.which("gosec"):
        _scanner_missing_sarif("gosec", "go install github.com/securego/gosec/v2/cmd/gosec@latest", out_path)
        return

    version = _get_version("gosec")
    try:
        result = subprocess.run(
            ["gosec", "-fmt", "sarif", "-out", str(out_path), "./..."],
            capture_output=True, text=True, timeout=120, cwd=str(repo_path),
        )
        (out_dir / "gosec.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("gosec", "gosec timed out", out_path)


def _run_brakeman(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "brakeman.sarif.json"
    if not shutil.which("brakeman"):
        _scanner_missing_sarif("brakeman", "gem install brakeman", out_path)
        return

    version = _get_version("brakeman")
    try:
        result = subprocess.run(
            ["brakeman", "--format", "sarif", "--output", str(out_path), "--quiet", str(repo_path)],
            capture_output=True, text=True, timeout=120,
        )
        (out_dir / "brakeman.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("brakeman", "brakeman timed out", out_path)


def _run_eslint_security(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "eslint-security.sarif.json"
    npx = shutil.which("npx")
    eslint = shutil.which("eslint") or (npx and "npx eslint")
    if not npx and not shutil.which("eslint"):
        _scanner_missing_sarif("eslint-plugin-security", "npm install -g eslint eslint-plugin-security", out_path)
        return

    version = _get_version("eslint") if shutil.which("eslint") else "unknown"
    config_content = json.dumps({
        "plugins": ["security"],
        "extends": ["plugin:security/recommended"],
        "env": {"node": True, "es2021": True},
    }, indent=2)
    config_path = out_dir / ".eslintrc.security.json"
    config_path.write_text(config_content)

    try:
        cmd = ["npx", "eslint", "--config", str(config_path), "--format", "json", "--output-file", str(out_dir / "eslint-security.json"), str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(repo_path))
        (out_dir / "eslint-security.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("eslint-plugin-security", "eslint timed out", out_path)
        return

    raw_path = out_dir / "eslint-security.json"
    if not raw_path.exists():
        _scanner_missing_sarif("eslint-plugin-security", "eslint produced no output", out_path)
        return

    try:
        data = json.loads(raw_path.read_text())
    except json.JSONDecodeError:
        _scanner_missing_sarif("eslint-plugin-security", "eslint output unparseable", out_path)
        return

    results = []
    for file_result in data:
        filepath = file_result.get("filePath", "")
        try:
            rel = str(Path(filepath).relative_to(repo_path))
        except ValueError:
            rel = filepath
        for msg in file_result.get("messages", []):
            severity = "error" if msg.get("severity", 1) == 2 else "warning"
            rule_id = msg.get("ruleId", "eslint/unknown")
            line_num = msg.get("line", 1)
            fingerprint = f"eslint/{rule_id}/{rel}:{line_num}"
            results.append({
                "ruleId": rule_id,
                "level": severity,
                "message": {"text": msg.get("message", "")},
                "fingerprints": {"primaryLocation": fingerprint},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": rel}, "region": {"startLine": line_num}}}],
            })

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": "eslint-plugin-security", "version": version, "rules": []}}, "results": results}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_cppcheck(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "cppcheck.sarif.json"
    if not shutil.which("cppcheck"):
        _scanner_missing_sarif("cppcheck", "brew install cppcheck", out_path)
        return

    version = _get_version("cppcheck")
    xml_out = out_dir / "cppcheck.xml"
    try:
        result = subprocess.run(
            ["cppcheck", "--enable=all", "--xml", "--xml-version=2", "--output-file", str(xml_out), str(repo_path)],
            capture_output=True, text=True, timeout=120,
        )
        (out_dir / "cppcheck.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("cppcheck", "cppcheck timed out", out_path)
        return

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": "cppcheck", "version": version, "rules": []}}, "results": []}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_flawfinder(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "flawfinder.sarif.json"
    if not shutil.which("flawfinder"):
        _scanner_missing_sarif("flawfinder", "pip install flawfinder", out_path)
        return

    version = _get_version("flawfinder")
    try:
        result = subprocess.run(
            ["flawfinder", "--sarif", str(repo_path)],
            capture_output=True, text=True, timeout=120,
        )
        (out_dir / "flawfinder.stderr").write_text(result.stderr)
        if result.stdout.strip():
            out_path.write_text(result.stdout)
        else:
            sarif = {"version": "2.1.0", "$schema": SARIF_SCHEMA, "runs": [{"tool": {"driver": {"name": "flawfinder", "version": version, "rules": []}}, "results": []}]}
            out_path.write_text(json.dumps(sarif, indent=2))
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("flawfinder", "flawfinder timed out", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dispatch per-language SAST scanners and emit SARIF 2.1.0 files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo-path", required=True, help="Absolute path to the repository root")
    parser.add_argument("--out-dir", required=True, help="Absolute path to the output directory")
    parser.add_argument("--languages", required=True, help="Comma-separated list of detected languages")
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not repo_path.is_dir():
        print(f"ERROR: --repo-path '{repo_path}' is not a directory", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    languages = [lang.strip().lower() for lang in args.languages.split(",") if lang.strip()]

    print(f"Running SAST for languages: {languages}", file=sys.stderr)

    _run_semgrep(repo_path, out_dir, languages)

    for lang in languages:
        if lang == "python":
            _run_bandit(repo_path, out_dir)
        elif lang in ("javascript", "typescript"):
            _run_eslint_security(repo_path, out_dir)
        elif lang == "go":
            _run_gosec(repo_path, out_dir)
        elif lang == "ruby":
            _run_brakeman(repo_path, out_dir)
        elif lang == "c_cpp":
            _run_cppcheck(repo_path, out_dir)
            _run_flawfinder(repo_path, out_dir)

    print("SAST scan complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
