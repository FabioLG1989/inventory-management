"""Scope a test run to a git diff instead of running an entire suite.

This script computes, for one --suite, which of its test files are impacted
by the changes between --base and the working tree (or --head), and whether
it is even safe to scope the run at all.

Safety is the point, not the optimization. Scoping is refused (scope="full")
whenever the mapping cannot be trusted:
  - the current branch matches a protected-branch pattern (release gates
    should always run everything, not whatever a diff-mapping heuristic
    found)
  - a changed file matches a "core" glob (lockfiles, CI config, root
    config, env files, migrations) — a change there can affect tests with
    no direct import relationship to it
  - a changed source file maps to zero known test files (an "unmapped"
    file) — silently skipping untested-by-mapping code is worse than a
    slower full run

Mapping is intentionally cheap (filesystem-convention heuristics plus an
optional per-project rule file) rather than import resolution — this is a
stdlib-only script with no access to a language's module resolver. For a
stronger transitive-impact signal (a shared file changed, what actually
imports it), the calling agent should Grep the way the project's imports
reference each changed file (module path, package name or file basename)
and pass the changed files plus their importers in via --changed-files,
which replaces git diff with that list; the heuristic mapping then runs
over it — see references/test-impact-analysis.md.

This script never runs the tests it selects — it only decides which ones a
caller should run and prints the resulting command. After that run
finishes, record it with `record_run.py --scope impacted --impacted-files
<paths> --base-ref <base>` so references/history-schema.md's scope/
impactedFiles/baseRef fields make the partial run visible in history
instead of quietly skewing pass-rate and flaky-test trends.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_PROTECTED_BRANCHES = (
    r"^(main|master|develop|development)$",
    r"^release/.*$",
    r"^hotfix/.*$",
)

DEFAULT_CORE_GLOBS = (
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "poetry.lock", "Pipfile.lock", "go.sum", "Gemfile.lock", "composer.lock",
    ".github/workflows/**", "azure-pipelines.yml", ".gitlab-ci.yml",
    "package.json", "pyproject.toml", "tsconfig*.json", "*.config.js", "*.config.ts",
    "*.config.cjs", "*.config.mjs", "Dockerfile*", "docker-compose*.yml", "docker-compose*.yaml",
    ".env*",
)
# Directory names that force scope=full wherever they appear in a changed
# file's path — checked by path-segment membership, not a glob. fnmatch's
# `*` has no path-separator awareness, so a **/-prefixed glob like
# "**/migrations/**" only matches when at least one segment precedes it
# (app/migrations/x.sql matches, a root-level migrations/x.sql does not —
# common for single-app Django/Alembic/Prisma layouts) and silently misses
# the exact root-level case the check exists to catch. Same reasoning
# scan_test_data.py's INCLUDE_DIR_MARKERS already uses for fixtures/seeds/
# etc.; a fixed-position directory (.github/workflows, always repo-root)
# doesn't need this and stays a plain glob in DEFAULT_CORE_GLOBS above.
DEFAULT_CORE_DIR_MARKERS = ("migrations",)

# (source suffix, test-file templates tried in the same directory, in order)
COLOCATION_TEMPLATES: dict[str, tuple[str, ...]] = {
    ".ts": ("{stem}.spec.ts", "{stem}.test.ts"),
    ".tsx": ("{stem}.spec.tsx", "{stem}.test.tsx"),
    ".js": ("{stem}.spec.js", "{stem}.test.js"),
    ".jsx": ("{stem}.spec.jsx", "{stem}.test.jsx"),
    ".py": ("test_{stem}.py", "{stem}_test.py"),
    ".go": ("{stem}_test.go",),
    ".rb": ("{stem}_spec.rb",),
    # Maven Surefire's own default test-inclusion globs — see TEST_FILE_HINTS.
    ".java": ("{stem}Test.java", "{stem}Tests.java", "{stem}TestCase.java", "Test{stem}.java"),
    ".cs": ("{stem}Tests.cs", "{stem}Test.cs"),
    ".php": ("{stem}Test.php",),
}

# Directory-name pairs tried for the "mirror" convention: a source file under
# a `.../<src_dir>/...` path is also looked for under `.../<test_dir>/...`
# at the same relative position, keeping its own filename (plus the same
# colocation suffix templates, in case the mirrored copy is also renamed).
MIRROR_DIR_PAIRS: tuple[tuple[str, str], ...] = (
    ("src", "test"), ("src", "tests"), ("src", "__tests__"),
    ("lib", "test"), ("lib", "tests"),
    ("app", "test"), ("app", "tests"),
)

TEST_FILE_HINTS = re.compile(
    r"(\.spec\.[jt]sx?$|\.test\.[jt]sx?$|^test_.*\.py$|.*_test\.py$|_test\.go$|_spec\.rb$"
    r"|Test\.java$|Tests\.java$|TestCase\.java$|^Test.*\.java$|Tests?\.cs$|Test\.php$)"
)


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(cwd))
    if result.returncode != 0:
        print(f"ERROR: git {' '.join(args)} failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def _current_branch(repo_root: Path) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root).strip()


def _changed_files(base: str, head: str | None, repo_root: Path) -> list[str]:
    diff_range = f"{base}...{head}" if head else base
    output = _git(["diff", "--name-only", diff_range], repo_root)
    files = {line.strip() for line in output.splitlines() if line.strip()}
    if not head:
        # Diffing against the working tree: also pick up new, not-yet-tracked
        # files (git diff alone never reports these) so a locally-added
        # source+test pair is impact-analyzed like any other local edit.
        untracked = _git(["ls-files", "--others", "--exclude-standard"], repo_root)
        files.update(line.strip() for line in untracked.splitlines() if line.strip())
    return sorted(files)


def _load_map_file(path: Path, suite: str) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"ERROR: cannot parse --map-file '{path}': {exc}", file=sys.stderr)
        sys.exit(1)
    return data.get("suites", {}).get(suite, {})


def _matches_any_glob(path: str, globs: tuple[str, ...]) -> str | None:
    for glob in globs:
        if fnmatch.fnmatch(path, glob) or fnmatch.fnmatch("/" + path, "*/" + glob):
            return glob
    return None


def _is_core_file(path: str, core_globs: tuple[str, ...], core_dir_markers: tuple[str, ...]) -> bool:
    if _matches_any_glob(path, core_globs) is not None:
        return True
    return any(part in core_dir_markers for part in Path(path).parts)


def _apply_custom_rules(changed_file: str, rules: list[dict], repo_root: Path) -> list[str]:
    found: list[str] = []
    repo_root_resolved = repo_root.resolve()
    for rule in rules:
        source_pattern = rule.get("sourcePattern")
        test_pattern = rule.get("testPattern")
        if not source_pattern or not test_pattern:
            continue
        match = re.match(source_pattern, changed_file)
        if not match:
            continue
        candidate = match.expand(re.sub(r"\\(\d)", r"\\g<\1>", test_pattern))
        candidate_path = repo_root / candidate
        if not candidate_path.exists():
            continue
        # testPattern is a capture-group substitution from the map file, so a
        # rule with an unanchored sourcePattern or a `../`-bearing
        # testPattern can expand to a path outside repo_root — confirm the
        # resolved candidate is still contained before ever treating it as a
        # test to run.
        if not candidate_path.resolve().is_relative_to(repo_root_resolved):
            print(f"WARNING: custom rule for '{changed_file}' expanded to '{candidate}', which resolves outside the repo root — skipping", file=sys.stderr)
            continue
        found.append(candidate)
    return found


def _colocation_candidates(changed_file: str, repo_root: Path) -> list[str]:
    path = Path(changed_file)
    templates = COLOCATION_TEMPLATES.get(path.suffix)
    if not templates:
        return []
    found = []
    for template in templates:
        candidate = path.with_name(template.format(stem=path.stem))
        if (repo_root / candidate).exists():
            found.append(str(candidate))
    return found


def _mirror_candidates(changed_file: str, repo_root: Path) -> list[str]:
    parts = Path(changed_file).parts
    found: list[str] = []
    for src_dir, test_dir in MIRROR_DIR_PAIRS:
        if src_dir not in parts:
            continue
        idx = parts.index(src_dir)
        mirrored_parts = parts[:idx] + (test_dir,) + parts[idx + 1:]
        mirrored = Path(*mirrored_parts)
        if (repo_root / mirrored).exists():
            found.append(str(mirrored))
        found.extend(_colocation_candidates(str(mirrored), repo_root))
    return found


def _map_to_tests(changed_file: str, repo_root: Path, suite_config: dict) -> list[str]:
    if TEST_FILE_HINTS.search(Path(changed_file).name):
        # `git diff --name-only` reports deletions too — a changed file that
        # looks like a test but no longer exists (deleted on this branch)
        # must not come back as something to run. The other three mapping
        # branches below all gate on .exists(); this early return has to
        # match them instead of handing the path straight back.
        return [changed_file] if (repo_root / changed_file).exists() else []
    candidates: list[str] = []
    candidates.extend(_apply_custom_rules(changed_file, suite_config.get("rules", []), repo_root))
    candidates.extend(_colocation_candidates(changed_file, repo_root))
    candidates.extend(_mirror_candidates(changed_file, repo_root))
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _build_report(args: argparse.Namespace, repo_root: Path) -> dict:
    # --map-file is documented as a path relative to the repo, not to the
    # caller's cwd — resolve it against repo_root so `--repo-root
    # /some/repo` from a different working directory (the entire point of
    # that flag) doesn't silently lose the map file's rules/coreGlobs/
    # runCommandTemplate with no error, just a quiet fallback to `{}`.
    map_file_path = Path(args.map_file)
    if not map_file_path.is_absolute():
        map_file_path = repo_root / map_file_path
    suite_config = _load_map_file(map_file_path, args.suite)
    # A change to the map file itself always forces a full run — it's the
    # rulebook this script trusts to decide what's safe to skip, so editing
    # it is exactly the moment to re-verify with everything, not the moment
    # to trust a stale mapping to score its own replacement.
    core_globs = (args.map_file,) + tuple(suite_config.get("coreGlobs", ())) + DEFAULT_CORE_GLOBS + tuple(args.core_glob or ())
    core_dir_markers = tuple(suite_config.get("coreDirMarkers", ())) + DEFAULT_CORE_DIR_MARKERS + tuple(args.core_dir_marker or ())
    protected_patterns = tuple(args.protected_branch) if args.protected_branch else DEFAULT_PROTECTED_BRANCHES

    branch = args.branch or _current_branch(repo_root)
    changed_files = args.changed_files or _changed_files(args.base, args.head, repo_root)

    if not changed_files:
        return {
            "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
            "scope": "none", "reason": f"no changes detected against {args.base}",
            "changedFiles": [], "impactedTestFiles": [], "coreFilesChanged": [],
            "unmappedFiles": [], "recommendedCommand": None, "recommendedCommandNote": None,
        }

    if not args.allow_scoped_on_protected_branch:
        # A detached HEAD (git's literal `--abbrev-ref HEAD` output when
        # there's no branch) has no name to check against the protected
        # patterns at all — common in CI checking out a specific commit,
        # which can just as easily be main's own tip as a scratch
        # exploration. No branch identity to trust means no basis to scope,
        # so it gets the same treatment as an explicitly protected branch.
        if branch == "HEAD":
            return {
                "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
                "scope": "full",
                "reason": "detached HEAD — no branch name to check against the protected list, "
                          "so there's no basis to trust scoping "
                          "(pass --allow-scoped-on-protected-branch to override)",
                "changedFiles": changed_files, "impactedTestFiles": [], "coreFilesChanged": [],
                "unmappedFiles": [], "recommendedCommand": None, "recommendedCommandNote": None,
            }
        for pattern in protected_patterns:
            if re.match(pattern, branch):
                return {
                    "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
                    "scope": "full",
                    "reason": f"branch '{branch}' matches protected pattern '{pattern}' — "
                              "impact analysis is opt-in only on feature branches "
                              "(pass --allow-scoped-on-protected-branch to override)",
                    "changedFiles": changed_files, "impactedTestFiles": [], "coreFilesChanged": [],
                    "unmappedFiles": [], "recommendedCommand": None, "recommendedCommandNote": None,
                }

    core_files_changed = [f for f in changed_files if _is_core_file(f, core_globs, core_dir_markers)]
    if core_files_changed:
        return {
            "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
            "scope": "full",
            "reason": f"{len(core_files_changed)} changed file(s) match a core glob or core directory "
                      "(shared config, lockfile, CI, migration) with unpredictable blast radius",
            "changedFiles": changed_files, "impactedTestFiles": [], "coreFilesChanged": core_files_changed,
            "unmappedFiles": [], "recommendedCommand": None, "recommendedCommandNote": None,
        }

    impacted_test_files: list[str] = []
    unmapped_files: list[str] = []
    for changed_file in changed_files:
        candidates = _map_to_tests(changed_file, repo_root, suite_config)
        if candidates:
            impacted_test_files.extend(candidates)
        else:
            unmapped_files.append(changed_file)

    if unmapped_files and not args.allow_unmapped:
        return {
            "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
            "scope": "full",
            "reason": f"{len(unmapped_files)} changed file(s) matched no test file by convention or "
                      f"--map-file rule — see 'unmappedFiles' (pass --allow-unmapped to scope anyway)",
            "changedFiles": changed_files, "impactedTestFiles": sorted(set(impacted_test_files)),
            "coreFilesChanged": [], "unmappedFiles": unmapped_files, "recommendedCommand": None, "recommendedCommandNote": None,
        }

    impacted_test_files = sorted(set(impacted_test_files))
    template = suite_config.get("runCommandTemplate")
    recommended_command = None
    recommended_command_note = None
    if template and impacted_test_files:
        recommended_command = template.replace("{testFiles}", " ".join(shlex.quote(f) for f in impacted_test_files))
    elif impacted_test_files:
        # Not a command — a prose explanation of why there isn't one. Kept
        # out of recommendedCommand so a markdown renderer never emits this
        # inside a ```bash fence as if it were something to run.
        recommended_command_note = (
            f"no runCommandTemplate configured for suite '{args.suite}' in {args.map_file} — "
            "pass impactedTestFiles to your runner's file-filter flag manually"
        )

    if impacted_test_files:
        reason = (
            f"--allow-unmapped set: {len(unmapped_files)} changed file(s) matched no test file and were skipped; "
            "the rest map to a known test file within a trusted scope"
            if unmapped_files
            else "all changed files map to a known test file within a trusted scope"
        )
    elif unmapped_files:
        reason = (
            f"--allow-unmapped set: {len(unmapped_files)} changed file(s) matched no test file, "
            "and no other changed file mapped to one either — nothing to run for this suite"
        )
    else:
        reason = "changes are confined to test files already accounted for above"

    return {
        "suite": args.suite, "branch": branch, "base": args.base, "head": args.head,
        "scope": "impacted" if impacted_test_files else "none",
        "reason": reason,
        "changedFiles": changed_files, "impactedTestFiles": impacted_test_files,
        "coreFilesChanged": [], "unmappedFiles": unmapped_files if args.allow_unmapped else [],
        "recommendedCommand": recommended_command, "recommendedCommandNote": recommended_command_note,
    }


def _render_markdown(report: dict) -> str:
    lines = [f"## Impact analysis — {report['suite']} ({report['scope']})", "", report["reason"], ""]
    lines.append(f"- Branch: `{report['branch']}` | Base: `{report['base']}`" + (f" | Head: `{report['head']}`" if report["head"] else ""))
    lines.append(f"- Changed files: {len(report['changedFiles'])}")
    if report["scope"] == "impacted":
        lines.append(f"- Impacted test files ({len(report['impactedTestFiles'])}):")
        lines.extend(f"  - `{f}`" for f in report["impactedTestFiles"])
        if report["unmappedFiles"]:
            lines.append(f"- Unmapped files skipped via --allow-unmapped: {', '.join(f'`{f}`' for f in report['unmappedFiles'][:10])}")
        if report["recommendedCommand"]:
            lines += ["", "```bash", report["recommendedCommand"], "```"]
        elif report["recommendedCommandNote"]:
            lines += ["", f"_{report['recommendedCommandNote']}_"]
    elif report["coreFilesChanged"]:
        lines.append(f"- Core files triggering full run: {', '.join(f'`{f}`' for f in report['coreFilesChanged'][:10])}")
    elif report["unmappedFiles"]:
        lines.append(f"- Unmapped files: {', '.join(f'`{f}`' for f in report['unmappedFiles'][:10])}")
    lines += [
        "",
        "Record whichever run you actually execute with `record_run.py --scope "
        f"{'impacted' if report['scope'] == 'impacted' else 'full'} "
        f"{'--impacted-files ' + ' '.join(report['impactedTestFiles']) + ' ' if report['impactedTestFiles'] else ''}"
        f"--base-ref {report['base']}`.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scope a test run to the files changed since --base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--suite", required=True, help="Logical suite name (matches record_run.py's --suite and a --map-file entry, if any)")
    parser.add_argument("--base", required=True, help="Git ref to diff against, e.g. origin/main or a merge-base SHA")
    parser.add_argument("--head", help="Git ref to diff to (default: working tree, via `git diff --name-only <base>`)")
    parser.add_argument("--branch", help="Override auto-detected current branch (used only for the protected-branch check)")
    parser.add_argument("--map-file", default=".qa/test-impact-map.json", help="Per-suite mapping rules (default: .qa/test-impact-map.json)")
    parser.add_argument("--repo-root", help="Repository root (default: cwd)")
    parser.add_argument("--changed-files", nargs="+", help="Explicit changed-file list — skips `git diff` entirely (e.g. the diff plus every importer a Grep for each changed file found)")
    parser.add_argument("--protected-branch", nargs="+", help="Override the default protected-branch regex list")
    parser.add_argument("--allow-scoped-on-protected-branch", action="store_true", help="Allow scoping even on a protected branch")
    parser.add_argument("--core-glob", nargs="+", help="Extra glob(s) that always force scope=full, in addition to the built-in defaults")
    parser.add_argument("--core-dir-marker", nargs="+", help="Extra directory name(s) that force scope=full wherever they appear in a changed file's path (checked by path-segment membership, not a glob — for directories that can appear at any depth, like a per-app migrations/ folder), in addition to the built-in 'migrations'")
    parser.add_argument("--allow-unmapped", action="store_true", help="Scope down even when some changed files matched no test file (their names are still reported)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", help="File path to write the report to (default: stdout)")
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    report = _build_report(args, repo_root)

    rendered = _render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + ("\n" if not rendered.endswith("\n") else ""))
        print(f"Impact analysis written to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    print(f"scope={report['scope']}: {report['reason']}", file=sys.stderr)


if __name__ == "__main__":
    main()
