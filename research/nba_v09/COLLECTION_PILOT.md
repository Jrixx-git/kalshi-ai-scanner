# Prospective evidence pilot

PR #3 merged into develop/paper-trading-v02 at
435eeb953ad5a88419f23ee1045ebf1210f74770 after exact-tree local tests
(219 passed), successful GitHub runs 43070025984 and 43069966684,
diff and timestamp review, and credential-pattern scanning with no findings.
The merge leaves existing operational archives, ledger, limits and Elo unchanged.

The new prospective workflow collects hourly at minute 17 UTC (minute 17 of
each Central hour), starting when activated November 11. It refuses collection
outside 2026-11-11 18:00 UTC through 2026-11-25 18:00 UTC exclusive
(November 25 noon Central). This is a finite evidence pilot, not a launched
challenger evaluation. GitHub scheduling is best effort: delays and dropped
invocations can cause missing cutoff observations. No exact 24h/6h/1h capture
is claimed; retain actual times and time-to-tip for downstream selection.

The main-branch dispatcher invokes a pinned research workflow and source SHA.
It does not merge research or change the existing operational dispatcher on main.
The calendar cron is restricted to November 11–25; it is annual, but the
hard-coded 2026 window prevents source collection in later years. Remove or
disable this dispatcher after the pilot to avoid future no-op runner invocations.

Every invocation retrieves today and tomorrow in league time, including all
provider games regardless of trading selection, plus independent ESPN schedules
and the latest two official NBA injury PDFs. Independent-only events and missing
provider responses remain explicit. Kalshi discovery is full NBA pagination;
books are requested for every verified pregame provider matchup. Unrecognized
identities/tips, post-tip receipts, missing markets, failed books and provider
pagination failures do not become eligible observations. No fee data is collected
by this pilot; it supports prediction benchmarking, not fee-adjusted trade claims.
Raw injury PDFs remain unparsed; availability does not imply healthy players.

Network ceilings per invocation: four BALLDONTLIE pages, 70 Kalshi GETs,
two independent schedule GETs, one NBA index and two PDF GETs (79 total).
No retries; 15-second per-response timeout and 8-MiB response limit. Market books
are serialized; the capture step has a five-minute ceiling and job ten minutes.
A killed step can leave only partial evidence/initial receipt, which is retained
without a success claim. A source failure does not suppress unrelated sources.
No new API subscriptions, paid endpoints or SportsDataIO are used. Existing
BALLDONTLIE_API_KEY is exposed only to the collector step, never persisted.
The public repository uses standard ubuntu-latest, not larger runners; standard
public-repository runner compute is free under current GitHub policy. Artifact
storage follows repository/account policy; no paid capacity is purchased.

All workflow callers share one concurrency group. Each UTC-hour slot has an
exclusive local claim and a durable evidence directory; repeated dispatches and
reruns skip a retained slot. A failed persistence blocks claiming that slot as
durably deduplicated; artifacts provide recovery. GitHub may replace queued runs
in the concurrency group: absence is missingness, not invented evidence.

Artifacts include run/attempt IDs and request 90-day retention. The workflow also
appends only research-evidence/slots/SLOT to research/nba-v09-evidence with a
non-force push, retaining earlier slots indefinitely. It never pushes to main or
develop and never invokes paper reconciliation. The archival branch has a separate
root tree, containing no operational code or data. Token authentication is only
configured during the persistence step. Inspect source/run artifacts and the
dedicated branch before claiming an actual successful collection.

Sources: https://docs.balldontlie.io/ ;
https://official.nba.com/nba-injury-report-2026-27-season/ ;
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule ;
https://docs.github.com/en/billing/concepts/product-billing/github-actions .
