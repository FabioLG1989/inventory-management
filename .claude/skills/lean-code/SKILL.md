---
name: lean-code
description: Write the minimum code that fully solves the problem and review changes for over-engineering. Use when asked to minimize code, simplify or shrink a change, decide "is this over-engineered", figure out "what can we delete", reuse-before-building, fix a bug at its root cause, or "review for over-engineering". Provides a reuse-first decision ladder, a non-negotiable "do not cut corners on" safety list, and a delete/stdlib/native/yagni/shrink over-engineering review with a "net: -N lines possible" metric.
---

# Lean Code

You write the minimum code that fully solves the problem, and not one line more. Lean means efficient, not careless — the best code is the code you never had to write. This skill governs minimal-code methodology — apply it whenever you write or review code. It does not override security, testing, or correctness guidance from other skills; the "Do NOT cut corners on" list below is the explicit boundary.

Lean is never about fewest tokens or golfed one-liners. It is about not building what the problem does not require, and not re-building what already exists.

## Understand first, then climb the ladder

The ladder below runs **after** you understand the problem, never instead of it. First read the task and the code it touches, trace the real flow end to end, and confirm where the change actually belongs. The smallest change in the wrong place is not lean — it is a second bug. A small diff you do not understand is laziness dressed up as efficiency.

Once you understand the problem, stop at the **first rung that holds**. This is a cheap short-circuit, not a checklist to fully traverse. When two rungs both work, take the higher (less-code) one and move on.

1. **Does this need to exist at all?** Question scope before writing. If a requested feature, abstraction, config knob, or layer has no caller and no current need, say so in one line and do not build it.
2. **Does it already exist in this codebase?** Search the repo for an existing helper, utility, type, or pattern and reuse it. Reuse-first is the highest-value rung — duplicated logic is the most common form of AI slop.
3. **Does the language's standard library do it?** If the stdlib ships it, call it instead of hand-rolling it.
4. **Does a built-in feature of the detected platform/framework cover it?** Consult the project's discovered stack profile (`.claude/framework-config.json` and its `by_service` map) and use the platform's native capability rather than re-implementing it in application code. Phrase this for the stack you are actually in — a database constraint, a framework lifecycle hook, a runtime built-in — never assume a web frontend.
5. **Does an already-installed dependency solve it?** Reach for a dependency the project already has before adding a new one. Do not add a new dependency for what a few lines of your own would do.
6. **Can it be one small, clear change?** Prefer the smallest coherent edit that a reviewer can read at a glance.
7. **Only then, write the minimum code that works.** Correct, readable, and no broader than the problem.

## Fix bugs at the root, not the symptom

The root-cause fix is the lean move, because it is the smaller diff. Before changing a function, find **every caller** of it and fix the shared function once. One guard in the shared function is a smaller diff than one guard per caller — and patching only the path the ticket names leaves a sibling caller still broken. Trace the data flow to the function that is actually wrong; do not bandage the call site that happened to surface the symptom.

## Directive rules

- **Reuse before you write.** Search for the existing helper/pattern first; a second copy of logic is a liability, not a feature.
- **Deletion over addition.** The strongest change is often removing code. Prefer cutting to adding.
- **Boring over clever.** Clever is what someone has to decode at 3am. Write the obvious version.
- **Shortest working diff wins** — but only once you understand the problem. Fewest files touched, smallest coherent change.
- **No unrequested abstractions.** No new interface, factory, wrapper, or config layer until there is a second real caller. One implementation does not justify an abstraction.
- **No new dependency if it can be avoided.** A few lines you own beat a dependency you must track, update, and audit.
- **No boilerplate nobody asked for.** Do not scaffold flexibility for a future that has not arrived.
- **Question over-scoped requests.** When a request looks larger than the problem, ask: "Do you actually need X, or does Y already cover it?" before building X.
- **When two equal-size options exist, pick the edge-case-correct one.**

## Output discipline

State the change first. Then, if you intentionally simplified something, add at most a short bounded note: **what you skipped, and the trigger to add it later** — in the form `skipped: <X>; add when <Y>`. If the explanation is longer than the change, the explanation is the bug — every paragraph defending a simplification is complexity smuggled back in as prose.

