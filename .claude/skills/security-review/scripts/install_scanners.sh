#!/usr/bin/env bash
# One-shot scanner installation for fresh machines. Idempotent: safe to re-run.
# Installs security scanners used by the security-review skill across all
# supported language stacks. Uses brew on macOS, apt on Debian/Ubuntu, and
# cargo/pip/gem/go install as language-specific fallbacks.
#
# Usage: bash install_scanners.sh [--dry-run]
# Exit: 0 when all installations succeed or were already present;
#       non-zero only if a critical universal scanner fails to install.

set -euo pipefail

DRY_RUN=false

print_help() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h) print_help ;;
      --dry-run) DRY_RUN=true; shift ;;
      *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
    esac
  done
}

detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macos"
  elif [[ -f /etc/debian_version ]] || command -v apt &>/dev/null; then
    echo "linux-apt"
  else
    echo "linux-other"
  fi
}

run_cmd() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

install_brew_package() {
  local pkg="$1"
  if brew list "$pkg" &>/dev/null 2>&1; then
    echo "  $pkg already installed"
  else
    echo "  Installing $pkg via brew ..."
    run_cmd brew install "$pkg"
  fi
}

install_apt_package() {
  local pkg="$1"
  if dpkg -l "$pkg" &>/dev/null 2>&1; then
    echo "  $pkg already installed"
  else
    echo "  Installing $pkg via apt ..."
    run_cmd sudo apt-get install -y "$pkg"
  fi
}

install_pip_package() {
  local pkg="$1"
  local cmd="${2:-$1}"
  if command -v "$cmd" &>/dev/null; then
    echo "  $pkg already installed"
  else
    echo "  Installing $pkg via pip ..."
    run_cmd pip install --quiet "$pkg"
  fi
}

install_go_tool() {
  local import_path="$1"
  local cmd="$2"
  if command -v "$cmd" &>/dev/null; then
    echo "  $cmd already installed"
  else
    echo "  Installing $cmd via go install ..."
    run_cmd go install "$import_path"
  fi
}

install_cargo_crate() {
  local crate="$1"
  local cmd="${2:-$1}"
  if command -v "$cmd" &>/dev/null; then
    echo "  $cmd already installed"
  else
    echo "  Installing $crate via cargo install ..."
    run_cmd cargo install "$crate"
  fi
}

install_gem() {
  local gem_name="$1"
  local cmd="${2:-$1}"
  if command -v "$cmd" &>/dev/null; then
    echo "  $cmd already installed"
  else
    echo "  Installing $gem_name via gem ..."
    run_cmd gem install "$gem_name"
  fi
}

install_universal_scanners() {
  local os="$1"
  echo ""
  echo "==> Universal scanners (gitleaks, trufflehog, semgrep, osv-scanner) ..."
  if [[ "$os" == "macos" ]]; then
    install_brew_package gitleaks
    install_brew_package trufflesecurity/trufflehog/trufflehog
    install_brew_package osv-scanner
  elif [[ "$os" == "linux-apt" ]]; then
    if ! command -v gitleaks &>/dev/null; then
      echo "  Installing gitleaks via GitHub release ..."
      run_cmd bash -c "curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_linux_x64.tar.gz | tar xz -C /usr/local/bin gitleaks"
    else
      echo "  gitleaks already installed"
    fi
    if ! command -v trufflehog &>/dev/null; then
      echo "  Installing trufflehog via script ..."
      run_cmd bash -c "curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin"
    else
      echo "  trufflehog already installed"
    fi
    if ! command -v osv-scanner &>/dev/null; then
      echo "  Installing osv-scanner via Go ..."
      run_cmd go install github.com/google/osv-scanner/cmd/osv-scanner@latest
    else
      echo "  osv-scanner already installed"
    fi
  fi
  install_pip_package semgrep semgrep
}

install_python_scanners() {
  echo ""
  echo "==> Python scanners (bandit, pip-audit) ..."
  install_pip_package bandit bandit
  install_pip_package pip-audit pip-audit
}

install_js_ts_scanners() {
  echo ""
  echo "==> JS/TS scanners (eslint, eslint-plugin-security) ..."
  if ! command -v npm &>/dev/null; then
    echo "  WARN: npm not found; skipping JS/TS scanner install. Install Node.js first."
    return 0
  fi
  if ! npm list -g eslint &>/dev/null 2>&1; then
    run_cmd npm install -g eslint eslint-plugin-security
  else
    echo "  eslint already installed globally"
  fi
}

install_go_scanners() {
  echo ""
  echo "==> Go scanners (gosec, govulncheck) ..."
  if ! command -v go &>/dev/null; then
    echo "  WARN: go not found; skipping Go scanner install."
    return 0
  fi
  install_go_tool github.com/securego/gosec/v2/cmd/gosec@latest gosec
  install_go_tool golang.org/x/vuln/cmd/govulncheck@latest govulncheck
}

install_rust_scanners() {
  echo ""
  echo "==> Rust scanners (cargo-audit, cargo-deny) ..."
  if ! command -v cargo &>/dev/null; then
    echo "  WARN: cargo not found; skipping Rust scanner install."
    return 0
  fi
  install_cargo_crate cargo-audit cargo-audit
  install_cargo_crate cargo-deny cargo-deny
}

install_ruby_scanners() {
  echo ""
  echo "==> Ruby scanners (brakeman, bundler-audit) ..."
  if ! command -v gem &>/dev/null; then
    echo "  WARN: gem not found; skipping Ruby scanner install."
    return 0
  fi
  install_gem brakeman brakeman
  install_gem bundler-audit bundle-audit
}

install_iac_scanners() {
  local os="$1"
  echo ""
  echo "==> IaC scanners (trivy, checkov) ..."
  if [[ "$os" == "macos" ]]; then
    install_brew_package trivy
  elif [[ "$os" == "linux-apt" ]]; then
    if ! command -v trivy &>/dev/null; then
      echo "  Installing trivy via script ..."
      run_cmd bash -c "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin"
    else
      echo "  trivy already installed"
    fi
  fi
  install_pip_package checkov checkov
}

install_c_cpp_scanners() {
  local os="$1"
  echo ""
  echo "==> C/C++ scanners (cppcheck, flawfinder) ..."
  if [[ "$os" == "macos" ]]; then
    install_brew_package cppcheck
  elif [[ "$os" == "linux-apt" ]]; then
    install_apt_package cppcheck
  fi
  install_pip_package flawfinder flawfinder
}

main() {
  parse_args "$@"

  local os
  os=$(detect_os)
  echo "Detected OS: $os"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN mode enabled — no changes will be made]"
  fi

  install_universal_scanners "$os"
  install_python_scanners
  install_js_ts_scanners
  install_go_scanners
  install_rust_scanners
  install_ruby_scanners
  install_iac_scanners "$os"
  install_c_cpp_scanners "$os"

  echo ""
  echo "Scanner installation complete."
  echo "Re-run this script at any time to ensure all scanners are up to date."
}

main "$@"
