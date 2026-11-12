#!/bin/bash
# ============================================================================
# ENSURE-CONTEXT — deterministic preflight for /create-sdd-ticket and /implement-ticket
# ============================================================================
#
# Single bash entry point that both skills call as their literal first phase.
# Idempotent.
#
# Usage (engineer projects):
#   bash <project>/.claude/scripts/ensure-context.sh \
#     [--artifacts-dir <path>] [--quiet] [--skip-update-check]
#
# --skip-update-check (or the QAF_SKIP_UPDATE_CHECK env var) fully opts out of
# the framework-release detection step.
#
# The framework's own copy at `<framework>/scripts/ensure-context.sh` is the
# single source of truth and is also runnable directly during dogfooding.
#
# What it does (in order):
#   0. Reuse a fresh .preflight-ok marker when the environment is provably
#      unchanged (same repo HEADs) and no framework-update prompt is pending —
#      the delegated-skill re-run within one ticket exits here in ~1s, carrying
#      the marker's framework_update verdict forward. QAF_PREFLIGHT_FORCE=1
#      skips the reuse.
#   1. Record the workspace topology (single repo or multi-repo parent) and
#      the HEAD of every repo in it.
#   2. Exclude the provider temp dirs and local state files in every repo via
#      .git/info/exclude.
#   3. Remove the gitignored, per-developer leftovers of the retired code-graph
#      integration (`code_graph` MCP entries, `.code-review-graph/`), which a
#      teammate who only pulls the synced config would otherwise keep.
#   4. Resolve the tool-default baseline the skills read back from the marker.
#   5. Detect (read-only, fail-open) whether a newer framework release is
#      available via check-framework-update.sh.
#   6. Write a JSON success marker at <artifacts-dir>/.preflight-ok carrying
#      git_head + per-repo HEADs (so subsequent skill phases can verify the
#      preflight ran for THIS run) plus a framework_update object the skill
#      glue consumes to prompt on an available upgrade.
#
# Wiki staleness is an AI-driven concern the `/wiki-refresh` skill owns: Phase 9
# of `/implement-ticket` invokes it after implementation, and users invoke it
# directly whenever desired. The wiki `.state.json` tracks per-repo commits so
# the skill can diff cheaply.
#
# Exit code:
#   0  – preflight succeeded; the marker is written.
#   non-zero – something the preflight cannot fix on its own. The skill body
#              STOPs and surfaces our stderr to the user.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/resolve-paths.sh
source "$SCRIPT_DIR/lib/resolve-paths.sh"

PREFLIGHT_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

PROJECT_PATH="$(project_path)"

# Every dependency this preflight needs ships as a sibling of this script,
# either inside the framework checkout (`<framework>/scripts/`) or in the
# engineer-facing copy (`<project>/.claude/scripts/`). No `qubika-agentic-framework/`
# checkout is required at runtime in user projects.
REQUIRED_SIBLING_FILES=(
  "$SCRIPT_DIR/lib/workspace-topology.sh"
)
for __required in "${REQUIRED_SIBLING_FILES[@]}"; do
  if [ ! -f "$__required" ]; then
    echo "[ensure-context] ERROR: required preflight file missing: $__required" >&2
    echo "[ensure-context] The shipped scripts directory at $SCRIPT_DIR appears to be incomplete." >&2
    echo "[ensure-context] Remediation: run \`./qubika-agentic-framework/scripts/sync-framework-resources.sh\` (or \`./qubika-agentic-framework/scripts/initialize-project.sh\` for a full rebuild) to repopulate $SCRIPT_DIR." >&2
    FAILED_DIR="${ARTIFACTS_DIR:-$PROJECT_PATH/.claude-temp/preflight}"
    mkdir -p "$FAILED_DIR" 2>/dev/null || true
    cat > "$FAILED_DIR/.preflight-failed" 2>/dev/null <<EOF
{
  "reason": "shipped_scripts_missing",
  "missing": "$__required",
  "scripts_dir": "$SCRIPT_DIR",
  "ran_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
    exit 4
  fi
done
unset __required REQUIRED_SIBLING_FILES

# ---------- option parsing ----------
ARTIFACTS_DIR=""
QUIET=0
SKIP_UPDATE_CHECK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --artifacts-dir)
      ARTIFACTS_DIR="$2"; shift 2 ;;
    --artifacts-dir=*)
      ARTIFACTS_DIR="${1#*=}"; shift ;;
    --quiet)
      QUIET=1; shift ;;
    --skip-update-check)
      SKIP_UPDATE_CHECK=1; shift ;;
    --help|-h)
      sed -n '2,48p' "$0"; exit 0 ;;
    # Accept-and-ignore legacy flags so older callers don't break the moment
    # they upgrade. Safe to drop after one release cycle.
    --force-wiki|--skip-wiki)
      shift ;;
    *)
      echo "[ensure-context] ERROR: unknown argument: $1" >&2
      exit 2 ;;
  esac
