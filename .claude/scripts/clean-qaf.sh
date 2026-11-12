#!/bin/bash
# ============================================================================
# CLEAN-QAF — remove every framework-generated artifact from a project
# ============================================================================
#
# Returns a project to its pre-`initialize-project` state so the next
# initialization starts from a clean slate. Backs up everything it removes
# first, so a mistaken run is one command away from being undone.
#
# Usage (engineer projects — no framework checkout required):
#   bash <project>/.claude/scripts/clean-qaf.sh [options]
#
# Usage (framework checkout present):
#   ./qubika-agentic-framework/scripts/clean-qaf.sh [options]
#
# What it removes:
#   - Framework-owned entries inside .claude/ and .codex/: the instruction
#     file, framework-config.json, .framework-update-state.json, scripts/,
#     the skills/agents recorded as framework-managed in
#     framework-config.json's `resource_state`, and the skills/agents the
#     framework has since retired (see RETIRED_SKILL_NAMES) — those are removed
#     on sight, since no record still names them. The config dir itself is
#     removed only when nothing else is left in it.
#   - .claude-temp/ .codex-temp/
#   - docs/llm-wiki/ (and docs/ when it becomes empty)
#   - .code-review-graph/ and .code-review-graphignore
#
# What it prunes surgically (these files are shared with the engineer):
#   - .mcp.json           → drops the `code_graph` server; deletes the file
#                           when no other server or key survives.
#   - .codex/config.toml  → drops [mcp_servers.code_graph] and the managed
#                           codex-hooks block; deletes the file when empty.
#   - .gitignore          → drops the entries preflight added; deletes the
#                           file when empty.
#
# `--provider claude|codex` narrows every list above to that provider's
# artifacts, which is how `initialize-project.sh` invokes it: a run initializing
# for Codex must not archive and delete a co-installed Claude installation on
# its behalf. A provider-scoped run also leaves the artifacts both providers
# read — docs/llm-wiki/ and the root .gitignore block — in place whenever the
# OTHER provider's installation survives it. `.code-review-graph/`,
# `.code-review-graphignore` and the `code_graph` MCP entries are read by no
# provider, so every run removes them, scoped or not.
#
# A clean never destroys a backup. `.claude-backups/` (`.codex-backups/` on a
# Codex-only project) is where `sync-framework-resources` already stores the
# skills and agents it is about to overwrite, so it is the store this archive
# belongs in rather than a second one — and it is why those directories are NOT
# in the removal list above. An engineer whose clean turns out to be a mistake
# needs that history intact, which is the whole point of the archive.
#
# Archives land at `<backups-dir>/clean-qaf/<timestamp>-NN.tar.gz`, inside a
# self-ignoring directory (its own `.gitignore` is a bare `*`) so a tarball of
# your `.claude/` can never be committed by accident — the root `.gitignore`
# cannot be relied on for it, because this script prunes that file. Set
# QAF_BACKUP_HOME to keep archives outside the project, where they survive
# deleting it.
#
# What it never touches:
#   - Engineer-owned config: settings.json, settings.local.json, commands/,
#     rules/, credentials, and any skill or agent not recorded as
#     framework-managed.
#   - `.claude-backups/` / `.codex-backups/` — every backup, its own included.
#   - The qubika-agentic-framework/ checkout (use --include-framework).
#   - Machine-wide tooling (uv, a code-review-graph install): removing it is
#     the engineer's call (`uv tool uninstall code-review-graph`).
#
# Exit codes:
#   0  – cleaned, or nothing to clean, or dry run completed. Under --check:
#        this project carries framework artifacts.
#   1  – aborted by the user. Under --check: nothing to clean.
#   2  – bad usage.
#   3  – could not resolve a project to clean.
#   4  – backup failed (nothing was removed).
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

SELF_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SELF_PATH")"
ORIGINAL_ARGS=("$@")

if [ -f "$SCRIPT_DIR/lib/resolve-paths.sh" ]; then
    # shellcheck source=lib/resolve-paths.sh
    source "$SCRIPT_DIR/lib/resolve-paths.sh"
fi

DEFAULT_FRAMEWORK_DIR_NAME="qubika-agentic-framework"
CLEAN_ARCHIVE_SUBDIR="clean-qaf"

# Resources the framework used to install and has since retired. They are in no
# other record this script can read: a retired name is gone from the checkout's
# `skills/` tree, gone from the run manifest of any later initialization, and
# never added to `framework-config.json` on installations old enough to predate
# the inventory — so without this list they outlive every clean.
#
# `sync-framework-resources` deletes them from disk regardless of what the
# inventory claims (`orchestration/src/services/framework/legacy-skills.ts`),
# and these arrays are the same decision on the clean side. A unit test binds
# them to that module so the two cannot drift.
RETIRED_SKILL_NAMES=(
    "code-conventions"
    "multi-file-workflows"
    "testing-conventions"
)
RETIRED_AGENT_NAMES=()

show_help() {
    cat << EOF
${CYAN}Qubika Agentic Framework — clean-qaf${NC}

${BLUE}USAGE:${NC}
    clean-qaf.sh [OPTIONS]

${BLUE}OPTIONS:${NC}
    --dry-run             Show exactly what would be removed and exit.
    -y, --yes             Skip the confirmation prompt (required for CI).
    --no-backup           Do not archive before removing.
    --keep-config         Preserve <config-dir>/framework-config.json, so the
                          next initialization carries your team's tool defaults
                          forward instead of reseeding the shipped ones.
    --check               Quiet probe for other scripts: exit 0 when this
                          project carries framework artifacts, 1 when it does
                          not. Prints nothing and changes nothing.
    --include-framework   Also remove the ${DEFAULT_FRAMEWORK_DIR_NAME}/ checkout.
                          A re-initialization then needs a fresh git clone.
    --provider PROVIDER   Clean only one provider's artifacts: claude or codex.
                          Default: every provider installed in the project.
                          Shared artifacts (docs/llm-wiki/, the .gitignore
                          block) survive when the other provider's installation
                          does.
    --project PATH        Project to clean. Default: auto-resolved from this
                          script's location (or \$PROJECT_PATH).
    --list                List this project's backups and exit.
    --restore [ID]        Restore a backup (ID from --list, or "latest") into
                          the project and exit. Overwrites current files.
    -h, --help            Show this help.

${BLUE}BACKUPS:${NC}
    Archives are written inside the project, to
    .claude-backups/clean-qaf/<timestamp>-NN.tar.gz
    (.codex-backups/ on a Codex-only project, or under --provider codex)

    That is the same store sync-framework-resources already uses for the
    resources it overwrites, and a clean never removes it: backups survive,
    including this one, so repeated cleans stack instead of eating the previous
    archive. The archive directory also ignores itself in Git (its own
    .gitignore is a bare asterisk), since the root .gitignore is a file this
    script prunes. Set \$QAF_BACKUP_HOME to put archives outside the project,
    where they outlive deleting it.

${BLUE}EXAMPLES:${NC}
    # See what would go, change nothing
    bash .claude/scripts/clean-qaf.sh --dry-run

    # Clean, then re-initialize from scratch
    bash .claude/scripts/clean-qaf.sh -y
    ./${DEFAULT_FRAMEWORK_DIR_NAME}/scripts/initialize-project.sh

    # Undo the last clean — from the framework checkout, because this script's
    # shipped copy under <config-dir>/scripts/ is one of the things a clean
    # removes. With no checkout, extract the archive directly:
    #   tar -xzf <archive> -C <project>
    ./qubika-agentic-framework/scripts/clean-qaf.sh --restore latest

EOF
}

