#!/usr/bin/env bash
# validate-skill-sync.sh — Verify a skill was correctly registered and synced
#
# Usage:
#   bash validate-skill-sync.sh <skill-name> <framework-path> <project-path>
#
# Checks:
#   1. Framework source SKILL.md exists
#   2. Skill is registered in skills.config.json
#   3. skills.config.json is valid JSON
#   4. Synced SKILL.md exists in project .claude/skills/
#   5. Content matches between framework source and synced copy

set -euo pipefail

SKILL_NAME="${1:?Usage: validate-skill-sync.sh <skill-name> <framework-path> <project-path>}"
FRAMEWORK_PATH="${2:?Usage: validate-skill-sync.sh <skill-name> <framework-path> <project-path>}"
PROJECT_PATH="${3:?Usage: validate-skill-sync.sh <skill-name> <framework-path> <project-path>}"

PASS=0
FAIL=0
WARN=0

pass() { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }
warn() { echo "  ⚠ $1"; ((WARN++)); }

echo "Validating skill: ${SKILL_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# --- Check 1: Framework source exists ---
FRAMEWORK_SKILL_DIR=$(find "${FRAMEWORK_PATH}/skills" -maxdepth 2 -type d -name "${SKILL_NAME}" 2>/dev/null | head -1)

if [ -n "${FRAMEWORK_SKILL_DIR}" ] && [ -f "${FRAMEWORK_SKILL_DIR}/SKILL.md" ]; then
  pass "Framework source exists: ${FRAMEWORK_SKILL_DIR}/SKILL.md"
else
  fail "Framework source not found: skills/*/${SKILL_NAME}/SKILL.md"
fi

# --- Check 2: Registered in skills.config.json ---
CONFIG_FILE="${FRAMEWORK_PATH}/skills/skills.config.json"

if [ -f "${CONFIG_FILE}" ]; then
  if command -v jq &>/dev/null; then
    REGISTERED=$(jq -r --arg name "${SKILL_NAME}" '.skills[] | select(.name == $name) | .name' "${CONFIG_FILE}" 2>/dev/null)
    TRIGGER_MODE=$(jq -r --arg name "${SKILL_NAME}" '.skills[] | select(.name == $name) | .trigger_mode' "${CONFIG_FILE}" 2>/dev/null)
  else
    # Fallback: simple grep
    REGISTERED=$(grep -o "\"name\": *\"${SKILL_NAME}\"" "${CONFIG_FILE}" 2>/dev/null && echo "${SKILL_NAME}" || true)
    TRIGGER_MODE="unknown"
  fi

  if [ -n "${REGISTERED}" ]; then
    pass "Registered in skills.config.json (trigger_mode: ${TRIGGER_MODE})"
  else
    fail "Not registered in skills.config.json"
  fi
else
  fail "skills.config.json not found at ${CONFIG_FILE}"
fi

# --- Check 3: skills.config.json is valid JSON ---
if [ -f "${CONFIG_FILE}" ]; then
  if command -v jq &>/dev/null; then
    if jq empty "${CONFIG_FILE}" 2>/dev/null; then
      pass "skills.config.json is valid JSON"
    else
      fail "skills.config.json has invalid JSON syntax"
    fi
  elif command -v python3 &>/dev/null; then
    if python3 -m json.tool "${CONFIG_FILE}" >/dev/null 2>&1; then
      pass "skills.config.json is valid JSON"
    else
      fail "skills.config.json has invalid JSON syntax"
    fi
  else
    warn "Cannot validate JSON (neither jq nor python3 available)"
  fi
fi

# --- Check 4: Synced SKILL.md exists in project .claude/skills/ ---
SYNCED_SKILL=$(find "${PROJECT_PATH}/.claude/skills" -type f -path "*/${SKILL_NAME}/SKILL.md" 2>/dev/null | head -1)

if [ -n "${SYNCED_SKILL}" ]; then
  pass "Synced to project: ${SYNCED_SKILL}"
else
  if [ "${TRIGGER_MODE}" = "triggered" ]; then
    warn "Not synced to .claude/skills/ — expected for triggered skills if project stack does not match triggers"
  else
    fail "Not synced to .claude/skills/ — expected at ${PROJECT_PATH}/.claude/skills/*/${SKILL_NAME}/SKILL.md"
  fi
fi

# --- Check 5: Content matches ---
if [ -n "${FRAMEWORK_SKILL_DIR:-}" ] && [ -f "${FRAMEWORK_SKILL_DIR}/SKILL.md" ] && [ -n "${SYNCED_SKILL:-}" ]; then
  if diff -q "${FRAMEWORK_SKILL_DIR}/SKILL.md" "${SYNCED_SKILL}" >/dev/null 2>&1; then
    pass "Content matches between framework source and synced copy"
  else
    fail "Content mismatch — synced copy differs from framework source (may have been user-modified)"
  fi
fi

# --- Summary ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings"

if [ "${FAIL}" -gt 0 ]; then
  echo ""
  echo "Troubleshooting:"
  echo "  - Source missing?    → SKILL.md was not written to the correct framework directory"
  echo "  - Not registered?    → skills.config.json update failed or entry is malformed"
  echo "  - Not synced?        → Run ./scripts/sync-framework-resources.sh again"
  echo "  - Content mismatch?  → Sync may have skipped a user-modified version"
  exit 1
fi

exit 0
