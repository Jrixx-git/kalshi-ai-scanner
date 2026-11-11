# Bounded NBA result retrieval

Run 43052443674, job 130632921364 completed successfully on November 11, 2026.
Scoring started 15:51:23 UTC and completed 16:08:20 UTC: about 17 minutes.
It scored 108 games; paper capture then recorded seven entries; audit reported no errors.
The run uploaded artifact 13869849465. It was slow, not a failed provider retrieval.

Root cause: serial game-ID fetches, 13-second pacing, four 30-second attempts with
15/30/45-second backoffs, and quote collection downstream of scoring. Growing
archives can exhaust the 120-minute job even when every individual call is bounded.

The fix verifies cached final identity, scores and observation/tipoff timing before
reuse. Finals are checked at most daily during the seven-day correction window.
Freezing still requires an actual provider observation at or beyond seven days;
old pre-boundary observations never freeze just because today's date is later.
Refresh-all bypasses freshness/freezing but retains budgets. Defaults: 60 requests,
1200 seconds, reserving 210 seconds plus pacing before each request. A workflow
25-minute step timeout protects against a transport that exceeds its socket timeout.
Least-recent attempts rotate bounded work, including missing/error IDs. Missing IDs
remain unresolved; forecasts and historical content-addressed snapshots are never
rewritten. Failed/404 refreshes retain prior results and their original timestamps.
Diagnostics list attempted IDs, error classes and deferred counts without secrets.
Partial scoring excludes unresolved games and exposes partial_refresh explicitly.

Paper capture, reconciliation, audit and persistence precede slow result scoring.
No risk limits, bankroll, credentials or live trading behavior changed. The main
scheduled caller must pin the new reusable-workflow commit for this ordering to
apply to scheduled runs. Offline tests cover correction windows, post-window
verification, forced refresh, bad cache identity/scores, budgets, rotation, timestamps,
partial outages and workflow ordering. No live provider calls are made by tests.
