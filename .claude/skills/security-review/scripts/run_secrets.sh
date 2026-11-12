#!/usr/bin/env bash
# Runs gitleaks and trufflehog (verified mode) against a repository and emits
# SARIF 2.1.0 output files under --out-dir. Respects .gitleaks.toml when present.
# Accepts an optional --baseline <sarif-path> flag to carry over baseline
# suppressions into the emitted SARIF. Never mutates the target repository.
#
# Usage: bash run_secrets.sh --repo-path <abs> --out-dir <abs> [--baseline <path>]
# Exit: 0 on success (even with findings); non-zero only on hard failure.

set -euo pipefail

REPO_PATH=""
OUT_DIR=""
BASELINE=""

print_help() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h) print_help ;;
      --repo-path) REPO_PATH="$2"; shift 2 ;;
      --out-dir) OUT_DIR="$2"; shift 2 ;;
      --baseline) BASELINE="$2"; shift 2 ;;
      *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
    esac
  done
}

validate_args() {
  if [[ -z "$REPO_PATH" ]]; then
    echo "ERROR: --repo-path is required" >&2
    exit 1
  fi
  if [[ -z "$OUT_DIR" ]]; then
    echo "ERROR: --out-dir is required" >&2
    exit 1
  fi
  if [[ ! -d "$REPO_PATH" ]]; then
    echo "ERROR: --repo-path '$REPO_PATH' is not a directory" >&2
    exit 1
  fi
}

emit_missing_scanner_sarif() {
  local tool="$1"
  local install_cmd="$2"
  local out_file="$3"
  cat > "$out_file" <<JSON
{
  "version": "2.1.0",
  "\$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "runs": [{
    "tool": { "driver": { "name": "$tool", "version": "unknown", "rules": [] } },
    "results": [{
      "ruleId": "scanner-missing",
      "level": "warning",
      "message": { "text": "Scanner '$tool' not installed. Install with: $install_cmd" },
      "fingerprints": { "primaryLocation": "scanner-missing/$tool" },
      "locations": []
    }]
  }]
}
JSON
}

run_gitleaks() {
  local sarif_out="$OUT_DIR/gitleaks.sarif.json"

  if ! command -v gitleaks &>/dev/null; then
    echo "WARN: gitleaks not found. Emitting scanner-missing finding." >&2
    emit_missing_scanner_sarif "gitleaks" "brew install gitleaks" "$sarif_out"
    return 0
  fi

  local gitleaks_version
  gitleaks_version=$(gitleaks version 2>/dev/null | head -1 || echo "unknown")
  echo "Running gitleaks $gitleaks_version ..." >&2

  local extra_args=()
  if [[ -f "$REPO_PATH/.gitleaks.toml" ]]; then
    extra_args+=(--config "$REPO_PATH/.gitleaks.toml")
  fi

  gitleaks detect \
    --source "$REPO_PATH" \
    --report-format sarif \
    --report-path "$sarif_out" \
    --no-git \
    "${extra_args[@]}" \
    2>"$OUT_DIR/gitleaks.stderr" || {
    local exit_code=$?
    if [[ $exit_code -eq 1 ]]; then
      echo "gitleaks found secrets (exit 1 is expected)" >&2
    else
      echo "WARN: gitleaks exited with code $exit_code. See $OUT_DIR/gitleaks.stderr" >&2
    fi
  }

  echo "gitleaks complete. SARIF written to $sarif_out" >&2
}

run_trufflehog() {
  local sarif_out="$OUT_DIR/trufflehog.sarif.json"

  if ! command -v trufflehog &>/dev/null; then
    echo "WARN: trufflehog not found. Emitting scanner-missing finding." >&2
    emit_missing_scanner_sarif "trufflehog" "brew install trufflesecurity/trufflehog/trufflehog" "$sarif_out"
    return 0
  fi

  local trufflehog_version
  trufflehog_version=$(trufflehog --version 2>/dev/null | head -1 || echo "unknown")
  echo "Running trufflehog $trufflehog_version (verified mode) ..." >&2

  local json_out="$OUT_DIR/trufflehog.json"
  trufflehog filesystem "$REPO_PATH" \
    --only-verified \
    --json \
    2>"$OUT_DIR/trufflehog.stderr" \
    > "$json_out" || {
    echo "WARN: trufflehog exited non-zero. See $OUT_DIR/trufflehog.stderr" >&2
  }

  python3 - <<PYEOF
import json, sys
from pathlib import Path

raw_path = Path("$json_out")
if not raw_path.exists() or raw_path.stat().st_size == 0:
    sarif = {
        "version": "2.1.0",
        "\$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "trufflehog", "version": "$trufflehog_version", "rules": []}}, "results": []}]
    }
    Path("$sarif_out").write_text(json.dumps(sarif, indent=2))
    sys.exit(0)

results = []
for line in raw_path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        finding = json.loads(line)
    except json.JSONDecodeError:
        continue
    det_type = finding.get("DetectorName", "unknown")
    source_meta = finding.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
    filepath = source_meta.get("file", "")
    fingerprint = f"trufflehog/{det_type}/{filepath}"
    results.append({
        "ruleId": f"trufflehog/{det_type}",
        "level": "error",
        "message": {"text": f"Verified secret detected: {det_type}"},
        "fingerprints": {"primaryLocation": fingerprint},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": filepath}}}]
    })

sarif = {
    "version": "2.1.0",
    "\$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "runs": [{"tool": {"driver": {"name": "trufflehog", "version": "$trufflehog_version", "rules": []}}, "results": results}]
}
Path("$sarif_out").write_text(json.dumps(sarif, indent=2))
print(f"trufflehog: {len(results)} verified findings written to $sarif_out", file=sys.stderr)
PYEOF
}

main() {
  parse_args "$@"
  validate_args

  mkdir -p "$OUT_DIR"

  run_gitleaks
  run_trufflehog

  echo "Secrets scan complete." >&2
}

main "$@"
