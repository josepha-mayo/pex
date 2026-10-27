# Worker time receipt guard — WIP live qualification

Before this change, authored negative and NaN active-time receipts reached a
graded natural stop; a 100-second baseline turn was also a natural stop despite
the same 90-second limit making the PEX arm budget-inconclusive.

The controller now rejects nonnumeric, Boolean, negative and nonfinite durations
as infrastructure errors, retains already-validated usage, and classifies active
time overruns as budget-terminal for either arm. It never calls the supervisor
or protected grader for an invalid-duration receipt. Exactly-at-limit natural
baseline stops remain valid; the PEX arm cannot spend another review cycle.

Thirteen new authored regressions exercise malformed duration values, overrun,
zero duration and exact boundaries. These are controller tests, not inference,
payment, browser, VM or real benchmark results. Live source pins must be refreshed
before qualification; historical live receipts do not qualify changed bytes.
No approval gate, provider limit, credential handling or deployment is changed.
