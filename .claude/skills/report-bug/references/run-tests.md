# Running the suites (`--run`)

`--run` runs the project's E2E suites itself, writes each runner's report under `.claude-temp/report-bug/run/`, and hands the result to the same flow as `--from-run`. Playwright, Detox, pytest and WebdriverIO's JSON report go to that folder, so they never replace a report the team is looking at; Maven and Gradle still write their usual build folders, and a WebdriverIO config's failure hook and Appium log still write where the config says.

## 1. Find the suites

Look for runner configs outside `node_modules/`, `vendor/` and build output. Each config's folder is one suite, run from that folder:

| Found | Suite |
|---|---|
| `playwright.config.*` | Playwright |
| `.detoxrc`, `.detoxrc.*`, `detox.config.*`, or a `"detox"` key in `package.json` | Detox |
| `wdio.conf.*` | WebdriverIO — Appium when its capabilities target a device (`platformName` `Android`/`iOS`, or an `automationName`) |
| `<groupId>io.appium</groupId>` with `<artifactId>java-client</artifactId>` in `pom.xml` | Appium on Maven |
| `io.appium:java-client` in `build.gradle*` | Appium on Gradle |
| `Appium-Python-Client`, in any letter case, in the Python dependencies | Appium on pytest |

With a `<path>`, run only the suite whose folder holds it, limited to that file or folder. Without one and with several suites, ask which to run ([How to ask](../SKILL.md#phase-3-resolve-missing-required-fields), `multiSelect: true`, plus an `All suites` option); a headless run takes all of them. With none, stop: `❌ No Playwright, Detox or Appium suite found in this project.`

## 2. Make sure a device is up (Appium)

Detox boots the emulator or simulator its `.detoxrc` device names by itself — don't boot one for it; a `response not received` failure is handled as in [Phase 2](../SKILL.md#phase-2-evidence-gathering).

For Appium:

- Android: `adb devices` must list a device in the `device` state. iOS: `xcrun simctl list devices booted` must list one.
- With none, boot the one the config names — the `appium:avd` capability, or the `deviceName` only when `emulator -list-avds` (Android) or `xcrun simctl list devices` (iOS) lists that name (a `deviceName` such as `emulator-5554` is a serial, not something to boot); when the config names nothing bootable, ask which one to start. Pass the name as one single-quoted argument: `emulator -avd '<name>' -no-snapshot-save` in the background, then `adb wait-for-device` and poll `adb shell getprop sys.boot_completed` until it prints `1` (give up after 5 minutes); `xcrun simctl boot '<name>'` on iOS.
- If no device can be booted, stop: `❌ No emulator, simulator or device available for the <suite> suite. Start one and run /report-bug --run again.`
- Leave whatever you booted running — Phase 2 re-runs each failure on it — and add `🔌 Booted <name> for this run — still running` to the Phase 2 summary.

## 3. Run each suite

Detox first needs the app binary its configuration points to — run `npx detox build --configuration <configuration>` when it is missing — and, for a debug build, a running Metro bundler.

`<run>` is the absolute path of `.claude-temp/report-bug/run`. Each runner exits non-zero when a test fails — that is the expected outcome here, never a crash; what matters is the report it writes.

| Suite | Command | Report |
|---|---|---|
| Playwright | `PLAYWRIGHT_JSON_OUTPUT_NAME=<run>/playwright.json PLAYWRIGHT_HTML_OUTPUT_DIR=<run>/playwright-report PLAYWRIGHT_HTML_REPORT=<run>/playwright-report PLAYWRIGHT_HTML_OPEN=never npx playwright test [<path>] --reporter=json,html --output=<run>/playwright-results` | `playwright.json`; screenshots, traces and videos under `playwright-results/`; the HTML report under `playwright-report/` |
| Detox | `npx detox test --configuration <configuration> [<path>] --json --outputFile=<run>/detox.json` (Detox passes the last two flags on to Jest) | `detox.json` |
| WebdriverIO / Appium | `npx wdio run <wdio.conf> [--spec <path>] --reporters json --logLevel error > <run>/wdio.out` | each `"json" Reporter:` line in `wdio.out` is followed by one worker's JSON report; screenshots and device logs come from the config's failure hook |
| Maven | `mvn test [-Dtest=<Class>]` | `target/surefire-reports/*.xml` written by this run |
| Gradle | `gradle test --rerun [--tests '<Class>']` (or `./gradlew`; `--rerun-tasks` before Gradle 7.6) — plain `gradle test` is skipped as up to date when no Gradle input changed, a new app build included | `build/test-results/test/*.xml` written by this run |
| pytest | `pytest [<path>] --junitxml=<run>/pytest.xml` | `pytest.xml` |

- `--output` keeps Playwright from emptying the project's own `outputDir`, which it does at the start of every run.
- `--reporters json` needs `wdio-json-reporter` in the project. Without it, run with the config's reporters and read the JUnit XML its `junit` reporter writes; with neither, stop: `❌ The WebdriverIO suite writes no JSON or JUnit report. Add wdio-json-reporter to its reporters (see the mobile-e2e-automation-architecture skill).`
- Pick the Detox configuration the same way: the only one, or the one whose platform matches the booted device; ask when that still leaves several.
- A long suite can run for many minutes: run it in the background and wait for it, rather than under a short command timeout.

## 4. Read the result

- **No report, or zero tests ran** (the config failed to load, nothing matched `<path>`): show the last 30 lines of the runner's output and stop: `❌ The <suite> suite didn't run: <first error line>.`
- **No failures**: `✅ <suite>: all <n> tests passed — nothing to report.` Stop when every suite passed.
- **Failures**: continue as `--from-run` with these reports — the [Phase 0](../SKILL.md#phase-0-parse-arguments) table shows `Mode` `--run` and a `Failures` row per suite — then Phase 1 onwards. The suite run is the first observation of each failure; [Phase 2](../SKILL.md#phase-2-evidence-gathering) still confirms each one with its own re-run before it is reported.
