#!/usr/bin/env bash
# Run trivy and checkov against IaC files (Dockerfile, Terraform, Kubernetes manifests)
# and emit SARIF 2.1.0 output files under --out-dir. Never mutates the target tree.
#
# Usage: bash run_iac.sh --repo-path <abs> --out-dir <abs>
# Exit: 0 on success (even with findings); non-zero only on hard failure.

set -euo pipefail

REPO_PATH=""
OUT_DIR=""

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

run_trivy() {
  local sarif_out="$OUT_DIR/trivy.sarif.json"

  if ! command -v trivy &>/dev/null; then
    echo "WARN: trivy not found. Emitting scanner-missing finding." >&2
    emit_missing_scanner_sarif "trivy" "brew install trivy" "$sarif_out"
    return 0
  fi

  local trivy_version
  trivy_version=$(trivy --version 2>/dev/null | head -1 || echo "unknown")
  echo "Running trivy $trivy_version ..." >&2

  trivy fs \
    --format sarif \
    --output "$sarif_out" \
    --scanners vuln,misconfig,secret \
    --exit-code 0 \
    "$REPO_PATH" \
    2>"$OUT_DIR/trivy.stderr" || {
    echo "WARN: trivy exited non-zero. See $OUT_DIR/trivy.stderr" >&2
  }

  echo "trivy complete. SARIF written to $sarif_out" >&2
}

run_checkov() {
  local sarif_out="$OUT_DIR/checkov.sarif.json"

  if ! command -v checkov &>/dev/null; then
    echo "WARN: checkov not found. Emitting scanner-missing finding." >&2
    emit_missing_scanner_sarif "checkov" "pip install checkov" "$sarif_out"
    return 0
  fi

  local checkov_version
  checkov_version=$(checkov --version 2>/dev/null | head -1 || echo "unknown")
  echo "Running checkov $checkov_version ..." >&2

  checkov \
    --directory "$REPO_PATH" \
    --output sarif \
    --output-file-path "$OUT_DIR" \
    --soft-fail \
    --quiet \
    2>"$OUT_DIR/checkov.stderr" || {
    echo "WARN: checkov exited non-zero. See $OUT_DIR/checkov.stderr" >&2
  }

  local checkov_default="$OUT_DIR/results_sarif.sarif"
  if [[ -f "$checkov_default" ]] && [[ ! -f "$sarif_out" ]]; then
    mv "$checkov_default" "$sarif_out"
  fi

  if [[ ! -f "$sarif_out" ]]; then
    cat > "$sarif_out" <<JSON
{
  "version": "2.1.0",
  "\$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "runs": [{ "tool": { "driver": { "name": "checkov", "version": "$checkov_version", "rules": [] } }, "results": [] }]
}
JSON
  fi

  echo "checkov complete. SARIF written to $sarif_out" >&2
}

main() {
  parse_args "$@"
  validate_args

  mkdir -p "$OUT_DIR"

  run_trivy
  run_checkov

  echo "IaC scan complete." >&2
}

main "$@"
