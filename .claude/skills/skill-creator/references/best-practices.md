# Skill authoring best-practices checklist

The audit rubric for skill-creator's best-practices audit, distilled from Anthropic's skill-authoring best practices. Score the target skill against every item; each failing item is a finding to fix.

## Contents

- Frontmatter validity
- Writing effective descriptions
- Conciseness
- Degrees of freedom
- Progressive disclosure
- Workflows and feedback loops
- Content guidelines
- Scripts (skills with executable code)
- Anti-patterns

## Frontmatter validity

- `name`: ≤64 chars, lowercase letters / numbers / hyphens only; no XML tags; no reserved words (`anthropic`, `claude`). Prefer gerund or action form (`processing-pdfs`, `analyze-spreadsheets`); avoid vague names (`helper`, `utils`, `tools`).
- `description`: non-empty, ≤1024 chars, no XML tags.

## Writing effective descriptions

The description is how Claude picks this skill out of many, so it carries the most weight.

- **Third person always.** "Extracts text from PDFs…", never "I can help you…" or "You can use this to…".
- **What + when.** State what the skill does *and* the triggers/contexts for using it.
- **Concrete key terms.** Include the file types, tool names, and phrases a user would actually say.
- Bad: `Helps with documents` / `Processes data` / `Does stuff with files`.
- Good: `Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.`

## Conciseness

The context window is a shared public good. Assume Claude is already smart.

- Challenge each sentence: "Does Claude really need this? Can I assume it already knows this? Does this paragraph justify its token cost?"
- Cut background explanations of well-known concepts (what a PDF is, how libraries work).
- Keep the SKILL.md body under 500 lines.

## Degrees of freedom

Match specificity to the task's fragility.

- **High freedom** (prose steps) — many valid approaches, context-dependent decisions. E.g. code review.
- **Medium freedom** (pseudocode / parameterized scripts) — a preferred pattern with acceptable variation.
- **Low freedom** (exact scripts, few params) — fragile, consistency-critical, must run in sequence. E.g. migrations. Say "run exactly this; do not modify".

Over-constraining an open task wastes tokens; under-constraining a fragile one causes errors.

## Progressive disclosure

- SKILL.md is a table of contents that points to detail loaded on demand.
- Move large or specialized content into separate files (`reference/finance.md`, `FORMS.md`).
- **References must be one level deep from SKILL.md.** No SKILL → a.md → b.md chains — Claude may only partially read nested files.
- Reference files longer than 100 lines get a table of contents at the top.
- Name files by content (`form_validation_rules.md`), not `doc2.md`.

## Workflows and feedback loops

- Break complex tasks into clear sequential steps; offer a copyable checklist for multi-step work.
- Add validate → fix → repeat loops for quality-critical tasks ("only proceed when validation passes").
- Create verifiable intermediate outputs (plan → validate plan → execute) for batch or high-stakes operations.

## Content guidelines

- **No time-sensitive info.** Don't write "before August 2025 use the old API". Put deprecated behavior in a collapsed "Old patterns" section instead.
- **Consistent terminology.** Pick one term (always "field", always "extract") and use it throughout.
- **Concrete examples over abstract description** — show input/output pairs where output quality depends on style.
- **Templates** for output formats; match strictness (exact template vs. sensible default) to need.

## Scripts (skills with executable code)

- **Solve, don't punt.** Handle error conditions in the script rather than failing and leaving Claude to figure it out.
- **No voodoo constants.** Justify and document every configuration value; no unexplained magic numbers.
- **Provide utility scripts** for deterministic operations — more reliable and cheaper than regenerating code each run.
- **Make execution intent explicit**: "Run `analyze.py` to extract fields" (execute) vs. "See `analyze.py` for the algorithm" (read).
- **Don't assume packages are installed** — state dependencies and install commands.

## Anti-patterns

- **Windows-style paths.** Always forward slashes (`scripts/helper.py`), never backslashes — they break on Unix.
- **Too many options.** Give one default with an escape hatch, not "use pypdf, or pdfplumber, or PyMuPDF, or…".
- **Unqualified MCP tool names.** Always `ServerName:tool_name` (e.g. `GitHub:create_issue`), or Claude may not find the tool.

## Final verification

Before declaring the skill improved, confirm:

- Description is specific, third person, states what + when, includes key terms.
- SKILL.md body under 500 lines; detail split into one-level-deep reference files.
- No time-sensitive info; consistent terminology; concrete examples.
- Forward-slash paths; qualified MCP names; a default rather than many options.
- For scripts: explicit error handling, documented constants, stated dependencies.
