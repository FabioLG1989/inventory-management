#!/bin/bash
# Workspace topology detection: is a project root a multi-repo parent — a
# folder, itself a git repo or not, whose top-level children are git repos?
#
# Sourceable only. It defines functions and has no side effects, so callers
# (`ensure-context.sh`) `source` it and call `is_multi_repo`. The TypeScript
# mirror lives in `orchestration/src/services/wiki/wiki-state.ts`; keep the
# two rules identical.
#
# Stack-agnostic — operates purely on git plumbing; no language or
# project-layout assumptions.

# Echoes one absolute path per line of top-level dirs under <parent> that
# are themselves git repos, excluding the framework dir. Top-level only —
# deeper nesting would cross repository boundaries no caller walks.
_qaf_discover_children() {
  local parent="$1"
  local framework="$2"
  local framework_real
  framework_real="$(cd "$framework" 2>/dev/null && pwd -P)" || framework_real="$framework"

  local entry rel real
  for entry in "$parent"/*/; do
    [ -d "$entry" ] || continue
    # `.git` may be a directory (normal repo) or a file (gitfile/worktree).
    if [ ! -e "$entry/.git" ]; then
      continue
    fi
    real="$(cd "$entry" 2>/dev/null && pwd -P)" || real=""
    [ -n "$real" ] || continue
    [ "$real" = "$framework_real" ] && continue
    # Skip empty repos (no HEAD yet): there is no commit to branch from or
    # record.
    if ! git -C "$entry" rev-parse HEAD >/dev/null 2>&1; then
      continue
    fi
    # Echo the trimmed absolute path (no trailing slash).
    echo "${entry%/}"
  done
}

# Returns 0 only when <parent>/.gitmodules does NOT exist. A parent that
# manages submodules itself moves its own HEAD with the children, so it is a
# single-repo layout for topology purposes.
_qaf_safe_to_manage() {
  [ ! -e "$1/.gitmodules" ]
}

# Returns 0 (true) when <parent> is a multi-repo layout: a folder (git repo or
# not) with no `.gitmodules` of its own and at least one nested top-level
# child git repo (excluding the framework dir). `ensure-context.sh` records the answer in
# the preflight marker for the /implement-ticket phases that branch, commit
# and push per repo.
is_multi_repo() {
  local parent="$1" framework="$2"
  _qaf_safe_to_manage "$parent" || return 1
  local children
  children="$(_qaf_discover_children "$parent" "$framework")"
  [ -n "$children" ]
}
