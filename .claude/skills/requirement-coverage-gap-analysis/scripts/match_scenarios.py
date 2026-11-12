"""Fuzzy prefilter between a requirement-derived scenario list and an
existing test inventory, so an agent only has to read and adjudicate the
ambiguous middle band instead of every scenario against every existing test.

This is a token-overlap + string-similarity heuristic (stdlib `difflib`,
no embeddings, no network) — it is a prefilter, not the final answer. Only
`needs-review` is meant for a human/agent to actually decide; `auto-covered`
and `likely-gap` are provisional labels cheap enough to compute over a large
suite, not a verdict. See SKILL.md's workflow for how the three bands are
meant to be used.

Input contract:
  --scenarios <path.json>   {"scenarios": [{"id": str, "text": str, "category": str?}, ...]}
  --inventory <path.json>   scripts/inventory_tests.py's own --format json output
                             ({"tests": [{"file", "line", "title", "framework"}, ...]})

--scenarios is typically agent-generated from ticket prose, so a malformed
entry in an otherwise-good batch is expected, not exceptional: an entry
missing 'text' (or an inventory entry missing 'title') is skipped and
reported (stderr, plus skippedScenarios/skippedInventory in the JSON output)
rather than aborting the whole run — see _validate_scenarios/_validate_inventory.
`id` defaults to `S<n>` (1-indexed) when absent so a report is still
readable without one.
"""

from __future__ import annotations

import argparse
import difflib
import heapq
import json
import re
import sys
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "to", "of", "is", "are", "was", "were", "be", "been",
    "on", "in", "at", "for", "with", "and", "or", "not", "this", "that",
    "it", "its", "as", "by", "should", "when", "then", "given", "can",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _score(scenario_text: str, title: str) -> float:
    seq_ratio = difflib.SequenceMatcher(None, scenario_text.lower(), title.lower()).ratio()
    jaccard = _jaccard(set(_tokens(scenario_text)), set(_tokens(title)))
    return round((seq_ratio + jaccard) / 2, 4)


def _band(score: float, high: float, low: float) -> str:
    if score >= high:
        return "auto-covered"
    if score >= low:
        return "needs-review"
    return "likely-gap"


