# Categorizing failure groups

Categorize each **group** from `run-summary.json`, not each test. A status report needs a
category so the reader knows who acts next. Quote the signal you used.

| Category | Who acts | Strong signals (Playwright + TestNG) |
|---|---|---|
| **Product bug** | developers | assertion on content fails and the received value is an error ("Something went wrong"); the page's API call returned 5xx in the reporter output; wrong data on the page |
| **Test defect** | QA / test owner | `strict mode violation ... resolved to N elements`; locator timeout while the page looks normal; NPE in a `*Page`/`*Test` class; expected value contradicts the scenario |
| **Environment** | whoever owns the stand / CI | `net::ERR_CONNECTION_REFUSED`, `ERR_NAME_NOT_RESOLVED`, browser executable missing, DB connection errors; a config failure (`@BeforeClass`) that skipped many tests |
| **Flaky** | test owner | listed in `flaky` (failed, then passed on retry); timeouts with no wrong value |
| **Known issue** | nobody new — already ticketed | `known_issue` is set in the JSON (matched from known-issues.txt) |

Rules:

- **A config failure that skipped tests is one item.** Report "AdminDashboard setup failed →
  2 tests not run", not three separate problems.
- **Skipped tests are not passed tests.** If more than ~10% of tests were skipped or blocked by an
  environment problem, the run cannot support a GO — the recommendation is INCONCLUSIVE until a
  rerun.
- **Known issue does not mean harmless.** Keep its category (usually product bug or test defect)
  and add the ticket; the release criteria decide whether it blocks.
- When unsure between product bug and test defect, say "needs triage" and let the human decide —
  the bug-report-writer skill (if installed) does the detailed triage.