done

# Default artifacts dir: <project>/.claude-temp/preflight (or .codex-temp/).
if [ -z "$ARTIFACTS_DIR" ]; then
  ARTIFACTS_DIR="$PROJECT_PATH/.$(provider_name)-temp/preflight"
fi

# Anchor a caller-supplied relative --artifacts-dir (e.g. ".claude-temp/tickets/X/artifacts")
# to the deterministic project root. PROJECT_PATH comes from resolve-paths.sh, which is
# cwd-independent — so the marker, and every phase that reads it back, always lands under
# the workspace root and never inside a child repo, regardless of the caller's cwd.
case "$ARTIFACTS_DIR" in
  /*) : ;;
  *) ARTIFACTS_DIR="$PROJECT_PATH/$ARTIFACTS_DIR" ;;
esac

# ---------- logging ----------
log_info() {
  if [ "$QUIET" -eq 0 ]; then
    echo "[ensure-context] $1"
  fi
}
log_warn() { echo "[ensure-context] WARN: $1" >&2; }
log_error() { echo "[ensure-context] ERROR: $1" >&2; }

# ---------- helpers ----------

git_head() {
  (cd "$PROJECT_PATH" && git rev-parse HEAD 2>/dev/null) || echo ""
}

# ---------- run metadata (console telemetry) ----------

# Escape a scalar value for embedding in a JSON string.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

# Framework version from the project's framework-config.json:
# sync_version (last resource sync) falling back to version (initialization).
qaf_version() {
  local cfg="$PROJECT_PATH/.$1/framework-config.json"
  if [ ! -f "$cfg" ]; then
    echo ""
    return
  fi
  if command -v node >/dev/null 2>&1; then
    node -e '
      try {
        const cfg = JSON.parse(require("fs").readFileSync(process.argv[1], "utf-8"));
        process.stdout.write(cfg.sync_version || cfg.version || "");
      } catch {}
    ' "$cfg" 2>/dev/null || echo ""
    return
  fi
  grep -o '"sync_version": "[^"]*"\|"version": "[^"]*"' "$cfg" 2>/dev/null \
    | head -1 | sed 's/.*: "\(.*\)"/\1/' || echo ""
}

# Derive "org/repo" from a git remote URL (https or ssh form); empty when
# the URL has fewer than two path components.
repo_name_from_url() {
  local url="${1%/}"
  url="${url%.git}"
  printf '%s' "$url" | awk -F'[/:]' '{ if (NF >= 2 && $(NF-1) != "" && $NF != "") printf "%s/%s", $(NF-1), $NF }'
}

# Single-line structured run metadata for log analysis. Emitted with plain
# echo (not log_info) so it survives --quiet: it is telemetry, not chatter.
emit_run_metadata() {
  local user_name user_email account version repo_url repo_name branch
  user_name="$(git -C "$PROJECT_PATH" config --get user.name 2>/dev/null || echo "")"
  user_email="$(git -C "$PROJECT_PATH" config --get user.email 2>/dev/null || echo "")"
  version="$(qaf_version "$PROVIDER")"
  repo_url="$(git -C "$PROJECT_PATH" remote get-url origin 2>/dev/null || echo "")"
  repo_name="$(repo_name_from_url "$repo_url")"
  branch="$(git -C "$PROJECT_PATH" branch --show-current 2>/dev/null || echo "")"

  echo "[ensure-context] run-metadata: {\"event\":\"ensure_context\",\"ran_at\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\",\"qaf_version\":\"$(json_escape "$version")\",\"provider\":\"$PROVIDER\",\"git_user_name\":\"$(json_escape "$user_name")\",\"git_user_email\":\"$(json_escape "$user_email")\",\"repository\":\"$(json_escape "$repo_url")\",\"repository_name\":\"$(json_escape "$repo_name")\",\"branch\":\"$(json_escape "$branch")\",\"git_head\":\"$(git_head)\"}"
}

# ---------- marker reuse (early exit) ----------

# A delegated skill re-runs this preflight moments after its caller already ran
# it for the same ticket (same ARTIFACTS_DIR). When the existing marker proves
# the environment is unchanged, the full flow is redundant: re-stamp
# preflight_ran_at (keeping the original preflight_started_at for run timing)
# and exit 0. Reuse requires ALL of: no force flag, node available, marker
# version current, marker fresh (<60 min), every repo recorded in repo_heads
# still at the same HEAD, and no framework-update prompt pending — a pending
# prompt falls through so the detector re-decides against the snooze state the
# glue may have just written, instead of re-prompting for a declined or applied
# release. Anything else falls open to the full run.
#
# QAF_PREFLIGHT_ALLOW_HEAD_DRIFT=1 relaxes ONLY the repo_heads equality check,
# for a delegated skill that runs right after its caller committed (the
# /implement-ticket wiki refresh follows the implementation commit). Every
# other condition stands; the consumers that opt in derive their work from git
# diffs, so a marker whose repo_heads lag by that one commit misleads nothing.
preflight_marker_reusable() {
  local marker="$ARTIFACTS_DIR/.preflight-ok"
  [ "${QAF_PREFLIGHT_FORCE:-0}" != "1" ] || return 1
  [ -f "$marker" ] || return 1
  command -v node >/dev/null 2>&1 || return 1
  node -e '
    const fs = require("fs");
    const { execFileSync } = require("child_process");
    const [marker, project] = process.argv.slice(1);
    try {
      const m = JSON.parse(fs.readFileSync(marker, "utf-8"));
      if (m.preflight_version !== 9) process.exit(1);
      if (m.workspace_root !== project) process.exit(1);
      if (m.framework_update && m.framework_update.should_prompt === true) process.exit(1);
      const ranAt = Date.parse(m.preflight_ran_at || "");
      if (!Number.isFinite(ranAt) || Date.now() - ranAt > 60 * 60 * 1000) process.exit(1);
      const heads = m.repo_heads;
      if (!heads || typeof heads !== "object" || Object.keys(heads).length === 0) process.exit(1);
      if (process.env.QAF_PREFLIGHT_ALLOW_HEAD_DRIFT !== "1") {
        for (const [repo, head] of Object.entries(heads)) {
          const current = execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], {
            stdio: ["ignore", "pipe", "ignore"],
          }).toString().trim();
          if (!head || current !== head) process.exit(1);
        }
      }
      process.exit(0);
    } catch {
      process.exit(1);
    }
  ' "$marker" "$PROJECT_PATH" 2>/dev/null
}

# ---------- main flow ----------

PROVIDER="$(provider_name)"
log_info "provider: $PROVIDER"
log_info "project:  $PROJECT_PATH"
emit_run_metadata

if preflight_marker_reusable; then
  node -e '
    const fs = require("fs");
    const p = process.argv[1];
    const m = JSON.parse(fs.readFileSync(p, "utf-8"));
    m.preflight_ran_at = new Date().toISOString().replace(/\.\d+Z$/, "Z");
    fs.writeFileSync(p, JSON.stringify(m, null, 2) + "\n");
  ' "$ARTIFACTS_DIR/.preflight-ok" 2>/dev/null || true
  log_info "preflight: ok (reused marker at $ARTIFACTS_DIR/.preflight-ok — environment unchanged)"
  exit 0
fi

HEAD_COMMIT="$(git_head)"

# 1. Deterministic workspace topology — the single source of truth for the
# /implement-ticket phases that branch / commit / push per git repo.
# `workspace-topology.sh` only defines functions, so sourcing it has no side
# effects.
#
# Detect a colocated framework checkout solely so is_multi_repo can exclude it
# from nested-child-repo discovery. Empty when absent — _qaf_discover_children
# treats an empty exclusion as "nothing to exclude", which is correct. We do
# NOT call framework_path() here: the shipped resolve-paths.sh shim defines only
# project_path(), so framework_path() is undefined in `.claude/scripts/` installs.
detect_local_framework_dir() {
  local candidate="$PROJECT_PATH/qubika-agentic-framework"
  if [ -d "$candidate/scripts" ] && [ -f "$candidate/orchestration/package.json" ]; then
    ( cd "$candidate" && pwd )
    return 0
  fi
  echo ""
}
FRAMEWORK_PATH="$(detect_local_framework_dir)"
# shellcheck source=lib/workspace-topology.sh
source "$SCRIPT_DIR/lib/workspace-topology.sh"

# Build a JSON string array from newline-separated paths without depending on
# jq (this preflight must stay self-sufficient). Escapes \ and " per path.
json_string_array() {
  local first=1 line out="["
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    line="${line//\\/\\\\}"; line="${line//\"/\\\"}"
    if [ "$first" -eq 1 ]; then first=0; else out+=","; fi
    out+="\"$line\""
  done
  out+="]"
  printf '%s' "$out"
}

if is_multi_repo "$PROJECT_PATH" "$FRAMEWORK_PATH"; then
  WORKSPACE_MODE="multi"
  REPO_LIST="$(_qaf_discover_children "$PROJECT_PATH" "$FRAMEWORK_PATH")"
else
  WORKSPACE_MODE="single"
  # Prefer the repo toplevel; fall back to PROJECT_PATH so a rev-parse hiccup
  # can never abort an otherwise-good preflight (set -e is on).
  REPO_LIST="$( (cd "$PROJECT_PATH" && git rev-parse --show-toplevel 2>/dev/null) || printf '%s' "$PROJECT_PATH")"
fi
CHILD_REPOS_JSON="$(printf '%s\n' "$REPO_LIST" | json_string_array)"

# Per-repo HEADs, keyed by absolute repo path — what the marker-reuse check
# verifies. Built without jq (this preflight must stay self-sufficient).
json_repo_heads() {
  local first=1 line head out="{"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    head="$( (cd "$line" && git rev-parse HEAD 2>/dev/null) || echo "" )"
    line="${line//\\/\\\\}"; line="${line//\"/\\\"}"
    if [ "$first" -eq 1 ]; then first=0; else out+=","; fi
    out+="\"$line\":\"$head\""
  done
  out+="}"
  printf '%s' "$out"
}
REPO_HEADS_JSON="$(printf '%s\n' "$REPO_LIST" | json_repo_heads)"

# 2. Defense-in-depth: ignore the provider temp dirs, the per-developer tool-defaults
# override file, and the per-project framework-update snooze state file locally in
# every reachable repo (workspace root + every child repo) via .git/info/exclude —
# the UNTRACKED local ignore file. We deliberately avoid the tracked .gitignore:
# writing there would dirty the working tree and trip the clean-tree assertion.
# Even if some phase ever wrote .claude-temp into a child repo by mistake, it can
# never be staged or committed into that repo's PR. The two state files sit inside
# the committed config dir (.claude/.codex), so they are excluded by exact path
# rather than by ignoring the whole dir. Both provider variants are listed so a
# provider switch needs no re-run. Idempotent: exact-line match before append.
ensure_local_excluded() {
  local repo="$1" excl entry
  git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || return 0
  excl="$(git -C "$repo" rev-parse --git-path info/exclude 2>/dev/null)" || return 0
  [ -n "$excl" ] || return 0
  case "$excl" in /*) : ;; *) excl="$repo/$excl" ;; esac
  mkdir -p "$(dirname "$excl")" 2>/dev/null || return 0
  for entry in \
    ".claude-temp/" ".codex-temp/" \
    ".claude/.framework-defaults.local.json" ".codex/.framework-defaults.local.json" \
    ".claude/.framework-update-state.json" ".codex/.framework-update-state.json"; do
    if [ ! -f "$excl" ] || ! grep -qxF "$entry" "$excl" 2>/dev/null; then
      printf '%s\n' "$entry" >> "$excl"
    fi
  done
}
ensure_local_excluded "$PROJECT_PATH"
while IFS= read -r __repo; do
  [ -n "$__repo" ] || continue
  ensure_local_excluded "$__repo"
done <<EOF
$REPO_LIST
EOF

# 3. Remove the per-developer leftovers of the retired code-graph integration:
# the `code_graph` MCP server in `.mcp.json` and `.codex/config.toml`, and the
# `.code-review-graph/` index. A resource sync removes them on the machine that
# runs it, but they are gitignored, so a teammate who only pulls the synced
# config keeps an MCP entry whose launcher the pull deleted. Files git tracks
# are the sync's: it rewrites them and the pull delivers the result, so they
# are never touched here and the tree stays clean. Symlinked paths are kept.
# Each config file is copied to `.<provider>-backups/mcp-config/<timestamp>/`
# before it is rewritten. Fail-open: nothing here can abort the preflight.
is_untracked_local_path() {
  local rel="$1"
  [ -e "$PROJECT_PATH/$rel" ] && [ ! -L "$PROJECT_PATH/$rel" ] && [ ! -L "$PROJECT_PATH/${rel%%/*}" ] || return 1
  ! git -C "$PROJECT_PATH" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1
}

legacy_backup_dir() {
  local root="$PROJECT_PATH/.$1-backups"
  if [ -L "$root" ] || [ -L "$root/mcp-config" ]; then
    log_warn "kept $2: .$1-backups is behind a symbolic link, so it was not backed up; delete its code_graph MCP server by hand"
    return 1
  fi
  printf '%s/mcp-config/%s\n' "$root" "$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
}

remove_legacy_mcp_json_server() {
  local file="$PROJECT_PATH/.mcp.json" verdict backup
  is_untracked_local_path ".mcp.json" && grep -q '"code_graph"' "$file" 2>/dev/null || return 0
  if ! command -v node >/dev/null 2>&1; then
    log_warn ".mcp.json still registers the retired code_graph MCP server and node is unavailable to remove it; delete that entry by hand"
    return 0
  fi
  backup="$(legacy_backup_dir claude .mcp.json)" || return 0
  verdict="$(node -e '
    const fs = require("fs");
    const path = require("path");
    const [file, backupDir] = process.argv.slice(1);
    const cfg = JSON.parse(fs.readFileSync(file, "utf-8"));
    const servers = cfg && cfg.mcpServers;
    if (!servers || typeof servers !== "object" || !("code_graph" in servers)) process.exit(0);
    fs.mkdirSync(backupDir, { recursive: true });
    fs.copyFileSync(file, path.join(backupDir, ".mcp.json"));
    delete servers.code_graph;
    if (Object.keys(servers).length === 0) delete cfg.mcpServers;
    if (Object.keys(cfg).length === 0) {
      fs.unlinkSync(file);
      process.stdout.write("removed");
    } else {
      fs.writeFileSync(file, JSON.stringify(cfg, null, 2) + "\n");
      process.stdout.write("pruned");
    }
  ' "$file" "$backup" 2>/dev/null)" || verdict="failed"
  case "$verdict" in
    removed) log_info "removed .mcp.json (it held only the retired code_graph MCP server)" ;;
    pruned) log_info "dropped the retired code_graph MCP server from .mcp.json" ;;
    failed) log_warn "could not remove the retired code_graph MCP server from .mcp.json (not valid JSON?); delete that entry by hand" ;;
  esac
}

remove_legacy_codex_mcp_server() {
  local rel=".codex/config.toml" file="$PROJECT_PATH/.codex/config.toml" backup
  is_untracked_local_path "$rel" && grep -q '^[[:space:]]*\[mcp_servers\.code_graph[].]' "$file" 2>/dev/null || return 0
  backup="$(legacy_backup_dir codex "$rel")" || return 0
  mkdir -p "$backup" && cp "$file" "$backup/" || return 0
  awk '
    /^[[:space:]]*# === ai-agentic-framework/ { skip = 0 }
    /^[[:space:]]*\[/ { skip = ($0 ~ /^[[:space:]]*\[mcp_servers\.code_graph[].]/) }
    !skip
  ' "$file" > "$file.ensure-context.tmp" && cat "$file.ensure-context.tmp" > "$file" && rm -f "$file.ensure-context.tmp" || { rm -f "$file.ensure-context.tmp"; return 0; }
  log_info "dropped the retired code_graph MCP server from $rel"
}

remove_legacy_graph_index() {
  [ -d "$PROJECT_PATH/.code-review-graph" ] && is_untracked_local_path ".code-review-graph" || return 0
  rm -rf "${PROJECT_PATH:?}/.code-review-graph" && log_info "removed the retired code graph index .code-review-graph/"
}

remove_legacy_mcp_json_server || true
remove_legacy_codex_mcp_server || true
remove_legacy_graph_index || true

# 4. Resolve the level 2-4 tool-default baseline (personal → project → shipped)
# for stamping into the marker. Fail-open: a missing Node, a missing resolver,
# or any resolver failure yields the empty shape, so the preflight can never
# abort on it. Level 1 (CLI flags) is applied by the skill that reads the marker.
resolve_tool_defaults() {
  local registry="$SCRIPT_DIR/tool-defaults.json"
  local config="$PROJECT_PATH/.$PROVIDER/framework-config.json"
  local personal="$PROJECT_PATH/.$PROVIDER/.framework-defaults.local.json"
  if command -v node >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/resolve-tool-defaults.mjs" ]; then
    node "$SCRIPT_DIR/resolve-tool-defaults.mjs" \
      --registry "$registry" --config "$config" --personal "$personal" 2>/dev/null
    return 0
  fi
  printf '{"tools":{}}'
}
RESOLVED_DEFAULTS="$(resolve_tool_defaults)"
[ -n "$RESOLVED_DEFAULTS" ] || RESOLVED_DEFAULTS='{"tools":{}}'

# 5. Read-only framework-release detection. Best-effort and fail-open: the helper
# self-skips on dogfooding / non-release HEAD / git / network failure and always
# exits 0, and we still normalise anything unexpected to the skipped shape so a
# hiccup here can never abort an otherwise-good preflight (set -e is on). The
# helper is run from the framework checkout, not a shim, so it always reads the
# checkout's own upgrade-rules.json. The skill glue consumes framework_update.
#
# Opt-out (--skip-update-check flag or QAF_SKIP_UPDATE_CHECK env) short-circuits
# to the opt-out shape without touching git or the network. The per-project
# snooze state file lives beside the provider config and is git-excluded above.
#
# The installed version is resolved HERE and passed in, because only the caller
# knows which provider config holds it (`.claude/` vs `.codex/`). It is what the
# project actually runs — the detector decides against it rather than against
# whatever tag the framework checkout happens to sit on, which drifts the moment
# someone pulls the checkout without re-syncing.
UPDATE_STATE_FILE="$PROJECT_PATH/.$PROVIDER/.framework-update-state.json"

# The skipped shape of check-framework-update.sh, for the paths that never reach
# the script. Mirrors its output contract field for field.
framework_update_skipped() {
  printf '{"update_available":false,"installed":null,"checkout":null,"latest":null,"action":"none","should_prompt":false,"migrations":[],"reason":"%s","release_notes_url":null}' "$1"
}

FRAMEWORK_UPDATE_JSON=""
__opt_out=0
[ "$SKIP_UPDATE_CHECK" -eq 1 ] && __opt_out=1
case "${QAF_SKIP_UPDATE_CHECK:-}" in "" | 0 | false | no) : ;; *) __opt_out=1 ;; esac
if [ "$__opt_out" -eq 1 ]; then
  FRAMEWORK_UPDATE_JSON="$(framework_update_skipped "opt-out")"
elif [ -n "$FRAMEWORK_PATH" ] && [ -f "$FRAMEWORK_PATH/scripts/check-framework-update.sh" ]; then
  FRAMEWORK_UPDATE_JSON="$(bash "$FRAMEWORK_PATH/scripts/check-framework-update.sh" \
    --framework-path "$FRAMEWORK_PATH" --project-path "$PROJECT_PATH" \
    --installed-version "$(qaf_version "$PROVIDER")" \
    --state-file "$UPDATE_STATE_FILE" 2>/dev/null || true)"
fi
case "$FRAMEWORK_UPDATE_JSON" in
  '{'*'}') : ;;
  *) FRAMEWORK_UPDATE_JSON="$(framework_update_skipped "check-unavailable")" ;;
esac

# 6. Success marker. Wiki staleness is not reflected here; /wiki-refresh checks
# the wiki `.state.json` directly.
mkdir -p "$ARTIFACTS_DIR"
cat > "$ARTIFACTS_DIR/.preflight-ok" << EOF
{
  "git_head": "$HEAD_COMMIT",
  "provider": "$PROVIDER",
  "workspace_root": "$PROJECT_PATH",
  "artifacts_dir": "$ARTIFACTS_DIR",
  "workspace_mode": "$WORKSPACE_MODE",
  "child_repos": $CHILD_REPOS_JSON,
  "repo_heads": $REPO_HEADS_JSON,
  "framework_update": $FRAMEWORK_UPDATE_JSON,
  "resolved_defaults": $RESOLVED_DEFAULTS,
  "preflight_started_at": "$PREFLIGHT_STARTED_AT",
  "preflight_ran_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "preflight_version": 9
}
EOF

log_info "preflight: ok (marker at $ARTIFACTS_DIR/.preflight-ok)"