def _load_json_list(path: str, key: str, flag_name: str) -> list:
    """Load `path` as JSON and return the list at `key`, or exit(1) with a
    clear message — for any shape problem, not just the ones a bare
    try/except on the top-level `json.loads(...)[key]` catches. A bare
    list/string/null at the top level, or `key` present but not a list,
    used to reach `_validate_scenarios`/`_validate_inventory` and crash
    there instead (a JSON string is iterable character-by-character in
    Python, so it silently produced N bogus 'malformed entry' warnings
    instead of the one real error: wrong shape entirely).
    """
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {flag_name} '{path}': {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        print(f"ERROR: {flag_name} '{path}' must be a JSON object with a '{key}' list", file=sys.stderr)
        sys.exit(1)
    return data[key]


def _validate_scenarios(raw: list) -> tuple[list[dict], list[str]]:
    """Keep only scenarios with a usable 'text'; report, don't raise, on the
    rest — --scenarios is agent-generated from ticket prose, so one
    malformed entry in an otherwise-good batch is likely, and it must not
    abort the whole run."""
    valid: list[dict] = []
    skipped: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            skipped.append(f"scenarios[{i}]: missing or empty 'text'")
            continue
        entry = dict(item)
        entry.setdefault("id", f"S{i + 1}")
        entry.setdefault("category", None)
        valid.append(entry)
    return valid, skipped


def _validate_inventory(raw: list) -> tuple[list[dict], list[str]]:
    """Same as _validate_scenarios, for the inventory's 'title' field."""
    valid: list[dict] = []
    skipped: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not item["title"].strip():
            skipped.append(f"tests[{i}]: missing or empty 'title'")
            continue
        entry = dict(item)
        entry.setdefault("file", "<unknown>")
        entry.setdefault("line", 0)
        entry.setdefault("framework", None)
        valid.append(entry)
    return valid, skipped


def _match(scenario: dict, inventory: list[dict], top_k: int) -> dict:
    """Score every inventory title against this scenario and keep the best
    `top_k` — same result as scoring everything with `_score` and slicing
    the top `top_k`, but skips the expensive `SequenceMatcher.ratio()` call
    where it can't change the outcome. `quick_ratio()` is a cheap O(n+m)
    upper bound on `ratio()` (guaranteed >= it), so once `top_k` exact scores
    are already known, any later entry whose best-possible combined score
    can't beat the current worst kept one is skipped before ever computing
    its real score. Never replaces a kept entry on an exact tie, matching
    the original stable-sort-then-slice behavior of preferring the
    earlier-indexed entry."""
    if top_k <= 0:
        return {"scenario": scenario, "candidates": []}
    scenario_text = scenario["text"].lower()
    scenario_tokens = set(_tokens(scenario["text"]))
    heap: list[tuple[float, int, dict]] = []
    for i, entry in enumerate(inventory):
        title = entry["title"]
        title_tokens = set(_tokens(title))
        jaccard = _jaccard(scenario_tokens, title_tokens)
        matcher = difflib.SequenceMatcher(None, scenario_text, title.lower())
        if len(heap) >= top_k:
            best_possible = (matcher.quick_ratio() + jaccard) / 2
            if best_possible <= heap[0][0]:
                continue
        score = round((matcher.ratio() + jaccard) / 2, 4)
        scored_entry = {**entry, "score": score}
        if len(heap) < top_k:
            heapq.heappush(heap, (score, -i, scored_entry))
        elif score > heap[0][0]:
            heapq.heapreplace(heap, (score, -i, scored_entry))
    ordered = sorted(heap, key=lambda item: (-item[0], -item[1]))
    return {"scenario": scenario, "candidates": [item[2] for item in ordered]}


def _render_markdown(results: list[dict], summary: dict[str, int], skipped_scenarios: list[str], skipped_inventory: list[str]) -> str:
    lines = [
        f"## Scenario match — {summary['autoCovered']} auto-covered, "
        f"{summary['needsReview']} needs-review, {summary['likelyGap']} likely-gap",
        "",
    ]
    if skipped_scenarios or skipped_inventory:
        lines.append(
            f"⚠️ Skipped {len(skipped_scenarios)} malformed scenario entries and "
            f"{len(skipped_inventory)} malformed inventory entries — see stderr for detail.",
        )
        lines.append("")
    for r in results:
        top = r["candidates"][0] if r["candidates"] else None
        band = r["band"]
        marker = {"auto-covered": "✅", "needs-review": "⚠️", "likely-gap": "❌"}[band]
        lines.append(f"### {marker} {r['scenario']['id']} — {r['scenario']['text']}")
        if top:
            lines.append(f"- Best match ({top['score']}): `{top['file']}:{top['line']}` — {top['title']}")
        else:
            lines.append("- No candidates in inventory")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fuzzy-prefilter requirement scenarios against an existing test inventory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scenarios", required=True, help="Path to scenarios JSON (see module docstring for shape)")
    parser.add_argument("--inventory", required=True, help="Path to inventory_tests.py's JSON output")
    parser.add_argument("--high-threshold", type=float, default=0.72, help="Score at/above which a scenario is 'auto-covered' (default 0.72)")
    parser.add_argument("--low-threshold", type=float, default=0.35, help="Score below which a scenario is 'likely-gap' (default 0.35)")
    parser.add_argument("--top-k", type=int, default=3, help="Candidate matches kept per scenario (default 3)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", help="File path to write the report to (default: stdout)")
    args = parser.parse_args()

    raw_scenarios = _load_json_list(args.scenarios, "scenarios", "--scenarios")
    raw_inventory = _load_json_list(args.inventory, "tests", "--inventory")

    scenarios, skipped_scenarios = _validate_scenarios(raw_scenarios)
    inventory, skipped_inventory = _validate_inventory(raw_inventory)
    for message in skipped_scenarios + skipped_inventory:
        print(f"WARNING: skipping malformed entry — {message}", file=sys.stderr)

    if args.high_threshold <= args.low_threshold:
        print(f"ERROR: --high-threshold ({args.high_threshold}) must be greater than --low-threshold ({args.low_threshold})", file=sys.stderr)
        sys.exit(1)

    results = []
    summary = {"autoCovered": 0, "needsReview": 0, "likelyGap": 0}
    for scenario in scenarios:
        matched = _match(scenario, inventory, args.top_k)
        top_score = matched["candidates"][0]["score"] if matched["candidates"] else 0.0
        band = _band(top_score, args.high_threshold, args.low_threshold)
        summary[{"auto-covered": "autoCovered", "needs-review": "needsReview", "likely-gap": "likelyGap"}[band]] += 1
        results.append({"scenario": scenario, "band": band, "candidates": matched["candidates"]})

    if args.format == "markdown":
        rendered = _render_markdown(results, summary, skipped_scenarios, skipped_inventory)
    else:
        rendered = json.dumps(
            {"summary": summary, "results": results, "skippedScenarios": skipped_scenarios, "skippedInventory": skipped_inventory},
            indent=2,
        )

    if args.output:
        Path(args.output).write_text(rendered + ("\n" if not rendered.endswith("\n") else ""))
        print(f"Match report written to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    skip_note = f" ({len(skipped_scenarios)} scenario(s)/{len(skipped_inventory)} inventory entry(s) skipped as malformed)" if (skipped_scenarios or skipped_inventory) else ""
    print(
        f"{len(scenarios)} scenario(s) vs {len(inventory)} existing test(s): "
        f"{summary['autoCovered']} auto-covered, {summary['needsReview']} need review, {summary['likelyGap']} likely gaps{skip_note}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
