"""Heuristic scan for test-data governance problems: PII-shaped literals,
fixture files with no declared provenance, and hardcoded values repeated
across enough files to be worth extracting into a factory.

This is a best-effort text/regex scanner, not a guarantee — no AST, no
per-language parser, no network calls, stdlib only (same constraint every
script in this framework runs under: nothing to `pip install` on any of the
6000+ machines this ships to). It exists to make the no-PII / factories-over-
literals / fixture-provenance rules in SKILL.md and references/pii-patterns.md
checkable instead of aspirational — read a finding, don't trust an absence of
findings as proof a file is clean.

Categories:
  pii-suspect-email   An email whose domain is not an RFC 2606/6761 reserved
                      testing domain (example.com/.net/.org, or anything
                      ending .test/.example/.invalid/.localhost) or one of
                      --fake-domains.
  pii-suspect-phone   A 10-digit NANP phone number, its 3-3-4 groups
                      separated by a space/dot/dash, outside the 555-01XX
                      block NANP reserves for fictional use. A separator is
                      required — a bare 10-digit run (an order ID, a
                      truncated timestamp) is not phone-shaped enough on its
                      own; see references/pii-patterns.md for the tradeoff.
  pii-suspect-ssn     A ###-##-#### SSN-shaped value whose area number is not
                      one the SSA has never issued (000, 666, 900-999) —
                      those are the only area numbers safe to hardcode.
  pii-suspect-card    A 13-19 digit, Luhn-valid card-shaped number that is
                      not one of the well-known published test card numbers,
                      AND starts with a real issuer prefix (3/4/5/6) AND has
                      card/pan/cc as its own identifier segment somewhere on
                      the line (see _has_card_context — a standalone word or
                      a component of cardNumber/card_number/CARD_NUMBER/
                      creditCard, not a bare substring match). All three are
                      required together: Luhn alone passes ~10% of random
                      digit runs of the right length (epoch-millis
                      timestamps, trace IDs), and a real issuer prefix alone
                      does not rule those back out either — a 16-digit ID
                      that happens to start with 4 is Visa-shaped by every
                      structural measure a regex has. See
                      references/pii-patterns.md for the measured
                      false-positive rate this guards against. A Luhn-invalid
                      number cannot be a real card number, so it is never
                      flagged regardless.
  fixture-missing-provenance
                      A fixture-directory data file (json/yaml/yml/csv) with
                      no provenance marker in its first few lines.
  duplicated-literal-suggest-factory
                      The same email/phone value hardcoded in 3+ distinct
                      files — a signal to extract a factory/builder instead
                      of copy-pasting the literal (see SKILL.md).

Name-shaped PII (a plausible real full name with no other signal) is
deliberately not scanned — there is no reliable stdlib way to tell a real
name from a placeholder one, and false positives on every "Alice"/"Bob" in
the codebase would drown real findings. See references/pii-patterns.md.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_INCLUDE_GLOBS = (
    "*.spec.*", "*.test.*", "test_*.py", "*_test.py", "*_test.go",
    # Maven Surefire's own default test-inclusion globs.
    "*Test.java", "*Tests.java", "Test*.java", "*TestCase.java",
    "*Tests.cs", "*Test.cs", "*Test.php", "*_spec.rb",
)
# Any file under a directory with one of these names is included regardless
# of --include-glob/name pattern — checked by directory membership, not by
# fnmatch, because fnmatch has no path-separator-aware "**" semantics and
# silently fails to match a top-level `fixtures/…` path against `**/fixtures/**`.
INCLUDE_DIR_MARKERS = ("fixtures", "seeds", "__fixtures__", "factories")
# Pruned out of the walk before INCLUDE_DIR_MARKERS ever sees them — a
# vendored fixtures/ directory under node_modules is not this project's test
# data, and descending into these directories at all is the actual cost on
# a real repo (not just false findings from what came out the other end).
DEFAULT_EXCLUDE_DIR_MARKERS = frozenset({
    "node_modules", ".venv", "venv", "dist", "build", ".git", "target", "vendor",
})
FIXTURE_DIR_MARKERS = ("fixtures", "seeds", "__fixtures__")
FIXTURE_DATA_SUFFIXES = (".json", ".yaml", ".yml", ".csv")
# INCLUDE_DIR_MARKERS force-includes every file under fixtures/seeds/factories
# regardless of suffix, so a binary seed dump (a DB snapshot, an image fixture)
# qualifies just as much as a text file — read_text(errors="ignore") on a large
# binary is wasted work at best. Default is generous for any real text fixture;
# override with --max-file-bytes for a project with legitimately larger ones.
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
PROVENANCE_MARKERS = re.compile(r"(generated|anonymi[sz]ed|synthetic|faker|factory|placeholder|dummy|_provenance|_meta)", re.IGNORECASE)
RESERVED_TLDS = {"test", "example", "invalid", "localhost"}
RESERVED_DOMAINS = {"example.com", "example.net", "example.org"}

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# Separator between the 3-3-4 groups is mandatory: without it, this matches
# any 10-digit run (order IDs, truncated timestamps) — see module docstring.
PHONE_RE = re.compile(r"\(?\b(\d{3})\)?[\s.-](\d{3})[\s.-](\d{4})\b")
SSN_RE = re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
CARD_ISSUER_PREFIXES = ("3", "4", "5", "6")
CARD_CONTEXT_WORDS = frozenset({"card", "pan", "cc"})
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]+")
_IDENTIFIER_SEGMENT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

KNOWN_TEST_CARDS = {
    "4111111111111111", "4012888888881881", "4222222222222",
    "5555555555554444", "5105105105105100", "5454545454545454",
    "378282246310005", "371449635398431", "340000000000009",
    "6011111111111117", "6011000990139424", "30569309025904", "38520000023237",
}


def _is_fake_domain(domain: str, extra: set[str]) -> bool:
    domain = domain.lower()
    for safe in RESERVED_DOMAINS | extra:
        if domain == safe or domain.endswith("." + safe):
            return True
    return domain.rsplit(".", 1)[-1] in RESERVED_TLDS


def _is_fake_phone(digits: str) -> bool:
    return digits[3:6] == "555" and digits[6:8] == "01"


def _is_fake_ssn(area: str) -> bool:
    return area == "000" or area == "666" or (900 <= int(area) <= 999)


def _mask(value: str) -> str:
    """Mask a PII-suspect literal before it is ever written to a report or CI
    log — the same treatment `_scan_file` already gives card numbers below.
    Keeps punctuation/shape and the last 4 digits for a phone/SSN match
    (***-**-6789), or the first local-part character and the domain for an
    email (a***@corp.example); everything else that could identify a real
    person is starred out."""
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}{'*' * max(len(local) - 1, 3)}@{domain}"
    digit_count = sum(ch.isdigit() for ch in value)
    keep_from = digit_count - 4
    seen = 0
    masked = []
    for ch in value:
        if ch.isdigit():
            seen += 1
            masked.append(ch if seen > keep_from else "*")
        else:
            masked.append(ch)
    return "".join(masked)


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _has_card_context(line: str) -> bool:
    """True if 'card', 'pan', or 'cc' appears as its own identifier segment
    on this line — a standalone word, or a component of a camelCase /
    snake_case / SCREAMING_CASE name (cardNumber, card_number, CARD_NUMBER,
    creditCard, ccNumber).

    Deliberately segment-based rather than a bare substring search: 'pan'
    and 'cc' are short enough to appear inside ordinary words by accident
    (company, japan, access, success, account) if matched loosely, and a
    naive `\\bcard\\b` never matches inside a compound identifier at all —
    `\\b` only fires at a transition into/out of `[A-Za-z0-9_]`, and every
    character on both sides of the case-transition in "cardNumber" (or the
    underscore in "card_number") is itself a word character, so there is no
    such transition for `\\b` to find. Splitting each identifier into its
    real sub-words first, the way a human reads it, is what card|pan|cc as
    "an identifier" (not just a bare token) actually requires.
    """
    for token in _ALNUM_RUN_RE.findall(line):
        for segment in _IDENTIFIER_SEGMENT_RE.findall(token):
            if segment.lower() in CARD_CONTEXT_WORDS:
                return True
    return False


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
                candidate = root_path / filename
                name_matches = any(fnmatch.fnmatch(filename, g) for g in include_globs)
                in_include_dir = any(part in INCLUDE_DIR_MARKERS for part in candidate.parts)
                if name_matches or in_include_dir:
                    files.append(candidate)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered


def _is_fixture_data_file(path: Path) -> bool:
    return path.suffix.lower() in FIXTURE_DATA_SUFFIXES and any(part in FIXTURE_DIR_MARKERS for part in path.parts)


def _scan_file(path: Path, fake_domains: set[str], findings: list[dict], literal_locations: dict[tuple[str, str], list[dict]], max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        findings.append({"file": str(path), "line": 0, "category": "scan-error", "detail": str(exc)})
        return
    if size > max_file_bytes:
        findings.append({
            "file": str(path), "line": 0, "category": "scan-error",
            "detail": f"skipped — {size} bytes exceeds the {max_file_bytes}-byte scan cap (--max-file-bytes to override)",
        })
        return
    try:
        text = path.read_text(errors="ignore")
    except OSError as exc:
        findings.append({"file": str(path), "line": 0, "category": "scan-error", "detail": str(exc)})
        return

    lines = text.splitlines()

    if _is_fixture_data_file(path):
        head = "\n".join(lines[:5])
        if not PROVENANCE_MARKERS.search(head) and not PROVENANCE_MARKERS.search(text[:2000]):
            findings.append({
                "file": str(path), "line": 1, "category": "fixture-missing-provenance",
                "detail": "no provenance marker (generated/anonymized/synthetic/faker/factory/_meta) in the first lines or top-level keys",
            })

    for lineno, line in enumerate(lines, start=1):
        for match in EMAIL_RE.finditer(line):
            domain = match.group(1)
            if not _is_fake_domain(domain, fake_domains):
                findings.append({"file": str(path), "line": lineno, "category": "pii-suspect-email", "detail": _mask(match.group(0))})
            else:
                literal_locations[("email", match.group(0).lower())].append({"file": str(path), "line": lineno})

        for match in PHONE_RE.finditer(line):
            digits = "".join(match.groups())
            if len(digits) != 10:
                continue
            if not _is_fake_phone(digits):
                findings.append({"file": str(path), "line": lineno, "category": "pii-suspect-phone", "detail": _mask(match.group(0))})
            else:
                literal_locations[("phone", digits)].append({"file": str(path), "line": lineno})

        for match in SSN_RE.finditer(line):
            area = match.group(1)
            if not _is_fake_ssn(area):
                findings.append({"file": str(path), "line": lineno, "category": "pii-suspect-ssn", "detail": _mask(match.group(0))})

        for match in CARD_RE.finditer(line):
            digits = re.sub(r"[ -]", "", match.group(0))
            if len(digits) < 13 or len(digits) > 19:
                continue
            if digits in KNOWN_TEST_CARDS:
                continue
            if not _luhn_valid(digits):
                continue
            # Luhn alone passes ~10% of random digit runs of the right length
            # (epoch-millis timestamps, trace IDs) — and a real issuer
            # prefix alone isn't enough either: a 16-digit trace ID that
            # happens to start with 4 is legitimately Visa-shaped by every
            # structural measure available to a regex. Both signals are
            # required together — an issuer prefix AND nearby card/pan/cc
            # context — since a non-card ID passing both by coincidence is
            # vanishingly rare, unlike either alone.
            if digits[0] not in CARD_ISSUER_PREFIXES or not _has_card_context(line):
                continue
            findings.append({"file": str(path), "line": lineno, "category": "pii-suspect-card", "detail": digits[:4] + "…" + digits[-4:]})


def _duplicate_literal_findings(literal_locations: dict[tuple[str, str], list[dict]]) -> list[dict]:
    findings = []
    for (kind, value), locations in literal_locations.items():
        distinct_files = {loc["file"] for loc in locations}
        if len(distinct_files) >= 3:
            findings.append({
                "file": sorted(distinct_files)[0], "line": locations[0]["line"],
                "category": "duplicated-literal-suggest-factory",
                "detail": f"{kind} value {value!r} hardcoded identically in {len(distinct_files)} files: {sorted(distinct_files)[:5]}",
            })
    return findings


def _render_markdown(findings: list[dict], scanned: int) -> str:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_category[f["category"]].append(f)

    lines = [f"## Test-data scan — {scanned} file(s) scanned, {len(findings)} finding(s)", ""]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines)
    for category in sorted(by_category):
        items = by_category[category]
        lines.append(f"### {category} ({len(items)})")
        for item in items[:25]:
            lines.append(f"- `{item['file']}:{item['line']}` — {item['detail']}")
        if len(items) > 25:
            lines.append(f"- … +{len(items) - 25} more")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan test/fixture files for PII-shaped literals, missing fixture provenance, and duplicated hardcoded values.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--path", nargs="+", default=["."], help="File(s), directory/directories, or glob pattern(s) to scan (default: cwd)")
    parser.add_argument("--include-glob", nargs="+", help="Override the default filename-selection globs (fnmatch, no '/'). Files under a fixtures/seeds/__fixtures__/factories directory are always included regardless of this flag.")
    parser.add_argument("--fake-domains", nargs="+", default=[], help="Additional email domains to treat as safe, beyond example.com/.net/.org and .test/.example/.invalid/.localhost")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", help="File path to write the report to (default: stdout)")
    parser.add_argument("--fail-on-finding", action="store_true", help="Exit 1 if any pii-suspect-* finding exists (fixture-missing-provenance and duplicated-literal findings never fail the build)")
    parser.add_argument("--exclude-dir", nargs="+", help="Extra directory name(s) to prune from the walk, in addition to the built-in node_modules/.venv/venv/dist/build/.git/target/vendor")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES, help=f"Skip scanning a file's content past this size in bytes (default {DEFAULT_MAX_FILE_BYTES}) — a fixtures/seeds/factories file is force-included regardless of suffix, so this is what keeps a binary seed dump from being read as text")
    args = parser.parse_args()

    include_globs = tuple(args.include_glob) if args.include_glob else DEFAULT_INCLUDE_GLOBS
    fake_domains = {d.lower() for d in args.fake_domains}
    exclude_dirs = DEFAULT_EXCLUDE_DIR_MARKERS | frozenset(args.exclude_dir or ())

    files = _iter_files(args.path, include_globs, exclude_dirs)
    findings: list[dict] = []
    literal_locations: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in files:
        _scan_file(path, fake_domains, findings, literal_locations, args.max_file_bytes)
    findings.extend(_duplicate_literal_findings(literal_locations))
    findings.sort(key=lambda f: (f["category"], f["file"], f["line"]))

    if args.format == "markdown":
        rendered = _render_markdown(findings, len(files))
    else:
        rendered = json.dumps({"filesScanned": len(files), "findings": findings}, indent=2)

    if args.output:
        Path(args.output).write_text(rendered + ("\n" if not rendered.endswith("\n") else ""))
        print(f"Test-data scan report written to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    pii_findings = [f for f in findings if f["category"].startswith("pii-suspect-")]
    print(f"{len(files)} file(s) scanned, {len(findings)} finding(s) ({len(pii_findings)} PII-suspect)", file=sys.stderr)
    if args.fail_on_finding and pii_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
