# Team-only challenger implementation, 2026-11-11

Research code: `nba_v09_challenger.py`. Candidate version: `nba-team-offset-v1`.
This is an implemented pipeline, not a trained model or launched evaluation.
Operational v0.8 source, Elo temperature 1.23, forecasts, immutable archives,
paper ledger, $5,000 simulated bankroll, $50 position-loss, $150 daily-loss and
$500 open-exposure limits remain unchanged. Nothing admits trades.

## Evidence reviewed and current blockers

Source base: `cfaad3246636db292f06d786028bdc393367b5ce` on
`develop/paper-trading-v02`. Pilot evidence commit:
`9c891428867808c563d11905b6e7621a9dafc2d6` on `research/nba-v09-evidence`.
The November 11 18:00 UTC slot completed at 18:19:37.784077 UTC: 10 provider
games on November 11 and 4 on November 12, independent counts agree, all 14
raw contract pairs available, no reported source errors, two unparsed injury
PDFs. Its hourly quotes are not a launched 60-minute challenger evaluation.

No real challenger forecast or fitted model is claimed. Local
`BALLDONTLIE_API_KEY` is unavailable; direct collection refused before any
network request. A manual Actions collector can use the existing repository
secret, without buying another service. No live collection run has been
verified for this new workflow. Normal shell Git networking also failed DNS.

There are zero qualifying team-challenger input seals in the reviewed tree.
The fitter requires at least 100 complete development rows and 30 later
validation rows with verified pregame features and archived operational Elo.
Today's download cannot supply receipt-time evidence for past forecasts.
Neither the exploratory 102-game benchmark nor current hourly pilot is
silently relabeled as a new holdout or training dataset. Inspect existing
older raw archives for compatible receipt evidence before deciding whether
new development collection must supply the entire training cohort.

## Archive and features

The collector stores exact response bytes, their SHA-256, fixed source URL,
actual request and receipt times, individual page receipts and a completion
manifest. Maximum 30 pages, 8 MiB per response, 15-second timeout, no redirects
or retries. The manual workflow uses 20 pages. Truncation leaves raw evidence
but no completion claim; incomplete collections cannot feed features.
The archive is content addressed and refuses conflicting overwrites.

Every source page in a complete collection must already have arrived at the
cutoff. Each final needs exact provider ID/abbreviation identity, distinct NBA
teams, `Final` status and positive integer unequal scores. Duplicate games
within a collection fail. Repeated collections retain the first observed final
and reject identity changes. Later score corrections cannot replace it.

Features exclude target-game outcomes and every game on/after the target league
date. Tipoff must agree with that date in America/New_York. Rest is capped at
seven calendar days; back-to-back means one day. Last 5/10 margin and win rate
require full windows. Relevant home/away win rate requires 20 venue games.
Counts, explicit venue indicator, missing values and receipt hashes are retained.
Missing means abstain; it is never zero-filled. Injuries remain unknown and
excluded. Official injury files remain raw evidence. SportsDataIO is unused.
An absent current-season archive also forces missing features, so a previous
season download alone cannot masquerade as current form.

## Fit and freeze contract

Fixed logistic residual over the archived operational Elo log-odds; seven
home-minus-away features, train-only means/population standard deviations,
constant dimensions scaled by one, no learned intercept, L2=0.1, 2,000 batch
gradient steps of size 0.1. No parameter search. Minimum 100 training games
and 30 validation games. Games are sorted chronologically and by ID; duplicate
IDs fail. Results for training games must be received before validation starts.
Validation games never enter coefficient fitting or scaling. All outcomes
must precede the explicit training-data cutoff. All input seals are rebuilt
from raw receipts and checked against the immutable operational baseline.

The returned model includes weights, scaling, ordered field names, fixed
policy, training digest/counts, holdout scores, training cutoff and actual
freeze receipt. Its content hash and implementation-file SHA are verified
before prediction. An explicit model file is required; no latest-model alias,
automatic retraining or fallback to untrained coefficients exists. Changing
the implementation requires a newly versioned review/freeze. JSON model files
are written immutably in the separate research output directory.
Input collection without a model is explicitly marked development; inputs
collected with a frozen model are marked evaluation and excluded from fitting.

## Dedicated cutoff runner and comparison

The bounded runner waits until tip minus 60 minutes, allowing at most 30 seconds
of startup delay. It seals simultaneous games before network work, then fetches
an independent schedule and GET-only NBA books (70-request ceiling, one worker).
No model means input-collection mode, with no challenger prediction. Inputs and
forecasts have one immutable path per game (forecasts additionally per model).
Late starts, unresolved independent identities and source errors remain coverage
records. The runner does not replace the existing hourly pilot or dispatcher.
It must be launched before the cutoff by a supervised worker; no always-on
cutoff service has been deployed or reliability demonstrated in this milestone.

Comparison preserves the supplied full provider/independent universe. It uses
the first valid complete quote after sealing, received 60–30 minutes before tip,
with existing independent schedule/contract/rules/book receipt checks. Selection
does not inspect price, edge or outcome. Missing baseline/history/quote/result
remains explicit. Verified final receipt must follow tip and match team/date
identity. Same-game three-way Brier/log loss, ten-bin calibration, disagreement
bins [0,.03), [.03,.08), [.08,1], and deterministic 1,000-resample date-block
95% intervals for challenger-minus-control Brier differences are reported.
Intervals require at least two league dates. Evaluation requires 200 paired
games and 30 league dates; interim output is descriptive. Midpoint is not a fill.

## Commands

Run with Python 3.11+ and timezone data on Windows. These commands perform no
paper reconciliation or orders. Use a separate research output directory.

```text
python -m unittest discover -q
python nba_v09_challenger.py --season 2025 --history team-history
python nba_v09_challenger.py --season 2026 --history team-history
python nba_v09_challenger.py --action cutoff --targets targets.json --history team-history --operational forward_test --output team-challenger --max-wait-seconds 7200
python nba_v09_challenger.py --action train --history team-history --inputs team-challenger --operational forward_test --output team-challenger --freeze-at ACTUAL_DATA_CUTOFF --validation-start CHRONOLOGICAL_SPLIT
python nba_v09_challenger.py --action cutoff --targets targets.json --history team-history --operational forward_test --output team-challenger --model EXPLICIT_MODEL_FILE
python nba_v09_challenger.py --action compare --targets targets.json --history team-history --operational forward_test --inputs team-challenger --output team-challenger --model EXPLICIT_MODEL_FILE --market-roots team-challenger --asof ACTUAL_SCORING_TIME
```

Targets are a JSON array of raw provider game objects plus independent-only
records carrying unique IDs and dates. Preserve the independent-only denominator
when preparing this file; do not filter it to successful forecasts. Refresh both
current-season history and schedule evidence before each cutoff. Archive the
research outputs durably; the manual history workflow's artifacts expire after
90 days and are not an indefinite archive branch. No scheduled workflow was
enabled, no additional Work chat was created and no collaborator was contacted.