# ============================================================================
# ARGUMENT PARSING
# ============================================================================

DRY_RUN=0
ASSUME_YES=0
DO_BACKUP=1
KEEP_CONFIG=0
INCLUDE_FRAMEWORK=0
PROJECT_PATH_ARG=""
MODE="clean"
RESTORE_ID=""
PROVIDER=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        --no-backup) DO_BACKUP=0; shift ;;
        --keep-config) KEEP_CONFIG=1; shift ;;
        --check) MODE="check"; shift ;;
        --include-framework) INCLUDE_FRAMEWORK=1; shift ;;
        --provider) PROVIDER="${2:-}"; shift 2 ;;
        --provider=*) PROVIDER="${1#*=}"; shift ;;
        --project) PROJECT_PATH_ARG="${2:-}"; shift 2 ;;
        --project=*) PROJECT_PATH_ARG="${1#*=}"; shift ;;
        --list) MODE="list"; shift ;;
        --restore)
            MODE="restore"
            case "${2:-}" in
                ""|-*) RESTORE_ID="latest"; shift ;;
                *) RESTORE_ID="$2"; shift 2 ;;
            esac
            ;;
        --restore=*) MODE="restore"; RESTORE_ID="${1#*=}"; shift ;;
        -h|--help) show_help; exit 0 ;;
        *)
            echo -e "${RED}[clean-qaf] unknown argument: $1${NC}" >&2
            echo "Run with --help for usage." >&2
            exit 2 ;;
    esac
done

case "$PROVIDER" in
    ""|claude|codex) ;;
    *)
        echo -e "${RED}[clean-qaf] --provider must be 'claude' or 'codex' (got '$PROVIDER')${NC}" >&2
        exit 2 ;;
esac

# ============================================================================
# PROVIDER SCOPE
# ============================================================================

# Whether `$1` is a provider this run is allowed to touch. With no --provider
# every provider is in scope, which is what a standalone "revert this project"
# run means.
provider_in_scope() {
    [ -z "$PROVIDER" ] || [ "$PROVIDER" = "$1" ]
}

# The provider dir names, keyed by provider. Kept next to `provider_in_scope`
# so the shell side of the framework has one place stating them, mirroring
# `orchestration/src/utils/provider-paths.ts`.
provider_config_dir() { printf '%s\n' ".$1"; }
provider_temp_dir() { printf '%s\n' ".$1-temp"; }
provider_backup_dir() { printf '%s\n' ".$1-backups"; }
provider_instruction_file() {
    case "$1" in
        claude) printf '%s\n' "CLAUDE.md" ;;
        codex) printf '%s\n' "AGENTS.md" ;;
    esac
}

# ============================================================================
# PROJECT RESOLUTION
# ============================================================================

# Resolve the project root: an explicit --project wins, then $PROJECT_PATH,
# then the canonical resolver that ships next to this script in both of its
# homes (`<framework>/scripts/lib/` and `<project>/.claude/scripts/lib/`).
resolve_project() {
    if [ -n "$PROJECT_PATH_ARG" ]; then
        if [ ! -d "$PROJECT_PATH_ARG" ]; then
            echo -e "${RED}[clean-qaf] --project path does not exist: $PROJECT_PATH_ARG${NC}" >&2
            exit 3
        fi
        ( cd "$PROJECT_PATH_ARG" && pwd )
        return
    fi
    if [ -n "${PROJECT_PATH:-}" ] && [ -d "${PROJECT_PATH}" ]; then
        ( cd "$PROJECT_PATH" && pwd )
        return
    fi
    if command -v project_path > /dev/null 2>&1; then
        project_path
        return
    fi
    echo -e "${RED}[clean-qaf] cannot resolve the project root${NC}" >&2
    echo "Pass it explicitly: clean-qaf.sh --project /path/to/project" >&2
    exit 3
}

PROJECT_PATH="$(resolve_project)"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
# The provider's own backup store.
#
# An explicit --provider settles it outright: that run only ever archives that
# provider's artifacts, so they belong in that provider's store even on a
# project whose other provider already has one.
#
# Otherwise an archive directory that already exists wins over detection, and
# that ordering is load-bearing: detection reads `.claude/` / `.codex/`, which
# are directories a clean REMOVES. Deriving the store again on a later
# `--list` or `--restore` would then answer differently than the run that wrote
# the archive — on a Codex-only project the undo path looked in
# `.claude-backups/` while the tarball sat in `.codex-backups/`, and reported
# "no such backup: latest" with the archive intact on disk. Preferring an
# existing store also keeps repeated cleans stacking in one place on a project
# whose provider dirs come and go.
resolve_provider_backup_dir() {
    local candidate
    if [ -n "$PROVIDER" ]; then
        provider_backup_dir "$PROVIDER"
        return
    fi
    for candidate in ".claude-backups" ".codex-backups"; do
        if [ -d "$PROJECT_PATH/$candidate/$CLEAN_ARCHIVE_SUBDIR" ]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    if command -v provider_name > /dev/null 2>&1; then
        provider_backup_dir "$(provider_name)"
        return
    fi
    if [ -d "$PROJECT_PATH/.codex" ] && [ ! -d "$PROJECT_PATH/.claude" ]; then
        printf '%s\n' ".codex-backups"
    else
        printf '%s\n' ".claude-backups"
    fi
}

PROVIDER_BACKUP_DIR="$(resolve_provider_backup_dir)"
IN_PROJECT_BACKUP_DIR="$PROVIDER_BACKUP_DIR/$CLEAN_ARCHIVE_SUBDIR"

BACKUP_HOME="${QAF_BACKUP_HOME:-}"
if [ -n "$BACKUP_HOME" ]; then
    BACKUP_DIR="$BACKUP_HOME/$PROJECT_NAME"
