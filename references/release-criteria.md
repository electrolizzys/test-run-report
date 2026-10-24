# Release criteria — proposing a recommendation

Propose one of four recommendations with your reasons; the human decides. These thresholds are
defaults. If the project defines its own quality gate (for example in `CLAUDE.md`, a
`QUALITY_GATE.md` file or the CI configuration), use that instead and say which one you used.

| Recommendation | Propose when ALL of these hold |
|---|---|
| **GO** | no failures except known, non-blocking issues · executed pass rate ≥ 95% · ≤ 5% skipped · no new failures vs the previous run |
| **GO WITH RISKS** | every remaining failure is a test defect, flaky, or a known issue rated Minor/Trivial · no failure in a critical flow (login, create/pay/submit, permissions) · ≤ 10% skipped |
| **NO-GO** | any new product bug in a critical flow · any Blocker/Critical known issue still failing · executed pass rate dropped by > 10 points vs the previous run because of product bugs |
| **INCONCLUSIVE** | > 10% of tests skipped or blocked by environment / config failures · the run stopped early · results are from the wrong build or environment |

How to apply:

1. Check INCONCLUSIVE first. A run that did not really run cannot say GO or NO-GO — recommend a
   rerun and name what must be fixed (e.g. "admin app on :3001 was not running").
2. Then NO-GO. One critical product bug is enough.
3. Then GO WITH RISKS vs GO. List every risk you accept, by test name and ticket.
4. Write the reasons as evidence, not opinion: "2 new failures in event creation (POST
   /api/v1/events → 500)", not "creation looks broken".

The recommendation line in the report must name who made the decision
(`**Decided by:** <name>`). The checker refuses a report without it.
