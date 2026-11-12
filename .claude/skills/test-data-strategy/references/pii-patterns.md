# PII patterns — exact rules behind `scripts/scan_test_data.py`

What the scanner flags, why those specific thresholds, and a safe-placeholder cheat sheet. Read
this before deciding a finding is a false positive — the rules below are deliberately
standards-based (RFC-reserved domains, NANP/SSA-reserved ranges, published test card numbers)
rather than arbitrary, so a finding usually means the value really isn't one of the documented-safe
forms.

## Email — `pii-suspect-email`

Safe: the domain is `example.com`, `example.net`, or `example.org` (reserved for documentation by
[RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)), or ends in `.test`, `.example`, `.invalid`, or
`.localhost` (reserved TLDs, RFC 2606 / [RFC 6761](https://www.rfc-editor.org/rfc/rfc6761)), or is
listed in `--fake-domains`.

Flagged: any other domain — including a real corporate or personal domain, even one that looks
internal-only. A domain a project owns is not automatically safe: it can still resolve to a real
mailbox, and a leaked address there is still a real person's data.

**Use instead**: `alice@example.com`, `test-user-42@example.com`. Never a real teammate's,
customer's, or ticket-reporter's address, even as a "just for this one test" shortcut.

## Phone — `pii-suspect-phone`

Matched at all only when the 3-3-4 groups have an explicit separator (space, dot, or dash) between
them — a bare 10-digit run with no separator is not matched as a phone number. This is a
deliberate precision tradeoff: without it, the pattern matches *any* 10-digit run, and a plain
numeric ID or a truncated timestamp is exactly 10 digits often enough to make `--fail-on-finding`
break CI on ordinary code. The cost is a real, unformatted phone number (`5551234567`) going
unflagged — accepted because unformatted phone literals are rare in test data and a false CI
failure on unrelated code is the worse outcome.

Safe (of what's matched): a 10-digit NANP number where the exchange is `555` and the line number
is in `0100`–`0199` — the block NANP officially reserves for fictional use in film, TV, and, by
extension, test data.

Flagged: any other separated 10-digit sequence in phone-shaped punctuation, including other `555`
numbers — `555-1234`-style non-`01XX` numbers were never reserved and many are real assigned lines
today.

**Use instead**: `555-0100` through `555-0199` (e.g. `555-555-0142`).

## SSN — `pii-suspect-ssn`

Safe: area number `000`, `666`, or `900`–`999` — the [SSA has never issued](https://www.ssa.gov/employer/randomization.html)
an SSN in these ranges, so a value shaped like one there cannot collide with a real person's.

Flagged: any other area number in `###-##-####` shape — most of those are structurally valid and
some are issued.

**Use instead**: `000-00-0000`, `666-12-3456`, `900-00-0000`.

## Payment card — `pii-suspect-card`

Safe: an exact match against a published test card number (Visa `4111111111111111`, Mastercard
`5555555555554444`, Amex `378282246310005`, Discover `6011111111111117`, and similar — see the
`KNOWN_TEST_CARDS` set in the script for the full list; card networks publish these specifically
for test/sandbox use), or any digit run that **fails** the Luhn checksum — a Luhn-invalid number
cannot be a real, issuable card number under any network's numbering rules, so it poses no
real-data risk regardless of how it was chosen.

Flagged (of what passes the safe check above): a 13–19 digit run (with optional space/dash
separators) that passes the Luhn checksum, starts with a real issuer prefix (`3`/`4`/`5`/`6`), AND
has `card`, `pan`, or `cc` as its own identifier segment somewhere on the line — a standalone word
(`const pan = …`), or a component of a compound name: `cardNumber`, `card_number`, `CARD_NUMBER`,
`creditCard`, `ccNumber` all count, split the way a human reads the identifier rather than matched
as a bare substring (a bare substring search for `pan`/`cc` would also match inside ordinary words
like `company`, `japan`, `access`, `success` — see `_has_card_context` in the script). All three
signals are required together, not any one alone — measured over 200k samples, ~10% of random
epoch-millisecond timestamps and ~10% of random 16-digit IDs are Luhn-valid by chance, and a real
issuer prefix doesn't rule those back out either: a 16-digit trace ID that happens to start with
`4` is Visa-shaped by every structural test a regex can run. Card/pan/cc context is what actually
distinguishes "this is a card number" from "this is a coincidentally card-shaped ID," so it's
required rather than optional. The tradeoff: a real card number with no naming context nearby (a
bare `const x = '4111...'` with an uninformative variable name and no comment) goes unflagged —
the known-test-card exact-match list still catches the
overwhelmingly common case of test code using a published test number, and requiring context is
what keeps a clean codebase's IDs and timestamps out of `--fail-on-finding`'s way.

**Use instead**: the payment gateway/PSP's own published sandbox card numbers (Stripe, Braintree,
Adyen, etc. all publish a test-card table) — prefer those over the generic list above when a
specific gateway is being tested, since some gateways special-case their own numbers for specific
decline/3DS scenarios.

## Fixture provenance — `fixture-missing-provenance`

Any `.json`/`.yaml`/`.yml`/`.csv` file under a `fixtures/`, `seeds/`, or `__fixtures__/` directory
is expected to say, in its first few lines or top-level keys, where its data came from — a
`// generated` / `# synthetic` comment, a `_provenance`/`_meta` key, or a reference to the factory/
faker call that produced it. This is a presence check on that marker, not a content check: it
cannot tell a true "generated" comment from a false one, only that no comment exists at all.

**Why this matters**: a `.json` fixture with no provenance marker is indistinguishable, by
inspection, from an anonymization pass that missed a field, or a real data export someone dropped
in "temporarily." The marker is the cheap thing that makes the distinction inspectable later,
including by someone with no context on how the file was created.

## What this scanner does not catch

- **Real names.** No stdlib name database exists to tell `Alice Chen` (placeholder, matches the
  `Alice`/`Bob` convention already used in this framework's own [pytest-patterns](../../pytest-patterns/SKILL.md)
  and [e2e-test-architecture](../../e2e-test-architecture/references/helpers-and-fixtures.md) examples)
  from a real customer's name. Prefer instantly-recognizable placeholder names (`Alice`, `Bob`,
  `Test User`, `Jane Q. Public`) over anything that reads as a plausible real person.
- **Addresses, government IDs other than SSN, biometric data, auth tokens/secrets.** Out of scope
  for a regex scanner — review these by hand, and never commit a real one even temporarily.
- **Values assembled at runtime** (string concatenation, values read from environment variables or
  an external file) — the scanner only sees literal text in the file it's reading.
- **Base64/URL-encoded or otherwise obfuscated PII** — decoded values are invisible to a text scan.

None of the above make the scanner's silence proof of cleanliness — see [SKILL.md](../SKILL.md)'s
no-PII rule for what still needs a human read.