else
    BACKUP_DIR="$PROJECT_PATH/$IN_PROJECT_BACKUP_DIR"
fi

# ============================================================================
# SELF-RELOCATION
# ============================================================================

# The shipped copy of this script lives inside a directory it is about to
# delete, and bash reads a script incrementally — deleting it mid-run would
# truncate execution. Re-exec from a temp copy before touching anything.
relocate_if_inside_target() {
    case "$SELF_PATH" in
        "$PROJECT_PATH"/.claude/*|"$PROJECT_PATH"/.codex/*) ;;
        *) return 0 ;;
    esac
    local staging
    staging="$(mktemp -d "${TMPDIR:-/tmp}/clean-qaf.XXXXXX")"
    cp "$SELF_PATH" "$staging/clean-qaf.sh"
    if [ -f "$SCRIPT_DIR/lib/resolve-paths.sh" ]; then
        mkdir -p "$staging/lib"
        cp "$SCRIPT_DIR/lib/resolve-paths.sh" "$staging/lib/resolve-paths.sh"
    fi
    chmod +x "$staging/clean-qaf.sh"
    QAF_CLEAN_RELOCATED=1 \
    QAF_CLEAN_STAGING="$staging" \
    PROJECT_PATH="$PROJECT_PATH" \
        exec bash "$staging/clean-qaf.sh" "${ORIGINAL_ARGS[@]+"${ORIGINAL_ARGS[@]}"}"
}

if [ -z "${QAF_CLEAN_RELOCATED:-}" ]; then
    relocate_if_inside_target
elif [ -n "${QAF_CLEAN_STAGING:-}" ]; then
    trap 'rm -rf "$QAF_CLEAN_STAGING"' EXIT
fi

# ============================================================================
# BACKUP MODES
# ============================================================================

# Backup ids are the archive basenames, so `--list` output feeds `--restore`
# verbatim.
list_backups() {
    [ -d "$BACKUP_DIR" ] || return 0
    ls -1 "$BACKUP_DIR" 2>/dev/null | grep '\.tar\.gz$' | sed 's/\.tar\.gz$//' | sort
}

# An archive id that is free on disk. The stamp resolves to the second, and two
# cleans inside one second are reachable — a failed initialization retried
# immediately runs the cleaner twice — so the id always carries a sequence
# suffix rather than risking one run overwriting the safety net of the one
# before it.
#
# The suffix is unconditional, not just on collision: `-` sorts before `.`, so a
# bare `<stamp>.tar.gz` would sort AFTER `<stamp>-02.tar.gz` and `--restore
# latest` (`tail -1`) would hand back the older of the two. With every id the
# same shape, the lexicographic order `--list` and `latest` rely on is
# chronological again.
next_archive_id() {
    local stamp n=1
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    while [ -e "$BACKUP_DIR/$(printf '%s-%02d' "$stamp" "$n").tar.gz" ]; do
        n=$((n + 1))
    done
    printf '%s-%02d\n' "$stamp" "$n"
}

# Where archives go, for the messages that name it. Relative inside the project
# (it is the common case and shorter to read), absolute when overridden.
backup_location() {
    if [ -z "$BACKUP_HOME" ]; then
        printf '%s\n' "$IN_PROJECT_BACKUP_DIR"
    else
        printf '%s\n' "$BACKUP_DIR"
    fi
}

run_list_mode() {
    local ids
    ids="$(list_backups)"
    if [ -z "$ids" ]; then
        echo -e "${YELLOW}No clean-qaf backups for $PROJECT_NAME${NC}"
        echo -e "${DIM}Looked in: $BACKUP_DIR${NC}"
        return 0
    fi
    echo -e "${CYAN}clean-qaf backups for $PROJECT_NAME${NC}  ${DIM}($BACKUP_DIR)${NC}"
    local id size
    while IFS= read -r id; do
        size="$(du -h "$BACKUP_DIR/$id.tar.gz" 2>/dev/null | cut -f1)"
        echo "  $id  ${size:-?}"
    done <<< "$ids"
    echo ""
    echo -e "${DIM}Restore with: clean-qaf.sh --restore <id>${NC}"
}

run_restore_mode() {
    local id="$RESTORE_ID"
    if [ "$id" = "latest" ]; then
        id="$(list_backups | tail -1)"
    fi
    if [ -z "$id" ] || [ ! -f "$BACKUP_DIR/$id.tar.gz" ]; then
        echo -e "${RED}[clean-qaf] no such backup: ${RESTORE_ID}${NC}" >&2
        echo -e "${DIM}Available:${NC}" >&2
        list_backups >&2 || true
        exit 2
    fi
    local archive="$BACKUP_DIR/$id.tar.gz"
    echo -e "${CYAN}Restoring $id into $PROJECT_PATH${NC}"
    echo -e "${YELLOW}Files present in the archive overwrite their current versions.${NC}"
    if [ "$ASSUME_YES" -eq 0 ]; then
        if [ ! -t 0 ]; then
            echo -e "${RED}[clean-qaf] refusing to restore unattended without --yes${NC}" >&2
            exit 1
        fi
        printf "Continue? [y/N] "
        local reply
        read -r reply
        case "$reply" in
            y|Y|yes|YES) ;;
            *) echo "Aborted."; exit 1 ;;
        esac
    fi
    tar -xzf "$archive" -C "$PROJECT_PATH"
    echo -e "${GREEN}✓ Restored from $archive${NC}"
}

case "$MODE" in
    list) run_list_mode; exit 0 ;;
    restore) run_restore_mode; exit 0 ;;
esac

# ============================================================================
# FRAMEWORK CHECKOUT
# ============================================================================

# The checkout's directory name drives both its own removal and the
# `.gitignore` entry preflight added for it. Prefer the real one on disk over
# the conventional name so a renamed clone is still matched.
detect_framework_dir_name() {
    local candidate
    for candidate in "$PROJECT_PATH"/*/; do
        [ -d "$candidate" ] || continue
        if [ -f "$candidate/scripts/initialize-project.sh" ] && [ -f "$candidate/orchestration/package.json" ]; then
            basename "${candidate%/}"
            return 0
        fi
    done
    printf '%s\n' "$DEFAULT_FRAMEWORK_DIR_NAME"
}

