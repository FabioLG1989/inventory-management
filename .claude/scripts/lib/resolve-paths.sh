#!/usr/bin/env bash
# Shim-only path resolver shipped under `<project>/.claude/scripts/lib/`
# (and the `.codex/scripts/lib/` equivalent). The preflight-scripts service
# copies this file out to engineer machines so `ensure-context.sh` and
# `clean-qaf.sh` can locate the project root without depending on a
# `qubika-agentic-framework/` checkout being present in the user's project.
#
# This file intentionally exports ONLY `project_path()`. The full
# `framework_path()` lookup lives in the framework-internal companion
# (`scripts/lib/resolve-paths.sh`) for callers like `initialize-project` and
# `wiki-refresh` that actually need to locate the framework checkout.
#
# Usage (in another script):
#   source "<project>/.claude/scripts/lib/resolve-paths.sh"
#   PROJECT_PATH="$(project_path)"
#
# Variables produced by this helper are LOCALLY SCOPED — never `export` them.
# The single allowed env injection is a child-process VAR=value invocation,
# not a global export.
#
# The shim is installed at a FIXED depth — `<root>/.claude/scripts/lib/` (or the
# `.codex/...` equivalent) — so the project root is always exactly three levels
# up from this file's own directory; no upward directory search is needed.
#
# `${BASH_SOURCE:-${(%):-%x}}` resolves this sourced file's own path in both
# shells: bash uses `$BASH_SOURCE`; zsh leaves it empty and falls back to the
# default, where `${(%):-%x}` prompt-expands `%x` to the file being sourced.
# That zsh form is option-independent — correct even under `unsetopt
# FUNCTION_ARGZERO` or `setopt POSIX_ARGZERO`, where `$0` would be wrong. bash
# never evaluates the default branch (BASH_SOURCE is set), so the zsh-only
# syntax is inert there.
__resolve_paths_src="${BASH_SOURCE:-${(%):-%x}}"
__resolve_paths_root="$(cd "$(dirname "$__resolve_paths_src")/../../.." && pwd)"

# Name the provider this copy was installed for: `.codex/scripts/lib/` → codex,
# `.claude/scripts/lib/` → claude. Read from the shim's own location, so it is
# exact rather than a guess from which directories the project happens to carry
# — a codex install in a repo that also holds a leftover `.claude/` from someone
# opening Claude Code once is the common case, and guessing gets it wrong.
# $QAF_PROVIDER overrides for callers that already resolved it.
provider_name() {
  case "${QAF_PROVIDER:-}" in
    claude|codex) printf '%s\n' "$QAF_PROVIDER"; return ;;
  esac
  case "$(basename "$(cd "$(dirname "$__resolve_paths_src")/../.." && pwd)")" in
    .codex) printf 'codex\n' ;;
    *) printf 'claude\n' ;;
  esac
}

project_path() {
  if [ -n "${PROJECT_PATH:-}" ] && [ -d "$PROJECT_PATH" ]; then
    ( cd "$PROJECT_PATH" && pwd )
    return
  fi
  if [ ! -d "$__resolve_paths_root/.claude" ] && [ ! -d "$__resolve_paths_root/.codex" ]; then
    printf '%s\n' \
      "[resolve-paths] WARN: resolved project root '$__resolve_paths_root' (three levels up from '$__resolve_paths_src') has no .claude or .codex directory; the shim may be installed at an unexpected depth" >&2
  fi
  printf '%s\n' "$__resolve_paths_root"
}