**Record intentional simplifications in the PR description, never as inline comments.** This framework forbids comments inside function bodies. When you deliberately take a shortcut with a known ceiling, write a structured line in the PR description: `Simplified <X>; ceiling: <Y>; upgrade when: <Z>`. When the function itself carries a deliberate limitation a future maintainer must know about, state that limitation in the function's JSDoc/docstring. A simplification with no recorded upgrade trigger is the kind that silently rots — always name the trigger.

## Do NOT cut corners on

Lean reduces what is unnecessary. It never reduces what keeps the software correct and safe. Never simplify away:

- **Understanding the problem.** The ladder is worthless if you skip the read-and-trace step first.
- **Input validation at trust boundaries.** Every input that crosses a trust boundary (user input, network, file paths, deserialization) gets validated. The few lines you are tempted to drop are often the path-traversal or injection guard.
- **Error handling that prevents data loss.** Handle the failure paths that could corrupt, lose, or partially write data.
- **Security.** Authentication, authorization, secret handling, and injection defenses are never the line you cut to save a diff.
- **Accessibility.** Where the platform exposes it, accessible behavior ships by default.
- **Anything explicitly requested.** If the task asked for it, it is in scope. Lean trims what was not asked for, not what was.
- **Leaving a test behind.** Non-trivial logic ships with the smallest runnable check that fails if the logic breaks, using the **project's detected test runner and following the Testing rules in the service page's `## Conventions & How-To` (`docs/llm-wiki/wiki/services/<id>.md`)**. Trivial one-liners need none — YAGNI applies to tests too — but do not skip the check on real logic.

## Reviewing for over-engineering

This is a **read-only** pass: list findings, apply nothing. Scope is **over-engineering and complexity only**. Correctness bugs, security holes, and performance are explicitly **out of scope** — route those to a normal correctness review (the `pr-reviewer` and `security-review` skills). Never flag a project-test-runner check required by the service page's `## Conventions & How-To` Testing rules for deletion — that check is the minimum, not waste.

**Scope.** Default to the current diff. Say `audit` for repo-wide, ranked biggest-cut-first.

**Tags** (one per finding):

- `delete` — dead code, unused flexibility, or a speculative feature. Replacement is nothing.
- `stdlib` — a hand-rolled thing the standard library already ships. Name the function.
- `native` — a dependency or code doing what the platform/framework already does. Name the feature.
- `yagni` — an abstraction with one implementation, a config nobody sets, or a layer with one caller. Inline or remove it until a second caller exists.
- `shrink` — same logic, fewer lines. Show the shorter form.

**Finding format** — one line per finding, no prose:

- Diff scope: `L<line>: <tag> <what>. <replacement>.`
- Multi-file diff: `<file>:L<line>: <tag> <what>. <replacement>.`
- Audit scope (ranked, biggest cut first): `<tag> <what to cut>. <replacement>. [<path>]`

Every finding states location, what to cut, and what replaces it — nothing more.

**Examples** (stack-neutral illustrations, not the assumed stack):

- `L12-38: stdlib: 27-line validator class. "@" presence check, 1 line — real validation is the confirmation step.`
- `L4: native: a date library imported for one format call. The platform's built-in formatter, 0 deps.`
- `repo:L88: yagni: abstract repository with one implementation. Inline it until a second one exists.`
- `L52-71: delete: retry wrapper around an idempotent local call. Nothing replaces it.`
- `L30-44: shrink: manual loop building a map. Build it directly from the key/value pairs, 1 line.`

Do **not** hedge in prose. A finding is not "This class might be more complex than necessary, have you considered…"; it is the terse tagged line above.

**Audit hunt list:** dependencies the stdlib or platform already ships, single-implementation interfaces, factories with one product, wrappers that only delegate, files exporting one thing, dead flags and config nobody sets, hand-rolled reimplementations of stdlib.

**Close with the only metric that matters:**

- Diff: `net: -<N> lines possible.`
- Audit: `net: -<N> lines, -<M> deps possible.`
- Nothing to cut: `Lean already. Ship.` — then stop.

---

Methodology credited to ponytail: https://github.com/DietrichGebert/ponytail (MIT).
