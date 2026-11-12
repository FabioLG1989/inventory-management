#!/usr/bin/env bash
# Shared Phase 0/1 preflight bootstrap for /create-implementation-plan and
# /implement-ticket. Sourced, never executed — must not set shell options.
#
# The single definition of how both skills resolve $ARTIFACTS_DIR and run the
# deterministic preflight, so producer and consumer always anchor to the
# identical workspace-root artifacts dir. Shipped next to resolve-paths.sh and
# one level below ensure-context.sh under <project>/<config-dir>/scripts/.
#
# TEMP_DIR is taken from the config dir this copy lives under (.claude ->
# .claude-temp, .codex -> .codex-temp), matching the {{TEMP_DIR}} the sibling
# skills were rendered with.
#
# Usage (in a skill):
#   source "<config-dir>/scripts/lib/bootstrap-preflight.sh"
#   qaf_resolve_artifacts_dir "$TICKET_ID"   # sets + exports ARTIFACTS_DIR
#   qaf_run_preflight "$TICKET_ID"           # + runs ensure-context.sh; returns its exit code
#   qaf_progress "$TICKET_ID" 4 Implementation in_progress [note]   # appends to progress.jsonl
#
# `${BASH_SOURCE:-${(%):-%x}}` resolves this sourced file's own path in both
# shells: bash uses $BASH_SOURCE; zsh leaves it empty and prompt-expands %x to
# the file being sourced. bash never evaluates the default branch, so the
# zsh-only syntax is inert there.

__bootstrap_preflight_src="${BASH_SOURCE:-${(%):-%x}}"
__bootstrap_preflight_lib_dir="$(cd "$(dirname "$__bootstrap_preflight_src")" && pwd)"
__bootstrap_preflight_scripts_dir="$(dirname "$__bootstrap_preflight_lib_dir")"
__bootstrap_preflight_config_dir="$(basename "$(dirname "$__bootstrap_preflight_scripts_dir")")"
__bootstrap_preflight_temp_dir="${__bootstrap_preflight_config_dir}-temp"

# shellcheck source=resolve-paths.sh
source "$__bootstrap_preflight_lib_dir/resolve-paths.sh"

qaf_resolve_artifacts_dir() {
  local ticket_id="${1:?qaf_resolve_artifacts_dir: TICKET_ID required}"
  ARTIFACTS_DIR="$(project_path)/$__bootstrap_preflight_temp_dir/tickets/$ticket_id/artifacts"
  export ARTIFACTS_DIR
  mkdir -p "$ARTIFACTS_DIR/context" "$ARTIFACTS_DIR/plans"
  printf '%s\n' "$ARTIFACTS_DIR"
}

qaf_run_preflight() {
  local ticket_id="${1:?qaf_run_preflight: TICKET_ID required}"
  local project
  project="$(project_path)"
  cd "$project" || return 1
  qaf_resolve_artifacts_dir "$ticket_id" >/dev/null
  PROJECT_PATH="$project" bash "$__bootstrap_preflight_scripts_dir/ensure-context.sh" --artifacts-dir "$ARTIFACTS_DIR"
}

# Escapes a string for use inside a JSON string literal: backslash, double
# quote, newline, carriage return, and tab. Parameter expansion only, so it
# behaves identically under bash and zsh.
__qaf_json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# Appends one JSONL record for a phase transition to $ARTIFACTS_DIR/progress.jsonl,
# resolving the artifacts dir itself so a skill folds the append into the same
# command as the phase's real work and never spends a tool call on it:
#   qaf_progress "$TICKET_ID" 4 Implementation in_progress && <work> \
#     && qaf_progress "$TICKET_ID" 4 Implementation completed
# An integer phase is written as a JSON number; a delegated sub-step key such
# as "2.3" as a string. The optional fifth argument is recorded as "reason" when
# the status is `failed` and as "note" for any other status.
qaf_progress() {
  local ticket_id="${1:?qaf_progress: TICKET_ID required}"
  local phase="${2:?qaf_progress: phase required}"
  local name="${3:?qaf_progress: name required}"
  local phase_status="${4:?qaf_progress: status required}"
  local detail="${5:-}"
  qaf_resolve_artifacts_dir "$ticket_id" >/dev/null
  local phase_json
  case "$phase" in
    ''|*[!0-9]*) phase_json="\"$(__qaf_json_escape "$phase")\"" ;;
    *) phase_json="$phase" ;;
  esac
  local record
  record="{\"phase\": $phase_json, \"name\": \"$(__qaf_json_escape "$name")\", \"status\": \"$(__qaf_json_escape "$phase_status")\""
  if [ -n "$detail" ]; then
    if [ "$phase_status" = "failed" ]; then
      record="$record, \"reason\": \"$(__qaf_json_escape "$detail")\""
    else
      record="$record, \"note\": \"$(__qaf_json_escape "$detail")\""
    fi
  fi
  record="$record, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
  printf '%s\n' "$record" >> "$ARTIFACTS_DIR/progress.jsonl"
}
