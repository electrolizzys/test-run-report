---
name: test-run-report
description: >-
  Turn the results of an automated test run into a status report for the team or a manager: totals,
  pass rate, failures grouped by cause, skipped and flaky tests, comparison with the previous run, and a
  proposed release recommendation (GO / GO WITH RISKS / NO-GO / INCONCLUSIVE) that a human confirms. Use
  when someone asks "how did the regression go?", "summarize the test run", "write the daily/nightly test
  report", "are we ready to release?", "what changed since yesterday's run?", or points at
  testng-results.xml, allure-results, target/surefire-reports or test-output after a Playwright/TestNG
  (or JUnit) run. Complements the Allure dashboard: Allure shows the data, this skill writes the
  conclusion. Do
  not use for writing an individual bug report (bug-report-writer), for fixing a failing test
  (scenario-debug-kit), or for designing new scenarios.
---

# Test run report

After every regression run somebody has to answer the same three questions: *what ran, what
broke, can we ship?* Allure (or the TestNG report) shows the data — totals, a pie chart, a trend,
the failures — but it does not answer them. Someone still reads the dashboard, works out which
failures are new and which already have a ticket, decides whether the build can ship, and types
a summary into Slack or an email. Reading and comparing is mechanical; the "can we ship?" part
is a decision.

This skill splits it accordingly:

| Script (deterministic) | Model (judgment and writing) | Human (decision) |
|---|---|---|
| count totals, pass rate, duration; group failures by cause; resolve config failures, skips and retries; compare with the previous run; match known issues | categorize each failure group, propose a recommendation with evidence, write the report | confirm categories and known issues; make the release call |
| check the finished report's numbers against the data | | |

**Never count tests or compute rates yourself.** Run `scripts/summarize_run.py` and copy its
numbers. A status report with one wrong number loses the reader's trust in every other line.

## Workflow

### 1. Find the results

```bash
find . -name testng-results.xml -not -path "*/node_modules/*" 2>/dev/null
ls target/surefire-reports test-output 2>/dev/null | head
```

```bash
ls -d allure-results target/allure-results 2>/dev/null
```

TestNG via Maven writes `target/surefire-reports/testng-results.xml`; plain TestNG writes
`test-output/testng-results.xml`. Allure writes raw results to `allure-results/` or
`target/allure-results/`. The script uses the first format it finds in this order: TestNG,
Allure, JUnit `TEST-*.xml` — pass the one directory you want.

If the project publishes an Allure report (locally `allure serve allure-results`, or on CI),
ask for its URL and put it in the report so readers can drill into any test. Do not repeat what
the dashboard already shows test by test; the report's job is the conclusion.

**Previous run (optional, but it makes the report far more useful).** Ask where the previous
run's results are — a saved copy (e.g. `reports/runs/2026-10-22/`), a CI artifact the user
downloaded, or none. Do not invent a comparison when there is no previous run.

**Known issues (optional).** Look for a `known-issues.txt` (format in
`assets/known-issues.txt`) in the project, e.g. `.qa/known-issues.txt`.

### 2. Summarize

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/summarize_run.py target/surefire-reports \   # or allure-results
        --previous reports/runs/<previous-date> \
        --known .qa/known-issues.txt \
        --out target/test-run-report/run-summary.json
```

Leave out `--previous` / `--known` when they do not exist. The script prints a one-screen
summary and writes the full JSON. Read `summary`, `groups`, `skipped`, `flaky` and `comparison`.

What matters for Playwright + TestNG:

- a group with `config_failure: true` and `skipped_dependents` — one `@BeforeClass` failure that
  stopped N tests; it is **one** cause.
- `flaky` — failed, then passed after `RetryAnalyzer`; counts as passed, but must be listed.
- `comparison.new_failures` — the most important list in the report: what broke since last time.

### 3. Categorize each group

Read `references/failure-categories.md`. For each group propose Product bug / Test defect /
Environment / Needs triage, and a next action with an owner. Quote the evidence (exception,
message, status code).

### 4. Propose a recommendation

Read `references/release-criteria.md` and apply it in its order: INCONCLUSIVE first, then NO-GO,
then GO WITH RISKS vs GO. Write the reasons as evidence.

### 5. Human checkpoint — mandatory

Show the user, compactly:

```
Totals: 7 tests · 2 passed · 3 failed · 2 skipped · 1 flaky · executed pass rate 40%  (prev 71.4%)
#  Tests      Cause                                         Proposed      Known
1  1 (+2 sk)  AdminLoginPage.open ERR_CONNECTION_REFUSED     Environment   —
2  2          toast "Something went wrong" (POST → 500)      Product bug   —
3  1          strict mode violation: 2 Cancel buttons        Test defect   QA-212
Proposed recommendation: INCONCLUSIVE — 2 of 7 tests did not run (admin app down); also 2 new
product failures in event creation, which would be NO-GO on a complete run.
```

Ask the user to confirm or change: the categories, any failure that is a known issue (offer to
add it to `known-issues.txt` — only with their agreement), and the recommendation. Ask for the
name to put in **Decided by**.

Do not write the final report before this answer. The release call is the user's, even when the
numbers look obvious.

### 6. Write the report

Copy `assets/report-template.md` to `reports/test-run-<yyyy-mm-dd>.md` and fill it:

- **Totals** — copy from `summary` exactly (the checker compares them).
- **Headline** — 2–3 sentences for someone who reads nothing else. Lead with the decision and
  the single biggest reason.
- **Failures by cause** — one row per group, in the order of the JSON's `groups`.
- **Compared with previous run** — only when `comparison` exists; name the new failures.
- **Failing tests** — every id from `failures`, so nothing disappears into a summary.
- Delete the Slowest tests section if the user does not care about duration.

If the user also wants a chat message (Slack/Teams), add a 4–6 line version at the end of your
reply: recommendation, totals line, top 1–3 causes, link or path to the full report.

### 7. Check

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py reports/test-run-<date>.md target/test-run-report/run-summary.json
```

Fix everything it reports — a wrong number, a failing test missing from the report, a missing
section, an unfilled field or a missing **Decided by**.

### 8. Hand over

Give the path to the report and the short chat version if asked. Suggest saving the current
results as the next run's "previous" (e.g. copy `testng-results.xml` to `reports/runs/<date>/`)
— offer, do not do it unprompted. For product bugs, offer the bug-report-writer skill if it is
installed.

## Reference files

- `references/failure-categories.md` — how to categorize a failure group and who acts next.
- `references/release-criteria.md` — when to propose GO / GO WITH RISKS / NO-GO / INCONCLUSIVE.
- `assets/report-template.md` — the report template.
- `assets/known-issues.txt` — format of the known-issues file.
- `assets/examples/` — two TestNG + Playwright runs (previous and current), a known-issues file,
  the generated `run-summary.json` and the finished report. Try:
  `python3 scripts/summarize_run.py assets/examples/runs/current --previous assets/examples/runs/previous --known assets/examples/known-issues.txt`