# The framework checkout this run can read, or nothing. Two homes answer: the
# script's own, when it is the framework's copy (`<framework>/scripts/`), and
# the clone inside the project, which is where the copy shipped into
# `<config-dir>/scripts/` finds it.
framework_checkout_path() {
    local candidate
    for candidate in "$SCRIPT_DIR/.." "$PROJECT_PATH/$(detect_framework_dir_name)"; do
        if [ -f "$candidate/scripts/initialize-project.sh" ] \
            && [ -f "$candidate/orchestration/package.json" ]; then
            ( cd "$candidate" && pwd )
            return 0
        fi
    done
    return 1
}

# The skill (or agent) names the framework checkout can install.
#
# Skills are the directory names under `skills/<NNN-category>/`. Agents are the
# stems of `agents/templates/<stem>.template.md`: each template renders exactly
# one agent of the same name.
framework_shipped_names() {
    local kind="$1"
    local fw
    fw="$(framework_checkout_path)" || return 1
    case "$kind" in
        skills)
            [ -d "$fw/skills" ] || return 1
            find "$fw/skills" -mindepth 2 -maxdepth 2 -type d -exec basename {} \; 2>/dev/null
            ;;
        agents)
            [ -d "$fw/agents/templates" ] || return 1
            local template
            for template in "$fw"/agents/templates/*.template.md; do
                [ -f "$template" ] || continue
                basename "$template" .template.md
            done
            ;;
    esac
}

# ============================================================================
# INVENTORY
# ============================================================================

TARGETS=()
NOTES=()

# Record a project-relative path for removal when it exists on disk AND resolves
# inside the project.
#
# The containment check is not paranoia about our own literals: the skills and
# agents entries are built from `framework-config.json` keys, and that file is
# committed — so it travels with the repo, and `initialize-project.sh --clean`
# feeds it to this script automatically. A key holding `../` would otherwise
# make `rm -rf` delete whatever it points at, on every machine that cleans.
# `managed_resource_names` rejects such names at the source; this is the second
# line, so a future caller cannot reintroduce the hole by adding a target from
# somewhere else.
add_target() {
    local rel="$1"
    local candidate="$PROJECT_PATH/$rel"
    if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then
        return 0
    fi
    if ! resolves_inside_project "$candidate"; then
        NOTES+=("refused to target '$rel' — it resolves outside the project")
        return 0
    fi
    TARGETS+=("$rel")
}

# True when `$1` resolves to the project root or something beneath it. Resolves
# the parent physically (`pwd -P`) so a `../` segment or a symlinked parent
# cannot smuggle the path out of the tree.
resolves_inside_project() {
    local candidate="$1"
    local parent base root
    parent="$(cd "$(dirname "$candidate")" 2>/dev/null && pwd -P)" || return 1
    base="$(basename "$candidate")"
    root="$(cd "$PROJECT_PATH" 2>/dev/null && pwd -P)" || return 1
    case "$parent/$base" in
        "$root"/*) return 0 ;;
        *) return 1 ;;
    esac
}

# Names of the skills (or agents) `framework-config.json` records as
# framework-managed. A resource the engineer opted out of with
# `managed_by_framework: false` is deliberately excluded — it is theirs now.
#
# A name is a single directory entry, never a path: anything carrying a
# separator, or `.` / `..`, is dropped. The file is committed, so it is
# attacker- and corruption-reachable, and every name here is concatenated onto
# the config dir and handed to `rm -rf`.
managed_resource_names() {
    local config_file="$1"
    local kind="$2"
    command -v node > /dev/null 2>&1 || return 1
    [ -f "$config_file" ] || return 1
    node -e '
const fs = require("fs");
const [file, kind] = process.argv.slice(1);
try {
  const cfg = JSON.parse(fs.readFileSync(file, "utf8"));
  const bucket = (cfg.resource_state || {})[kind] || {};
  for (const [name, meta] of Object.entries(bucket)) {
    if (!name) continue;
    if (meta && meta.managed_by_framework === false) continue;
    if (name.includes("/") || name.includes("\\") || name === "." || name === "..") {
      process.stdout.write("!" + name + "\n");
      continue;
    }
    process.stdout.write(name + "\n");
  }
} catch {
  process.exit(1);
}
' "$config_file" "$kind" 2>/dev/null || return 1
}

# Names of the skills (or agents) the framework's own run manifest records
# writing under `$2` (a project-relative directory prefix such as
# `.codex/skills/`).
#
# `initialize-project` writes `<temp-dir>/managed-artifacts.json` in the same
# phase that installs the resources — it is the framework's record of what IT
# created, kept so later validation can scope itself to framework-owned files.
# That makes it the one source that still answers correctly when
# `framework-config.json`'s inventory does not, and it is exact: no name
# matching, no guessing which directory looks framework-shaped.
#
# Only entries exactly one segment below the prefix are returned, and the `.md`
# suffix agents carry is stripped so both sources hand back the same shape.
managed_artifact_names() {
    local manifest="$1"
    local prefix="$2"
    local kind="$3"
    command -v node > /dev/null 2>&1 || return 1
    [ -f "$manifest" ] || return 1
    node -e '
const fs = require("fs");
const [file, prefix, kind] = process.argv.slice(1);
try {
  const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!parsed || !Array.isArray(parsed.paths)) process.exit(1);
  for (const entry of parsed.paths) {
    if (typeof entry !== "string" || !entry.startsWith(prefix)) continue;
    let name = entry.slice(prefix.length);
    if (kind === "agents" && name.endsWith(".md")) name = name.slice(0, -3);
    if (!name || name.includes("/") || name.includes("\\") || name === "." || name === "..") {
      continue;
    }
    process.stdout.write(name + "\n");
  }
} catch {
  process.exit(1);
}
' "$manifest" "$prefix" "$kind" 2>/dev/null || return 1
}

# Targets for the retired resources still sitting under `<config-dir>/<kind>/`.
#
# Removal here does not consult the inventory. A retired name is one the
# framework itself shipped and later dropped, so nothing else on the machine
# still claims it: not the checkout, not a run manifest, and not a
# `framework-config.json` written before the inventory existed. Leaving it to a
# record means leaving it on disk forever. `sync-framework-resources` retires
# the same names on the same terms.
add_retired_targets() {
    local config_dir="$1"
    local kind="$2"
    local names=() found=() name rel
    case "$kind" in
        skills)
            [ "${#RETIRED_SKILL_NAMES[@]}" -gt 0 ] || return 0
            names=("${RETIRED_SKILL_NAMES[@]}")
            ;;
        agents)
            [ "${#RETIRED_AGENT_NAMES[@]}" -gt 0 ] || return 0
            names=("${RETIRED_AGENT_NAMES[@]}")
            ;;
        *) return 0 ;;
    esac

    for name in "${names[@]}"; do
        if [ "$kind" = "agents" ]; then
            rel="$config_dir/$kind/$name.md"
        else
            rel="$config_dir/$kind/$name"
        fi
        [ -e "$PROJECT_PATH/$rel" ] || continue
        add_target "$rel"
        found+=("$name")
    done

    if [ "${#found[@]}" -gt 0 ]; then
        NOTES+=("$config_dir/$kind: ${found[*]} — retired framework $kind, removed even though no inventory still names them")
    fi
}

# True when `$1` (project-relative) is a directory holding at least one entry.
dir_has_entries() {
    local dir="$PROJECT_PATH/$1"
    [ -d "$dir" ] || return 1
    local entry
    for entry in "$dir"/* "$dir"/.[!.]*; do
        [ -e "$entry" ] && return 0
    done
    return 1
}

# Framework-owned entries inside one provider config dir. `skills/` and
# `agents/` hold engineer-authored resources in many projects, so they are
# pruned per resource rather than wholesale, from whichever record of what the
# framework installed can still answer:
#
#   1. `framework-config.json`'s `resource_state` — the committed inventory, and
#      the only one that carries a `managed_by_framework: false` opt-out.
#   2. What the framework itself installs — its run manifest
#      (`<temp-dir>/managed-artifacts.json`, exact, and aware of resources a
#      later framework version renamed away) unioned with the skills and agent
#      templates the checkout ships. Used when the config records nothing or
#      cannot be read. A config claiming the framework manages nothing while the
#      directory is full of its resources is not "the engineer owns all of
#      this": it is an installation old enough to predate the inventory, or one
#      whose initialization stopped before the phase that records it. Both still
#      clean, instead of silently removing nothing.
#   3. Neither — the whole directory goes, engineer-authored resources included,
#      and the run says so out loud before asking for confirmation.
#
# The one case that removes nothing is an empty inventory on a project with no
# manifest AND no framework checkout to read: which directories the framework
# put there is not a question to answer by guessing when the answer feeds
# `rm -rf`.
#
# `--keep-config` spares `framework-config.json` itself. Both records are read
# before anything is removed, so keeping it changes what survives, never what
# this can see.
collect_config_dir_targets() {
    local config_dir="$1"
    local instruction_file="$2"
    [ -d "$PROJECT_PATH/$config_dir" ] || return 0

    add_target "$config_dir/$instruction_file"
    if [ "$KEEP_CONFIG" -eq 0 ]; then
        add_target "$config_dir/framework-config.json"
    fi
    add_target "$config_dir/.framework-update-state.json"
    add_target "$config_dir/scripts"

    local config_file="$PROJECT_PATH/$config_dir/framework-config.json"
    local manifest="$PROJECT_PATH/$(provider_temp_dir "${config_dir#.}")/managed-artifacts.json"
    local kind names name recorded
    for kind in skills agents; do
        [ -d "$PROJECT_PATH/$config_dir/$kind" ] || continue

        if names="$(managed_resource_names "$config_file" "$kind")"; then
            recorded="config"
        else
            recorded="unreadable"
            names=""
        fi

        if [ -z "$names" ]; then
            names="$(
                {
                    managed_artifact_names "$manifest" "$config_dir/$kind/" "$kind" || true
                    framework_shipped_names "$kind" || true
                } | sort -u
            )"
            if [ -n "$names" ]; then
                NOTES+=("$config_dir/framework-config.json records no framework-managed $kind — using what the framework itself installs instead, so a config that predates the inventory still cleans")
                recorded="fallback"
            fi
        fi

        if [ -z "$names" ] && [ "$recorded" = "unreadable" ]; then
            add_target "$config_dir/$kind"
            NOTES+=("$config_dir/$kind: no resource inventory found — removing the whole directory, engineer-authored $kind included")
            continue
        fi

        add_retired_targets "$config_dir" "$kind"

        if [ -z "$names" ]; then
            if dir_has_entries "$config_dir/$kind"; then
                NOTES+=("$config_dir/$kind/ holds resources no record claims and no framework checkout is available to name them — nothing there is removed")
            fi
            continue
        fi

        while IFS= read -r name; do
            [ -n "$name" ] || continue
            case "$name" in
                '!'*)
                    NOTES+=("$config_dir/framework-config.json lists '${name#!}' under $kind — not a plain directory entry, ignored")
                    continue
                    ;;
            esac
            if [ "$kind" = "agents" ]; then
                add_target "$config_dir/$kind/$name.md"
            else
                add_target "$config_dir/$kind/$name"
            fi
        done <<< "$names"
    done
}

for __provider in claude codex; do
    if provider_in_scope "$__provider"; then
        collect_config_dir_targets \
            "$(provider_config_dir "$__provider")" \
            "$(provider_instruction_file "$__provider")"
        add_target "$(provider_temp_dir "$__provider")"
    fi
done
unset __provider

# Whether a framework installation for the provider this run is NOT cleaning is
# present. The marker is a framework-written artifact inside the config dir, not
# the dir itself: any repo someone once opened Claude Code in carries a
# `.claude/` holding their local settings, and that is not an installation.
# Same rule as `getInstalledProviders` in provider-paths.ts.
other_provider_installed() {
    [ -n "$PROVIDER" ] || return 1
    local other config_dir
    case "$PROVIDER" in
        claude) other="codex" ;;
        codex) other="claude" ;;
    esac
    config_dir="$PROJECT_PATH/$(provider_config_dir "$other")"
    [ -d "$config_dir" ] || return 1
    [ -f "$config_dir/framework-config.json" ] \
        || [ -f "$config_dir/$(provider_instruction_file "$other")" ]
}

# The wiki and the root `.gitignore` block are written once and read by
# whichever providers are installed. A provider-scoped run leaves them alone
# while the other provider's installation still needs them — deleting the wiki
# on behalf of a Codex initialization would silently break the co-installed
# Claude one, and re-initializing regenerates them anyway.
SHARED_IN_SCOPE=1
if other_provider_installed; then
    SHARED_IN_SCOPE=0
    NOTES+=("keeping docs/llm-wiki/ and the .gitignore block — the other provider's installation still reads them")
fi

if [ "$SHARED_IN_SCOPE" -eq 1 ]; then
    add_target "docs/llm-wiki"
fi

# `.code-review-graph/` and `.code-review-graphignore` are read by no provider,
# so every run removes them, scoped or not.
add_target ".code-review-graph"
add_target ".code-review-graphignore"

# ============================================================================
# FRAMEWORK CHECKOUT
# ============================================================================

FRAMEWORK_DIR_NAME="$(detect_framework_dir_name)"
FRAMEWORK_PRESENT=0
if [ -d "$PROJECT_PATH/$FRAMEWORK_DIR_NAME" ]; then
    FRAMEWORK_PRESENT=1
fi

if [ "$INCLUDE_FRAMEWORK" -eq 1 ] && [ "$FRAMEWORK_PRESENT" -eq 1 ]; then
    TARGETS+=("$FRAMEWORK_DIR_NAME")
fi

# ============================================================================
# SHARED FILES TO PRUNE
# ============================================================================

GITIGNORE_MANAGED_ENTRIES=()
for __provider in claude codex; do
    if provider_in_scope "$__provider"; then
        GITIGNORE_MANAGED_ENTRIES+=("$(provider_temp_dir "$__provider")")
    fi
done
unset __provider
# The Codex MCP config is per-developer and ignored by the framework's
# root-gitignore requirements, so its rule belongs to the Codex scope.
if provider_in_scope "codex"; then
    GITIGNORE_MANAGED_ENTRIES+=(".codex/config.toml")
fi
# An entry whose directory this run leaves in place keeps its ignore rule:
# un-ignoring a directory that is still there would only fill `git status` with
# its contents. Same rule the framework checkout gets below. `.code-review-graph`
# is on the list so an installation that still ignores it loses the rule along
# with the directory.
#
# The question is answered from the PLAN, not from the disk. This list is built
# before anything is removed, so `[ -d ... ]` alone would say every target still
# exists and no rule would ever be pruned.
survives_this_run() {
    local rel="$1"
    [ -d "$PROJECT_PATH/$rel" ] || return 1
    local target
    for target in "${TARGETS[@]+"${TARGETS[@]}"}"; do
        [ "$target" = "$rel" ] && return 1
    done
    return 0
}

# A backup store belongs to one provider, so a provider-scoped run has no say
# over the other one's rule. The store this run archives INTO is skipped
# outright: it exists once the backup is written even on a project that had
# none, so its rule is one this run creates the need for rather than one it can
# drop.
for __managed_dir in ".claude-backups" ".codex-backups" ".code-review-graph"; do
    case "$__managed_dir" in
        ".claude-backups") provider_in_scope "claude" || continue ;;
        ".codex-backups") provider_in_scope "codex" || continue ;;
    esac
    if [ "$DO_BACKUP" -eq 1 ] && [ -z "$BACKUP_HOME" ] && [ "$__managed_dir" = "$PROVIDER_BACKUP_DIR" ]; then
        continue
    fi
    if ! survives_this_run "$__managed_dir"; then
        GITIGNORE_MANAGED_ENTRIES+=("$__managed_dir")
    fi
done
unset __managed_dir
GITIGNORE_DROP_HEADER=0
if [ "$FRAMEWORK_PRESENT" -eq 0 ] || [ "$INCLUDE_FRAMEWORK" -eq 1 ]; then
    GITIGNORE_MANAGED_ENTRIES+=("$FRAMEWORK_DIR_NAME")
    GITIGNORE_DROP_HEADER=1
fi
GITIGNORE_HEADER="# AI Agentic Framework files"

# Whether a shared file carries framework content at all. Without this the plan
# would promise an edit to a `.gitignore` or `.mcp.json` the framework never
# touched, and a project with nothing to clean would still ask for confirmation.
has_framework_content() {
    local rel="$1"
    local file="$PROJECT_PATH/$rel"
    case "$rel" in
        ".mcp.json")
            grep -q '"code_graph"' "$file" 2>/dev/null ;;
        ".codex/config.toml")
            grep -q 'code_graph' "$file" 2>/dev/null \
                || { provider_in_scope "codex" && grep -q 'ai-agentic-framework' "$file" 2>/dev/null; } ;;
        ".gitignore")
            printf '%s\n' "$GITIGNORE_HEADER" "${GITIGNORE_MANAGED_ENTRIES[@]}" | awk '
              NR == FNR { managed[$0] = 1; next }
              {
                line = $0
                sub(/^[[:space:]]+/, "", line)
                sub(/[[:space:]]+$/, "", line)
                bare = line
                sub(/\/$/, "", bare)
                if (line in managed || bare in managed) { found = 1; exit }
              }
              END { exit(found ? 0 : 1) }
            ' - "$file" ;;
        *) return 1 ;;
    esac
}

# `.mcp.json` is where Claude Code reads MCP servers and `.codex/config.toml` is
# where Codex reads them. A `code_graph` server in either is read by no
# provider, so both files are candidates on every run; the managed hooks block
# in `.codex/config.toml` is Codex's alone and goes only in its scope.
# `.gitignore` is shared, and follows the shared artifacts.
PRUNE_CANDIDATES=(".mcp.json" ".codex/config.toml")
if [ "$SHARED_IN_SCOPE" -eq 1 ]; then
    PRUNE_CANDIDATES+=(".gitignore")
fi

PRUNE_FILES=()
for candidate in "${PRUNE_CANDIDATES[@]}"; do
    if [ -f "$PROJECT_PATH/$candidate" ] && has_framework_content "$candidate"; then
        PRUNE_FILES+=("$candidate")
    fi
done

# `--check` is the probe other scripts use so this file stays the single owner
# of the inventory: initialize-project asks it whether a prior installation is
# there rather than re-deriving the path list and drifting from it.
if [ "$MODE" = "check" ]; then
    if [ "${#TARGETS[@]}" -gt 0 ] || [ "${#PRUNE_FILES[@]}" -gt 0 ]; then
        exit 0
    fi
    exit 1
fi

if [ "${#TARGETS[@]}" -eq 0 ] && [ "${#PRUNE_FILES[@]}" -eq 0 ]; then
    if [ -n "$PROVIDER" ]; then
        echo -e "${GREEN}Nothing to clean — no $PROVIDER framework artifacts found in $PROJECT_PATH${NC}"
    else
        echo -e "${GREEN}Nothing to clean — no framework artifacts found in $PROJECT_PATH${NC}"
    fi
    exit 0
fi

# ============================================================================
# PLAN REPORT
# ============================================================================

echo -e "${CYAN}========================================================================${NC}"
echo -e "${CYAN}  CLEAN-QAF${NC}"
echo -e "${CYAN}========================================================================${NC}"
echo -e "${BLUE}ℹ Project: $PROJECT_PATH${NC}"
if [ -n "$PROVIDER" ]; then
    echo -e "${BLUE}ℹ Scope:   $PROVIDER artifacts only${NC}"
fi
echo ""

if [ "${#TARGETS[@]}" -gt 0 ]; then
    echo -e "${YELLOW}Will remove:${NC}"
    for rel in "${TARGETS[@]}"; do
        size="$(du -sh "$PROJECT_PATH/$rel" 2>/dev/null | cut -f1)"
        echo -e "  ${RED}✗${NC} $rel  ${DIM}${size:-}${NC}"
    done
    echo ""
fi

if [ "${#PRUNE_FILES[@]}" -gt 0 ]; then
    echo -e "${YELLOW}Will prune (framework entries only, engineer entries kept):${NC}"
    for rel in "${PRUNE_FILES[@]}"; do
        echo -e "  ${YELLOW}~${NC} $rel"
    done
    echo ""
fi

if [ "$FRAMEWORK_PRESENT" -eq 1 ] && [ "$INCLUDE_FRAMEWORK" -eq 0 ]; then
    echo -e "${DIM}Keeping $FRAMEWORK_DIR_NAME/ — re-initialize with"
    echo -e "  ./$FRAMEWORK_DIR_NAME/scripts/initialize-project.sh"
    echo -e "Pass --include-framework to remove it too.${NC}"
    echo ""
fi

if [ -d "$PROJECT_PATH/$PROVIDER_BACKUP_DIR" ]; then
    echo -e "${DIM}Keeping $PROVIDER_BACKUP_DIR/ — a clean never removes a backup store, and this"
    echo -e "run's own archive goes in it.${NC}"
    echo ""
fi

if [ "$KEEP_CONFIG" -eq 1 ]; then
    echo -e "${DIM}Keeping framework-config.json (--keep-config) — the next initialization carries"
    echo -e "your team's tool defaults forward instead of reseeding the shipped ones.${NC}"
    echo ""
fi

if [ -f "$PROJECT_PATH/scripts/initialize-project.sh" ] && [ -f "$PROJECT_PATH/orchestration/package.json" ]; then
    echo -e "${YELLOW}⚠ This project IS the framework checkout (dogfooding mode).${NC}"
    echo -e "${YELLOW}  docs/llm-wiki/ is tracked here — removing it dirties the working tree.${NC}"
    echo -e "${YELLOW}  \`git restore\` brings it back.${NC}"
    echo ""
fi

if [ "${#NOTES[@]}" -gt 0 ]; then
    for note in "${NOTES[@]}"; do
        echo -e "${YELLOW}⚠ $note${NC}"
    done
    echo ""
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${BLUE}Dry run — nothing was changed.${NC}"
    exit 0
fi

# ============================================================================
# CONFIRMATION
# ============================================================================

if [ "$DO_BACKUP" -eq 1 ]; then
    echo -e "${BLUE}A backup is written to $(backup_location) before anything is removed.${NC}"
else
    echo -e "${RED}--no-backup: removals are NOT recoverable through clean-qaf.${NC}"
fi
echo ""

if [ "$ASSUME_YES" -eq 0 ]; then
    if [ ! -t 0 ]; then
        echo -e "${RED}[clean-qaf] refusing to clean unattended — pass --yes to confirm${NC}" >&2
        exit 1
    fi
    printf "Proceed? [y/N] "
    read -r REPLY_CONFIRM
    case "$REPLY_CONFIRM" in
        y|Y|yes|YES) ;;
        *) echo "Aborted."; exit 1 ;;
    esac
    echo ""
fi

# ============================================================================
# BACKUP
# ============================================================================

# Everything the run is about to remove or prune, in one archive rooted at the
# project so `tar -xzf … -C <project>` is the whole restore. The framework
# checkout is excluded even when it is being removed: it is a git clone, and
# archiving its dependencies would dwarf the artifacts that matter.
#
# The archive lands in the provider's backup store, so the directory holding it
# ignores itself in Git rather than relying on an entry in the root `.gitignore`
# — that file is something this script PRUNES, and an ignore rule for the
# archives has no business living in a file the cleaner edits. The store is also
# absent from the inventory above, so the archive tar is never one of the paths
# tar is asked to read while it writes it.
create_backup() {
    local -a entries=()
    local rel
    for rel in "${TARGETS[@]+"${TARGETS[@]}"}"; do
        [ "$rel" = "$FRAMEWORK_DIR_NAME" ] && continue
        entries+=("$rel")
    done
    for rel in "${PRUNE_FILES[@]+"${PRUNE_FILES[@]}"}"; do
        entries+=("$rel")
    done
    if [ "${#entries[@]}" -eq 0 ]; then
        return 0
    fi

    mkdir -p "$BACKUP_DIR"
    if [ -z "$BACKUP_HOME" ] && [ ! -f "$BACKUP_DIR/.gitignore" ]; then
        printf '*\n' > "$BACKUP_DIR/.gitignore"
    fi
    local archive
    archive="$BACKUP_DIR/$(next_archive_id).tar.gz"
    if ! tar -czf "$archive" -C "$PROJECT_PATH" "${entries[@]}" 2>/dev/null; then
        rm -f "$archive"
        echo -e "${RED}[clean-qaf] backup failed — nothing was removed${NC}" >&2
        echo -e "${DIM}Re-run with --no-backup to clean anyway.${NC}" >&2
        exit 4
    fi
    BACKUP_ARCHIVE="$archive"
    echo -e "${GREEN}✓ Backup: $archive${NC}"
}

BACKUP_ARCHIVE=""
if [ "$DO_BACKUP" -eq 1 ]; then
    create_backup
fi

# ============================================================================
# REMOVAL
# ============================================================================

for rel in "${TARGETS[@]+"${TARGETS[@]}"}"; do
    rm -rf "$PROJECT_PATH/$rel"
    echo -e "${GREEN}✓ Removed${NC} $rel"
done

# ============================================================================
# SURGICAL PRUNING
# ============================================================================

# Drop the `code_graph` server from a Claude MCP config, keeping every other
# server the engineer registered. The file goes only when nothing survives.
prune_mcp_json() {
    local file="$PROJECT_PATH/.mcp.json"
    [ -f "$file" ] || return 0
    if ! command -v node > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ node unavailable — left .mcp.json in place; remove its \"code_graph\" server by hand${NC}"
        return 0
    fi
    local verdict
    verdict="$(node -e '
const fs = require("fs");
const file = process.argv[1];
try {
  const cfg = JSON.parse(fs.readFileSync(file, "utf8")) || {};
  if (cfg.mcpServers && typeof cfg.mcpServers === "object") {
    delete cfg.mcpServers.code_graph;
    if (Object.keys(cfg.mcpServers).length === 0) delete cfg.mcpServers;
  }
  if (Object.keys(cfg).length === 0) {
    process.stdout.write("EMPTY");
  } else {
    fs.writeFileSync(file, JSON.stringify(cfg, null, 2) + "\n");
    process.stdout.write("PRUNED");
  }
} catch {
  process.stdout.write("UNPARSEABLE");
}
' "$file" 2>/dev/null || printf 'UNPARSEABLE')"

    case "$verdict" in
        EMPTY)
            rm -f "$file"
            echo -e "${GREEN}✓ Removed${NC} .mcp.json ${DIM}(held only the \"code_graph\" server)${NC}" ;;
        PRUNED)
            echo -e "${GREEN}✓ Pruned${NC} .mcp.json ${DIM}(dropped \"code_graph\", kept your other servers)${NC}" ;;
        *)
            echo -e "${YELLOW}⚠ .mcp.json is not valid JSON — left untouched${NC}" ;;
    esac
}

# Drop the framework's managed regions from a Codex config: the
# [mcp_servers.code_graph] table (with any subtables) on every run, and the
# sentinel-wrapped hooks block only when Codex is in scope — a surviving Codex
# installation still runs those hooks. Anything else in the file is the
# engineer's.
prune_codex_config_toml() {
    local file="$PROJECT_PATH/.codex/config.toml"
    [ -f "$file" ] || return 0
    local tmp="$file.clean-qaf.tmp"
    local drop_hooks=0
    provider_in_scope "codex" && drop_hooks=1
    awk -v drop_hooks="$drop_hooks" '
      /^[[:space:]]*#[[:space:]]*===[[:space:]]*(end:[[:space:]]*)?ai-agentic-framework/ { skip = 0 }
      drop_hooks == 1 && /^[[:space:]]*#[[:space:]]*===[[:space:]]*ai-agentic-framework:[[:space:]]*codex hooks/ { hooks = 1; next }
      hooks && /^[[:space:]]*#[[:space:]]*===[[:space:]]*end:[[:space:]]*ai-agentic-framework codex hooks/ { hooks = 0; next }
      hooks { next }
      /^[[:space:]]*\[/ {
        if ($0 ~ /^[[:space:]]*\[mcp_servers\.code_graph[.\]]/) { skip = 1; next }
        skip = 0
      }
      skip { next }
      { print }
    ' "$file" > "$tmp"

    if [ -n "$(grep -v '^[[:space:]]*$' "$tmp" 2>/dev/null | grep -v '^[[:space:]]*#' || true)" ]; then
        mv "$tmp" "$file"
        echo -e "${GREEN}✓ Pruned${NC} .codex/config.toml ${DIM}(dropped the framework blocks)${NC}"
    else
        rm -f "$tmp" "$file"
        echo -e "${GREEN}✓ Removed${NC} .codex/config.toml ${DIM}(held only framework blocks)${NC}"
    fi
}

# Drop the entries preflight added to .gitignore. The framework checkout's own
# entry survives while the checkout is still on disk — un-ignoring a directory
# that is still there would only fill `git status` with noise.
prune_gitignore() {
    local file="$PROJECT_PATH/.gitignore"
    [ -f "$file" ] || return 0

    local tmp="$file.clean-qaf.tmp"
    printf '%s\n' "${GITIGNORE_MANAGED_ENTRIES[@]}" \
        | awk -v drop_header="$GITIGNORE_DROP_HEADER" -v header="$GITIGNORE_HEADER" '
      NR == FNR { drop[$0] = 1; next }
      {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        sub(/[[:space:]]+$/, "", line)
        bare = line
        sub(/\/$/, "", bare)
        if (line == header && drop_header == 1) next
        if (bare != "" && (bare in drop)) next
        print
      }
    ' - "$file" > "$tmp"

    if [ -n "$(grep -v '^[[:space:]]*$' "$tmp" 2>/dev/null || true)" ]; then
        mv "$tmp" "$file"
        echo -e "${GREEN}✓ Pruned${NC} .gitignore ${DIM}(dropped the framework entries)${NC}"
    else
        rm -f "$tmp" "$file"
        echo -e "${GREEN}✓ Removed${NC} .gitignore ${DIM}(held only framework entries)${NC}"
    fi
}

# Only the files the plan listed: a shared file outside this run's scope, or one
# carrying no framework content, is not this run's to rewrite.
for rel in "${PRUNE_FILES[@]+"${PRUNE_FILES[@]}"}"; do
    case "$rel" in
        ".mcp.json") prune_mcp_json ;;
        ".codex/config.toml") prune_codex_config_toml ;;
        ".gitignore") prune_gitignore ;;
    esac
done

# ============================================================================
# EMPTY-PARENT CLEANUP
# ============================================================================

# A parent the framework created purely to hold its own output should not
# outlive it. `rmdir` is the guard: it refuses on anything non-empty.
remove_if_empty() {
    local rel="$1"
    [ -d "$PROJECT_PATH/$rel" ] || return 0
    if rmdir "$PROJECT_PATH/$rel" 2>/dev/null; then
        echo -e "${GREEN}✓ Removed${NC} $rel ${DIM}(empty)${NC}"
    fi
}

if [ "$SHARED_IN_SCOPE" -eq 1 ]; then
    remove_if_empty "docs"
fi
for __provider in claude codex; do
    if provider_in_scope "$__provider"; then
        __config_dir="$(provider_config_dir "$__provider")"
        remove_if_empty "$__config_dir/skills"
        remove_if_empty "$__config_dir/agents"
        remove_if_empty "$__config_dir"
    fi
done
unset __provider __config_dir

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${GREEN}========================================================================${NC}"
echo -e "${GREEN}  Project cleaned${NC}"
echo -e "${GREEN}========================================================================${NC}"
if [ -n "$BACKUP_ARCHIVE" ]; then
    echo -e "${BLUE}Backup:${NC}  $BACKUP_ARCHIVE"
    if [ "$FRAMEWORK_PRESENT" -eq 1 ] && [ "$INCLUDE_FRAMEWORK" -eq 0 ]; then
        echo -e "${DIM}Undo:    ./$FRAMEWORK_DIR_NAME/scripts/clean-qaf.sh --restore latest${NC}"
    else
        echo -e "${DIM}Undo:    tar -xzf $BACKUP_ARCHIVE -C $PROJECT_PATH${NC}"
    fi
fi
if [ "$FRAMEWORK_PRESENT" -eq 1 ] && [ "$INCLUDE_FRAMEWORK" -eq 0 ]; then
    echo -e "${BLUE}Next:${NC}    ./$FRAMEWORK_DIR_NAME/scripts/initialize-project.sh"
else
    echo -e "${BLUE}Next:${NC}    git clone https://github.com/thisisqubika/qubika-agentic-framework.git $DEFAULT_FRAMEWORK_DIR_NAME"
    echo -e "         ./$DEFAULT_FRAMEWORK_DIR_NAME/scripts/initialize-project.sh"
fi
echo ""
