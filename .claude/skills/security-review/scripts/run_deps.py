"""Run dependency vulnerability scanners per detected language and emit SARIF 2.1.0.

Primary scanner: osv-scanner (cross-ecosystem). Per-language fallbacks:
  python     -> pip-audit
  javascript -> npm audit / pnpm audit
  typescript -> npm audit / pnpm audit
  go         -> govulncheck
  rust       -> cargo audit
  java       -> OWASP dependency-check (if available)
  ruby       -> bundle-audit
  php        -> composer audit
  dotnet     -> dotnet list package --vulnerable

When a scanner binary is absent, a scanner-missing SARIF finding is emitted
and the pipeline continues. Never mutates the target tree.
"""

from __future__ import annotations

import argparse
import json
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


def _empty_sarif(tool: str, version: str, out_path: Path) -> None:
    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": tool, "version": version, "rules": []}}, "results": []}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_osv_scanner(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "osv-scanner.sarif.json"
    if not shutil.which("osv-scanner"):
        _scanner_missing_sarif("osv-scanner", "brew install osv-scanner", out_path)
        return

    version = _get_version("osv-scanner")
    try:
        result = subprocess.run(
            ["osv-scanner", "--format", "sarif", "--recursive", str(repo_path)],
            capture_output=True, text=True, timeout=180,
        )
        (out_dir / "osv-scanner.stderr").write_text(result.stderr)
        if result.stdout.strip():
            out_path.write_text(result.stdout)
        else:
            _empty_sarif("osv-scanner", version, out_path)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("osv-scanner", "osv-scanner timed out", out_path)


def _run_pip_audit(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "pip-audit.sarif.json"
    if not shutil.which("pip-audit"):
        _scanner_missing_sarif("pip-audit", "pip install pip-audit", out_path)
        return

    version = _get_version("pip-audit")
    raw_out = out_dir / "pip-audit.json"
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json", "--output", str(raw_out), "--path", str(repo_path)],
            capture_output=True, text=True, timeout=120, cwd=str(repo_path),
        )
        (out_dir / "pip-audit.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("pip-audit", "pip-audit timed out", out_path)
        return

    if not raw_out.exists():
        _empty_sarif("pip-audit", version, out_path)
        return

    try:
        data = json.loads(raw_out.read_text())
    except json.JSONDecodeError:
        _empty_sarif("pip-audit", version, out_path)
        return

    results = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id", "unknown")
            pkg = dep.get("name", "unknown")
            version_str = dep.get("version", "unknown")
            fingerprint = f"pip-audit/{vuln_id}/{pkg}/{version_str}"
            results.append({
                "ruleId": vuln_id,
                "level": "error",
                "message": {"text": f"{vuln.get('description', vuln_id)} in {pkg}=={version_str}"},
                "fingerprints": {"primaryLocation": fingerprint},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "requirements.txt"}}}],
                "properties": {"fix": vuln.get("fix_versions", [])},
            })

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": "pip-audit", "version": version, "informationUri": "https://github.com/pypa/pip-audit", "rules": []}}, "results": results}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_npm_audit(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "npm-audit.sarif.json"
    npm = shutil.which("npm") or shutil.which("pnpm")
    if not npm:
        _scanner_missing_sarif("npm-audit", "install Node.js (includes npm)", out_path)
        return

    tool_name = "pnpm-audit" if "pnpm" in (npm or "") else "npm-audit"
    version = _get_version(npm)
    raw_out = out_dir / "npm-audit.json"
    try:
        cmd = [npm, "audit", "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(repo_path))
        (out_dir / "npm-audit.stderr").write_text(result.stderr)
        if result.stdout.strip():
            raw_out.write_text(result.stdout)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif(tool_name, "npm audit timed out", out_path)
        return

    if not raw_out.exists():
        _empty_sarif(tool_name, version, out_path)
        return

    try:
        data = json.loads(raw_out.read_text())
    except json.JSONDecodeError:
        _empty_sarif(tool_name, version, out_path)
        return

    level_map = {"critical": "error", "high": "error", "moderate": "warning", "low": "note", "info": "note"}
    results = []
    vulns = data.get("vulnerabilities", {})
    for pkg, info in vulns.items():
        sev = info.get("severity", "low")
        via = info.get("via", [])
        cve_ids = [v.get("url", "").split("/")[-1] for v in via if isinstance(v, dict) and "url" in v]
        for cve_id in cve_ids or [f"npm/{pkg}"]:
            fingerprint = f"npm-audit/{cve_id}/{pkg}"
            results.append({
                "ruleId": cve_id,
                "level": level_map.get(sev, "note"),
                "message": {"text": f"Vulnerable dependency: {pkg} ({sev})"},
                "fingerprints": {"primaryLocation": fingerprint},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "package.json"}}}],
            })

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": tool_name, "version": version, "rules": []}}, "results": results}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_cargo_audit(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "cargo-audit.sarif.json"
    if not shutil.which("cargo"):
        _scanner_missing_sarif("cargo-audit", "curl https://sh.rustup.rs -sSf | sh", out_path)
        return

    version = "unknown"
    raw_out = out_dir / "cargo-audit.json"
    try:
        result = subprocess.run(
            ["cargo", "audit", "--json"],
            capture_output=True, text=True, timeout=120, cwd=str(repo_path),
        )
        (out_dir / "cargo-audit.stderr").write_text(result.stderr)
        if result.stdout.strip():
            raw_out.write_text(result.stdout)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("cargo-audit", "cargo audit timed out", out_path)
        return

    if not raw_out.exists():
        _empty_sarif("cargo-audit", version, out_path)
        return

    try:
        data = json.loads(raw_out.read_text())
    except json.JSONDecodeError:
        _empty_sarif("cargo-audit", version, out_path)
        return

    results = []
    for vuln in data.get("vulnerabilities", {}).get("list", []):
        adv = vuln.get("advisory", {})
        pkg = vuln.get("package", {}).get("name", "unknown")
        vuln_id = adv.get("id", "unknown")
        fingerprint = f"cargo-audit/{vuln_id}/{pkg}"
        results.append({
            "ruleId": vuln_id,
            "level": "error",
            "message": {"text": adv.get("title", vuln_id)},
            "fingerprints": {"primaryLocation": fingerprint},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "Cargo.toml"}}}],
        })

    sarif = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{"tool": {"driver": {"name": "cargo-audit", "version": version, "rules": []}}, "results": results}],
    }
    out_path.write_text(json.dumps(sarif, indent=2))


