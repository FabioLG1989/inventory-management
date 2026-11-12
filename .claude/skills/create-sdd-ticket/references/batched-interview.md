# Batched Product Interview (MCP ask channel)

Load this file only when Phase 3 routes to the MCP block (`QAF_ASK_USER_MCP_TOOL` is set). Interactive and headless runs keep Phase 3 exactly as written in `SKILL.md`.

An MCP ask channel is usually asynchronous: the questions go to a web UI, a chat, or a ticket comment, and the run pauses until someone answers. Asking one question per call would cost the PM one full round trip per question. Over MCP the interview therefore runs in batched rounds. This file replaces only the one-question-per-turn sequencing of Phase 3 (including `grill-me`'s one-question-per-turn rule); everything else in Phase 3 still applies: the Gap Classifier output, the topic list and its dependency order, the question format (2 or 3 concrete options, recommended first with ` (Recommended)`, the Delegate option appended by `jq`), evidence for every recommendation, and product-only scope. Where this file and `SKILL.md` differ, this file wins over MCP.

## One batch per round

Draft a question for every field in `productGaps[]`, in topic order, and send each round in a single ask-channel call: an asynchronous channel pauses the run after each call, so every extra call is another round trip for the PM. A second round is fine for dependent questions that would otherwise rest on a guess (for example, scenarios after an open-ended core-behavior question): hold them for the next round and draft them against the real answers.

## Dependent questions

Scope, scenarios, and edge cases build on the answers about users and core behavior. Draft each dependent question against the **recommended** answer of the question it depends on, and name that assumption in the question's context by the question it depends on, never by its position, since each channel numbers questions its own way (e.g. `Assumes primary users = Admin users`).

## Follow-up round, only on conflict

When the batch returns, check every answer against the assumptions the other questions were drafted on. An answer conflicts when it departs from its recommendation (another concrete option or Other) and a question drafted on that recommendation no longer fits. Re-draft only the invalidated questions against the real answers and ask them in one follow-up round, then run the same check on its answers. Never adjust an answered question to fit on your own: that decides product scope without the PM. A Delegate answer is not a conflict: dependent answers stand, and the delegated item records the recommendation they were drafted on. A delegated question keeps its Delegate answer and is not asked again, unless a conflicting answer invalidated the assumption it was drafted on: then it is invalidated like any other dependent question and joins the follow-up round, re-drafted against the real answers, and the PM may delegate it again. With no conflicts, the interview is a single round.

**Stop criterion:** every product-judgment field is PM-confirmed or PM-delegated, and no answer conflicts with another.

## Topic adjustments

- **Topic 3 (Scope):** always include the INVEST sizing question in the batch, even when the scope question itself is skipped because comments already settled it: "Is this one coherent, independently-valuable behavior increment a team could deliver in a sprint?" Phase 5 reads this answer for **Small** instead of asking the PM in a separate round.
- **Topic 5 (BDD scenarios):** add one question per main journey to the batch, each proposing a full Given-When-Then draft: happy path, edge case, error/failure path, and (if applicable) a permission scenario. Draft at least 3 (happy + edge + error). A delegated scenario counts toward that minimum: in Phase 6 it keeps its recommended draft, tagged `(delegated)`, and is cross-listed under `## Open Questions & Delegated Decisions`.
