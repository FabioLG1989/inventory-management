# Output Formatting

Everything this skill prints to the conversation — Phase 0's detection announcement, Phase 2's evidence summary, and Phase 4's bug cards — is Markdown, not plain text: headings, tables, and bold labels, so it renders as readable cards rather than a wall of indented text. This is what Phase 0/1/2 already template above; this section is the canonical spec for Phase 4's per-bug card, the part with the most fields to get right.

**Severity/priority emoji legend** — use consistently, never invent alternate icons for the same level:

| Severity | Icon | Priority | Icon |
|---|---|---|---|
| blocker | ⛔ | urgent | 🔺 |
| critical | 🔴 | high | 🔶 |
| major | 🟠 | medium | 🔸 |
| minor | 🟡 | low | 🔻 |
| trivial | ⚪ | | |

**Per-bug card template** (`<title>` here is the canonical `title` field verbatim, `[BUG] ` prefix included — see [Canonical Bug Format](canonical-format.md) — so the chat preview always matches what actually gets filed):
```
## Bug N — <title>

| Field | Value |
|---|---|
| Severity | <icon> <Severity> |
| Priority | <icon> <Priority> |
| Reproducibility | <only include this row when `reproducibility` is `"intermittent"` or `"once"` — see the rule below the table> |
| Regression | ✅ Yes \| ❌ No \| ❓ Unknown — last good: `<sha-or-null>` |
| Test | `<test_reference.framework>` — `<test_reference.test_name>` (omit this row entirely when `test_reference.framework` is `null`, e.g. `--from-text`/`--from-ticket`) |
| Ticket | <only present on Phase 5's post-publish block — see below; always omitted on the Phase 4 preview card, since nothing has been filed yet at that point> |

**Expected:** <expected_result>
**Actual:** <actual_result>

> 💡/⚠️ <optional one-line callout — shared root cause with another bug in this batch, a code comment marking it as an intentionally-seeded/test-fixture bug, a flaky signal, etc. Omit the blockquote line entirely when there's nothing worth flagging — don't manufacture one to fill the template.>

---
```
Use 💡 for a neutral/informational callout (e.g. "shares root cause with Bug 1") and ⚠️ for something that should give the user pause before filing (e.g. "this looks like an intentionally-seeded test-fixture bug, not a real defect").

**This callout is for the human deciding whether to file — it never goes into the filed ticket/defect body itself**, in either adapter. Once the human has seen it here and said "file it anyway," repeating "this is an intentionally-seeded fixture bug" inside the ticket adds nothing a developer fixing it needs; it's report-bug's own bookkeeping, the same category of noise as the other meta-explanations this section already rules out (see the `regression`/`priority`/`environment` rows in each adapter's field mapping table).

**Show `Reproducibility` only for `"intermittent"`/`"once"`.** `"always"` is the default for anything that cleared Phase 2's confirmation, so omit the row — on the preview, on the post-publish card, and in every adapter's payload (no restating it inside a description or comment either).

**The `Ticket` row** only appears on a Phase 5 post-publish card — the Phase 4 preview card never has it, since nothing has been filed yet at that point (this is true whether or not a `--to-*` flag was passed at invocation: the preview always comes first, see [Phase 4](../SKILL.md#phase-4-generate-the-canonical-bug-report)). Its value depends on what actually happened to that candidate:

| Outcome | `Ticket` row value |
|---|---|
| Created | `✅ [<KEY-or-ID>](<URL>)` — e.g. `✅ [KAN-8](https://site.atlassian.net/browse/KAN-8)` |
| Linked as duplicate instead of filed | `🔗 Linked as duplicate of [<KEY-or-ID>](<URL>)` |
| Written to a local file (`--to-markdown`) | `📝 Written to \`<path>\`` |
| Publish call failed | Do not add this row at all — an error follows the adapter's error template instead, and the full canonical report is reprinted per [Error Handling](../SKILL.md#error-handling) rather than folded into a card. |

The card **is** each adapter's success report. An adapter file may still call out one adapter-specific detail (e.g. Jira's evidence-as-comment status) as an extra short line directly under the table, but it should not re-print the same severity/priority/expected/actual fields in a second, differently-shaped block.

**Worked example** (from a `--from-run` batch of 2, abbreviated):
```
## Bug 1 — [BUG] [UI] Cart | Subtotal ignores quantity for a repeated item

| Field | Value |
|---|---|
| Severity | 🔴 Critical |
| Priority | 🔺 Urgent |
| Regression | ✅ Yes — last good: `88b125a` (broken by the *uncommitted* change in js/app.js) |
| Test | Playwright — `cart.spec.ts › cart subtotal reflects the quantity of a repeated item` |

**Expected:** cart-subtotal shows $24.00 for 2× Ceramic Mug ($12.00 each)
**Actual:** shows $12.00 (qty ignored)

---

## Bug 2 — [BUG] [UI] Checkout | Order total ignores quantity for a repeated item

| Field | Value |
|---|---|
| Severity | 🔴 Critical |
| Priority | 🔺 Urgent |
| Regression | ✅ Yes — last good: `88b125a` (same root cause as Bug 1, `cartSubtotal()` in js/app.js:138) |
| Test | Playwright — `checkout.spec.ts › order total accounts for a repeated item's quantity` |

**Expected:** item-total shows $24.00 for 2× Ceramic Mug
**Actual:** shows $12.00 (qty ignored)

> 💡 Bugs 1 and 2 share one root cause (`cartSubtotal()` not multiplying by `line.qty`) but were kept separate since they're different files/pages.

---

### ❓ Which of these should I file?

Reply **all**, **none**, or **select** to pick specific bugs.

### 📤 Where should I publish them?

You can pick **more than one** (e.g. "Jira and Linear"):
- [ ] Qase — project `QA`
- [ ] Jira — project `KAN`
- [ ] Linear — team `ENG`
- [ ] Markdown file — `bug-reports/`
```
This closing block is the **text fallback** only — with an ask tool the same questions go through consecutive ask calls (bugs first, the checklist on `Select Bugs to Report`, then destination) per [Phase 4](../SKILL.md#phase-4-generate-the-canonical-bug-report). The ask is mandatory on every batch; never soften it into a plain trailing sentence.
