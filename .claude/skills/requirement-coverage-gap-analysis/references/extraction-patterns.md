# Extraction patterns — what `inventory_tests.py` catches and misses per stack

Regex extraction over one file at a time, no AST, no cross-file resolution — mirrors
`test-execution-history`'s "closest thing to a universal format" tradeoff, just for test *titles*
instead of test *results*. Read this before treating an empty or thin inventory for a file as
proof that file has no tests.

| Stack | Pattern matched | Grouping | Known gaps |
| --- | --- | --- | --- |
| Jest / Vitest / Mocha / Playwright | `it(`/`test(` string literal (any modifier: `.only`, `.skip`); `it.each`/`test.each` with a single-line `([...])`/`({...})` table argument or a single-line `` `...` `` template table, before the title | Nearest **enclosing** `describe(...)`, tracked by brace depth (a `{`/`}` count per line, not a real parser) — a test outside every `describe`, or a sibling test after a nested `describe` closes, correctly gets no prefix / the outer prefix rather than a stale inner one. Still collapses truly nested describes to the innermost when a test is genuinely inside more than one. | Brace counting doesn't distinguish a block brace from one inside a string, comment, or object literal — a `{`/`}` inside either can miscount depth for the rest of the file. `it.each`/`test.each` table-driven cases still produce one title per call site, not one per row (row data is a runtime value, invisible to a text scan) — the table-argument fix is about *finding* the title at all, not expanding per-row. A **multi-line** template-literal table (the closing `` ` `` on a different line than `` test.each` ``) is not matched — single-line only. |
| pytest | `def test_*(...)` | Enclosing `class Test*` (only when the `def` line is indented) becomes `ClassName::name` | `@pytest.mark.parametrize` collapses to the function name — the individual case IDs are runtime values, same limitation as `it.each` above. Fixtures named `test_*` by accident (rare, against convention) would be misread as tests. |
| Go (`go test`) | `func Test*(t *testing.T)` at column 0 | None (Go doesn't nest test names structurally) | Table-driven subtests (`t.Run(name, ...)` inside a `TestX`) are invisible — only the outer `TestX` is captured. |
| PHPUnit | `public function test*(...)` | None | Tests named via `@test` annotation on a non-`test`-prefixed method are not matched. `#[DataProvider]` cases collapse to one title, same limitation as parametrize. |
| RSpec | `it '...'` / `it "..."` | Nearest **enclosing** `describe`/`context`, tracked by `do`/`end` depth (a keyword count per line, not a real parser) — same enclosing-scope correctness as Jest above, not just nearest-preceding. | `do`/`end` counting doesn't distinguish a spec block from any other Ruby `do...end` (a loop, a `module`/`class`, a conditional) — one of those between/around describe blocks can miscount depth for the rest of the file. `it` blocks with no string (implicit description from the matcher) are not matched. **`describe`/`it` written with `{ }` instead of `do...end` are invisible** — only `do`/`end` is tracked, not curly braces, so a suite using brace-style blocks (rare for RSpec's own convention, which reserves `{ }` for short one-liners like `expect { ... }.to raise_error`, not `describe`/`it` themselves) extracts nothing. |
| .NET (xUnit/NUnit) | `[Fact]`/`[Theory]`/`[Test]` attribute followed by the next method signature | None | The method *name* is used as the title, not a `[Description]` attribute if one is set separately — a project that documents test intent only via `[Description]` will get uninformative titles here. `[Theory]`/`[TestCase]` inline data collapses to one title, same parametrize limitation. |
| Gherkin (`.feature`) | `Scenario:` / `Scenario Outline:` | `Feature:` is not captured as a prefix (kept flat) | `Examples:` table rows for a `Scenario Outline` are not expanded — one title per outline, not per example row. |
| Java (JUnit) | `@Test`/`@ParameterizedTest`/`@RepeatedTest` attribute followed by the next method signature | None | Method *name* is used as the title, not a `@DisplayName` annotation if one is set separately — a project documenting test intent only via `@DisplayName` gets uninformative titles here. `@ParameterizedTest`/`@CsvSource` cases collapse to one title, same parametrize limitation as pytest/PHPUnit above. An annotation with parameters spanning multiple lines (rare) is not matched. |

## Why regex instead of a parser

Test *titles* are string literals and method names — data, not syntax structure — so a parser has
nothing to query for "what does this test call itself." A text pass over test files is the right
tool for this specific extraction, same reasoning `test-execution-history` uses for JUnit XML over
a custom per-runner integration.
