"""Extract test titles from repo test files, stack-agnostically, via regex.

The mechanical half of requirement-coverage-gap-analysis: `/generate-test-cases`
already knows how to turn a ticket into a scenario list (Phase 3a/3b), but has
no view of what the *existing* suite already covers, so its coverage checklist
only ever validates a generated batch against itself. This script builds that
missing view — a flat inventory of {file, line, title} for whatever test
files already exist on disk — so a caller (Claude, or match_scenarios.py's
prefilter) can compare requirement-derived scenarios against it.

Regex extraction, not an AST — one file, one language-agnostic pass, nothing
to install. Titles it cannot express structurally (a parametrized test's
per-case IDs, a deeply nested `describe` chain) collapse to their outer
name — see references/extraction-patterns.md for exactly what each pattern
catches and misses per stack.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_INCLUDE_GLOBS = (
    "*.spec.*", "*.test.*", "test_*.py", "*_test.py", "*_test.go",
    # Maven Surefire's own default test-inclusion globs — matching them
    # here means a Java project's own build convention decides what's a
    # test, not a guess at just one of its four accepted spellings.
    "*Test.java", "*Tests.java", "Test*.java", "*TestCase.java",
    "*Tests.cs", "*Test.cs", "*Test.php", "*_spec.rb",
    "*.feature",
)

# The title body is "an escaped char, or any char that isn't the same
# quote the string opened with" — not the simpler `.*?`, which stops at
# the *first* quote character it sees regardless of a preceding backslash
# and truncates a title like 'doesn\'t work' at the escaped apostrophe. A
# different quote type embedded unescaped (`'He said "hi"'`) still works,
# since only \1 — the actual opening delimiter — ends the match.
JS_TEST_RE = re.compile(r"""\b(?:it|test)(?:\.\w+)?\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""")
# it.each([...])(title, ...) / test.each`table`(title, ...): the modifier's
# own table argument — a parenthesized array/object or a tagged template —
# sits between `.each` and the real call, so the title is not the first
# quote after `(` the way it is for a plain it()/test() call. Single-line
# only: a multi-line template-literal table (the closing backtick on a
# different line) is not matched — see references/extraction-patterns.md.
JS_EACH_TEST_RE = re.compile(r"""\b(?:it|test)\.each\s*(?:\([^)]*\)|`[^`]*`)\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""")
JS_DESCRIBE_RE = re.compile(r"""\bdescribe(?:\.\w+)?\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""")
PY_FUNC_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(")
PY_CLASS_RE = re.compile(r"^\s*class\s+(Test\w+)\b")
GO_FUNC_RE = re.compile(r"^func\s+(Test\w+)\s*\(")
PHP_FUNC_RE = re.compile(r"public\s+function\s+(test\w+)\s*\(", re.IGNORECASE)
RUBY_IT_RE = re.compile(r"""\bit\s*(['"])((?:\\.|(?!\1).)*)\1""")
RUBY_DESCRIBE_RE = re.compile(r"""\b(?:describe|context)\s*(['"])((?:\\.|(?!\1).)*)\1""")
RUBY_BLOCK_OPEN_RE = re.compile(r"\bdo\b")
RUBY_BLOCK_CLOSE_RE = re.compile(r"\bend\b")
DOTNET_ATTR_RE = re.compile(r"\[(Fact|Theory|Test)\b")
DOTNET_METHOD_RE = re.compile(r"\b(?:public|private|internal)\s+(?:async\s+)?\S+\s+(\w+)\s*\(")
GHERKIN_RE = re.compile(r"^\s*(Scenario(?:\s+Outline)?):\s*(.+)$")
JAVA_ATTR_RE = re.compile(r"@(Test|ParameterizedTest|RepeatedTest)\b")
JAVA_METHOD_RE = re.compile(r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:void|\w+(?:<[^>]*>)?)\s+(\w+)\s*\(")

# Pruned out of the walk before it ever inspects a file inside — a vendored
# or build-output test is not this repo's test, and descending into these
# directories at all is the real cost on a large tree, not just the noise
# in the result.
DEFAULT_EXCLUDE_DIR_MARKERS = frozenset({
    "node_modules", ".venv", "venv", "dist", "build", ".git", "target", "vendor",
})


def _iter_files(paths: list[str], include_globs: tuple[str, ...], exclude_dirs: frozenset[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            files.append(p)
            continue
        if not p.exists():
            matches = (
                [m for m in Path().glob(raw) if m.is_file() and not any(part in exclude_dirs for part in m.parts)]
                if not p.is_absolute() else []
            )
            if not matches:
                print(f"ERROR: --path '{raw}' is not an existing file or directory and matched no files", file=sys.stderr)
                sys.exit(1)
            files.extend(matches)
            continue
        for root, dirs, filenames in os.walk(p):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            root_path = Path(root)
            for filename in filenames:
                if any(fnmatch.fnmatch(filename, g) for g in include_globs):
                    files.append(root_path / filename)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered


def _unescape(title: str) -> str:
    """Drop the backslash from an escaped character in a captured quoted
    title (\\' -> ', \\" -> ") — the boundary-detection regex above keeps
    the backslash in the capture so it can tell an escaped quote from the
    real closing one; this is purely the display-cleanup step after that."""
    return re.sub(r"\\(.)", r"\1", title)


def _extract_js_ts(lines: list[str]) -> list[dict]:
    entries = []
    # (brace_depth_at_open, title) per currently-open describe, innermost
    # last. Popped once the running brace depth drops back below the depth
    # it was pushed at — i.e. once that describe's own block has closed —
    # so a test after it (sibling or outer) is not mislabeled with a
    # describe that already ended, not just one that is less specific.
    describe_stack: list[tuple[int, str]] = []
    depth = 0
    for lineno, line in enumerate(lines, start=1):
        describe_match = JS_DESCRIBE_RE.search(line)
        test_match = None
        if not describe_match:
            each_match = JS_EACH_TEST_RE.search(line)
            test_match = each_match if each_match else JS_TEST_RE.search(line)
        depth += line.count("{") - line.count("}")

        while describe_stack and depth < describe_stack[-1][0]:
            describe_stack.pop()

        if describe_match:
            describe_stack.append((depth, _unescape(describe_match.group(2))))
        elif test_match:
            title = _unescape(test_match.group(2))
            current_describe = describe_stack[-1][1] if describe_stack else None
            entries.append({
                "line": lineno,
                "title": f"{current_describe} > {title}" if current_describe else title,
                "framework": "jest/vitest/mocha/playwright",
            })
    return entries


def _extract_python(lines: list[str]) -> list[dict]:
    entries = []
    current_class: str | None = None
    for lineno, line in enumerate(lines, start=1):
        class_match = PY_CLASS_RE.match(line)
        if class_match:
            current_class = class_match.group(1)
            continue
        func_match = PY_FUNC_RE.match(line)
        if func_match:
            name = func_match.group(1)
            is_method = current_class is not None and line[:1] in (" ", "\t")
            entries.append({
                "line": lineno,
                "title": f"{current_class}::{name}" if is_method else name,
                "framework": "pytest",
            })
    return entries


def _extract_go(lines: list[str]) -> list[dict]:
    return [
        {"line": i, "title": m.group(1), "framework": "go test"}
        for i, line in enumerate(lines, start=1)
        if (m := GO_FUNC_RE.match(line))
    ]


def _extract_php(lines: list[str]) -> list[dict]:
    return [
        {"line": i, "title": m.group(1), "framework": "phpunit"}
        for i, line in enumerate(lines, start=1)
        if (m := PHP_FUNC_RE.search(line))
    ]


def _extract_ruby(lines: list[str]) -> list[dict]:
    entries = []
    # Same depth-stack approach as _extract_js_ts, tracking Ruby's `do`/`end`
    # block delimiters instead of braces.
    describe_stack: list[tuple[int, str]] = []
    depth = 0
    for lineno, line in enumerate(lines, start=1):
        describe_match = RUBY_DESCRIBE_RE.search(line)
        it_match = None if describe_match else RUBY_IT_RE.search(line)
        depth += len(RUBY_BLOCK_OPEN_RE.findall(line)) - len(RUBY_BLOCK_CLOSE_RE.findall(line))

        while describe_stack and depth < describe_stack[-1][0]:
            describe_stack.pop()

        if describe_match:
            describe_stack.append((depth, _unescape(describe_match.group(2))))
        elif it_match:
            title = _unescape(it_match.group(2))
            current_describe = describe_stack[-1][1] if describe_stack else None
            entries.append({
                "line": lineno,
                "title": f"{current_describe} > {title}" if current_describe else title,
                "framework": "rspec",
            })
    return entries


def _extract_dotnet(lines: list[str]) -> list[dict]:
    entries = []
    pending_attr: str | None = None
    for lineno, line in enumerate(lines, start=1):
        attr_match = DOTNET_ATTR_RE.search(line)
        if attr_match:
            pending_attr = attr_match.group(1)
        # No `continue` here: `[Fact] public void Foo() {}` puts the
        # attribute and the method on the same line, and discarding the
        # rest of the line before checking for a method dropped it entirely
        # rather than just deferring to the next line.
        if pending_attr:
            method_match = DOTNET_METHOD_RE.search(line)
            if method_match:
                entries.append({"line": lineno, "title": method_match.group(1), "framework": f"dotnet-{pending_attr.lower()}"})
                pending_attr = None
    return entries


def _extract_java(lines: list[str]) -> list[dict]:
    entries = []
    pending = False
    for lineno, line in enumerate(lines, start=1):
        if JAVA_ATTR_RE.search(line):
            pending = True
        # No `continue` here — same reason as _extract_dotnet above:
        # `@Test void inlineStyle() {}` on one line must still be checked
        # for its method on this same pass, not just the next line.
        if pending:
            method_match = JAVA_METHOD_RE.search(line)
            if method_match:
                entries.append({"line": lineno, "title": method_match.group(1), "framework": "junit"})
                pending = False
    return entries


def _extract_gherkin(lines: list[str]) -> list[dict]:
    entries = []
    for lineno, line in enumerate(lines, start=1):
        match = GHERKIN_RE.match(line)
        if match:
            entries.append({"line": lineno, "title": match.group(2).strip(), "framework": "gherkin"})
    return entries


_EXTRACTORS_BY_SUFFIX = {
    ".ts": _extract_js_ts, ".tsx": _extract_js_ts, ".js": _extract_js_ts, ".jsx": _extract_js_ts,
    ".py": _extract_python,
    ".go": _extract_go,
    ".php": _extract_php,
    ".rb": _extract_ruby,
    ".cs": _extract_dotnet,
    ".java": _extract_java,
    ".feature": _extract_gherkin,
}


def _extract(path: Path) -> list[dict]:
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError as exc:
        return [{"line": 0, "title": None, "framework": None, "error": str(exc)}]
    extractor = _EXTRACTORS_BY_SUFFIX.get(path.suffix.lower())
    if not extractor:
        return []
    return extractor(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract existing test titles from repo test files (stack-agnostic, regex-based).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--path", nargs="+", default=["."], help="File(s), directory/directories, or glob pattern(s) to scan (default: cwd)")
    parser.add_argument("--include-glob", nargs="+", help="Override the default test-file naming globs")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", help="File path to write the inventory to (default: stdout)")
    parser.add_argument("--exclude-dir", nargs="+", help="Extra directory name(s) to prune from the walk, in addition to the built-in node_modules/.venv/venv/dist/build/.git/target/vendor")
    args = parser.parse_args()

    include_globs = tuple(args.include_glob) if args.include_glob else DEFAULT_INCLUDE_GLOBS
    exclude_dirs = DEFAULT_EXCLUDE_DIR_MARKERS | frozenset(args.exclude_dir or ())
    files = _iter_files(args.path, include_globs, exclude_dirs)

    inventory: list[dict] = []
    for path in files:
        for entry in _extract(path):
            if entry.get("title") is None:
                continue
            inventory.append({"file": str(path), **entry})

    if args.format == "markdown":
        lines = [f"## Test inventory — {len(files)} file(s), {len(inventory)} title(s)", ""]
        lines.extend(f"- `{e['file']}:{e['line']}` [{e['framework']}] {e['title']}" for e in inventory)
        rendered = "\n".join(lines)
    else:
        rendered = json.dumps({"filesScanned": len(files), "tests": inventory}, indent=2)

    if args.output:
        Path(args.output).write_text(rendered + ("\n" if not rendered.endswith("\n") else ""))
        print(f"Test inventory written to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    print(f"{len(files)} file(s) scanned, {len(inventory)} test title(s) extracted", file=sys.stderr)


if __name__ == "__main__":
    main()