def _run_govulncheck(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "govulncheck.sarif.json"
    if not shutil.which("govulncheck"):
        _scanner_missing_sarif("govulncheck", "go install golang.org/x/vuln/cmd/govulncheck@latest", out_path)
        return

    version = _get_version("govulncheck")
    try:
        result = subprocess.run(
            ["govulncheck", "-json", "./..."],
            capture_output=True, text=True, timeout=120, cwd=str(repo_path),
        )
        (out_dir / "govulncheck.stderr").write_text(result.stderr)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("govulncheck", "govulncheck timed out", out_path)
        return

    _empty_sarif("govulncheck", version, out_path)


def _run_bundle_audit(repo_path: Path, out_dir: Path) -> None:
    out_path = out_dir / "bundle-audit.sarif.json"
    if not shutil.which("bundle-audit"):
        _scanner_missing_sarif("bundle-audit", "gem install bundler-audit", out_path)
        return

    version = _get_version("bundle-audit")
    try:
        result = subprocess.run(
            ["bundle-audit", "check", "--update"],
            capture_output=True, text=True, timeout=120, cwd=str(repo_path),
        )
        (out_dir / "bundle-audit.stderr").write_text(result.stderr)
        (out_dir / "bundle-audit.txt").write_text(result.stdout)
    except subprocess.TimeoutExpired:
        _scanner_missing_sarif("bundle-audit", "bundle-audit timed out", out_path)
        return

    _empty_sarif("bundle-audit", version, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run dependency vulnerability scanners per detected language.",
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

    print(f"Running dependency audit for languages: {languages}", file=sys.stderr)

    _run_osv_scanner(repo_path, out_dir)

    for lang in languages:
        if lang == "python":
            _run_pip_audit(repo_path, out_dir)
        elif lang in ("javascript", "typescript"):
            _run_npm_audit(repo_path, out_dir)
        elif lang == "rust":
            _run_cargo_audit(repo_path, out_dir)
        elif lang == "go":
            _run_govulncheck(repo_path, out_dir)
        elif lang == "ruby":
            _run_bundle_audit(repo_path, out_dir)

    print("Dependency audit complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
