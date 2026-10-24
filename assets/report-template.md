# Test Run Report — {{suite name}} — {{yyyy-mm-dd}}

**Recommendation:** {{GO | GO WITH RISKS | NO-GO | INCONCLUSIVE}} — {{one-line reason}}
**Decided by:** {{name}}
**Build / environment:** {{commit or version}} · {{base URL}} · {{browser}}
**Full results:** {{Allure report URL or path — or "not published"}}

## Headline

{{2–3 sentences a manager can read in 10 seconds: what ran, what broke, what it means.}}

## Totals

| Metric | Value |
|---|---|
| Total | {{n}} |
| Passed | {{n}} |
| Failed | {{n}} |
| Skipped | {{n}} |
| Flaky (passed on retry) | {{n}} |
| Config failures | {{n}} |
| Pass rate (executed) | {{n}}% |
| Duration | {{n}} s |

## Compared with previous run

{{Only if a previous run was given. New failures, fixed, still failing, newly skipped, pass-rate change.}}

## Failures by cause

| # | Tests | Cause | Category | Known issue | Next action |
|---|---|---|---|---|---|
| 1 | {{n}} | {{short cause with evidence}} | {{Product bug / Test defect / Environment / Needs triage}} | {{ticket or —}} | {{who does what}} |

## Skipped tests

{{Which tests did not run and why (usually one config failure). "None" if none.}}

## Flaky tests

{{Tests that passed only on retry. "None" if none.}}

## Slowest tests

{{Top 5 from the data, with durations. Optional — remove if nobody cares.}}

## Risks and next steps

- {{risk or action, with owner}}

## Failing tests

{{Full list of failing test ids, grouped by cause number from the table above.}}
