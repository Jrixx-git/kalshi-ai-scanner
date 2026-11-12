# Bounded prospective NBA team development collection

This is research data collection only. There is no model parameter, fitting step,
forecast regeneration, ledger import, or order endpoint in this workflow.
The operational v0.8 source, historical forecasts, paper ledger and risk settings
remain outside its write targets.

## Deployment and actual time

The default-branch launcher calls a reviewed immutable source SHA on develop.
GitHub only activates schedules from its default branch. The launcher requests
hourly runs at minute 07 UTC during November 11–25. Actual execution is bounded
by the existing approved window, ending **2026-11-25 18:00 UTC**. Later cron
events, including future years, cannot collect provider or public source data.
No scheduler can guarantee an exact startup time: GitHub may delay or drop cron
events. One serialized worker waits for upcoming cutoffs, rather than hoping
the scheduler starts inside a 30-second window. Ordinary runs wait at most one
hour; initial activation can wait up to four hours. The total job has a
260-minute ceiling. A run records games outside its horizon so a later run can
capture them. Delayed starts and elapsed cutoffs stay missing, without backdating.

Seals use actual UTC start/end times, between 60:00 and 59:30 before the observed
tipoff, with at most 30 seconds to finish. Monotonic time bounds waiting only.
The independent ESPN settlement-source schedule is refreshed within 90 seconds
of a future cutoff (or immediately if setup finishes closer to cutoff), and
verified before sealing. Provider-only or ambiguous identities cannot pass
this check. If game times change, evidence fails closed or remains explicitly
missing; no old seal is rewritten for the new tipoff.

## Sources, limits, and durability

BALLDONTLIE uses the existing secret, without a new subscription or tier change.
Each seasonal collection has a 20-page, 8 MiB/page, 15-second/request ceiling.
Both 2025 and 2026 are collected with real raw response receipts. The existing
bounded source collector retains two dates of provider and independent schedule
universes, at most four provider pages, 70 public Kalshi GETs, and two official
NBA injury reports. Injury data remain unparsed and excluded from features.
The waiter adds at most 12 independent schedule refreshes; each is bounded by
the same byte/time policy. Redirects and trading endpoints are refused.

All provider games and independent-only identities survive as universe and
coverage evidence. Unknown or missing data are never silently dropped or
replaced with zero. A missing Elo or feature is recorded in a seal but does
not become an eligible training row.

Source preparation is checkpointed in an Actions artifact and the isolated
`research/nba-team-development-evidence` branch **before waiting**. The final
full or partial run is retained again. Artifacts last 90 days; the branch is
the persistent copy. Git attributes preserve exact raw and baseline bytes on
Windows and Linux. Restore imports only the evidence directory, preserving the
pinned executable source. Archives use normal fast-forward pushes, reject changes
or deletions of existing evidence, verify the remote head, and never push
to operational branches. A failed checkpoint prevents supervision. If a runner
is forcibly terminated, its prepared receipts still survive. Any unarchived
seals remain missing until an authentic artifact is recovered; never recreate
an old seal from a later response.

Restoration keeps the first receipts and immutable baseline bundles. Mutable
operational scoreboards are excluded. Exclusive actual-hour claims suppress
duplicate source collection after retry, and per-game immutable input files
plus a per-slot worker claim prevent duplicate seals. All scheduled calls use
the same concurrency group. Archive conflicts stop collection instead of
overwriting prior evidence. A failed partial slot is retained and not retried
under an invented timestamp; subsequent actual hours collect fresh evidence.

## Eligibility and legacy evidence

The baseline reader validates the original manifests, CSV, metadata and every
referenced snapshot. The legacy audit found 28 bundles, 118 unique pregame Elo
forecasts and 27 normalized history snapshots. These can legitimately establish
the baseline probability/identity and its original availability, including for
a future matching game's cutoff. They do not establish a previously unrecorded
60-minute development seal or raw provider page receipt. No legacy timestamp
is changed and no normalized snapshot is relabeled as a raw API response.

New receipts can supply history only from their actual receipt times onward.
Later updates do not replace first-observed final outcomes. A shared read-only
verifier now feeds both inventory and training: it recomputes each sealed
feature set from raw receipts and checks the exact original Elo archive.
Inventory additionally excludes incomplete features, missing outcomes and
invalid cutoff/tipoff/outcome receipt ordering. Its proposed chronological
split is the earliest tipoff admitting 100 previously received outcomes; it
never chooses a split using outcomes or performance. At least 30 later eligible
games must also exist. No scheduled workflow fits or freezes a model.

Offline verification: 277 tests pass, including a real Git stage/checkout round
trip with Windows line-ending conversion enabled, late starts, clock reversal,
budget expiry, simultaneous cutoffs, independent omissions, immutable game and
slot duplicates, source-plan tampering, receipt tampering, and delayed outcomes
at the train/validation boundary. Existing strategy and risk tests still pass.

Live validation exposed and fixed two boundary errors: schedule freshness now
uses a clock sampled after receipt, including the first game in a cutoff group;
repeated shallow archive fetches use FETCH_HEAD rather than rewriting a shallow
tracking ref. The server push still requires an ordinary fast-forward. Regression
tests cover the first network response and two sequential depth-one checkpoints.
Original seals recovered from an authentic artifact retain all original bytes
and times; recovery is never a new seal or a backdated capture.
