# NBA v0.6 daily research predictions

Branch: `develop/paper-trading-v02`. No changes to `main` are needed.
No real-money trading is implemented or enabled. This command makes only GET
requests to BALLDONTLIE and exports research files. It does not call Kalshi,
load trading credentials, map markets, or submit paper or live orders.

## Run manually in GitHub Actions

Use the existing **NBA Multi-Season Backtest** workflow (`nba-history.yml`):
select **Run workflow**, choose **develop/paper-trading-v02**, enable
`daily_predictions`, and optionally enter `prediction_date` (YYYY-MM-DD).
The date defaults to today in America/New_York and allows up to seven days ahead.
Download the `nba-v06-daily-predictions-<run-id>` artifact when the run completes.
The existing historical-backtest option remains available when the checkbox is off.

A dedicated `nba-daily.yml` manual workflow is also included. GitHub may not
register a new workflow until it exists on the default branch. The existing
`nba-history.yml` entry point avoids changing main just to register this workflow.
If the UI shows only old input fields, dispatch the existing workflow with CLI:

```sh
gh workflow run nba-history.yml --repo Jrixx-git/kalshi-ai-scanner --ref develop/paper-trading-v02 -f daily_predictions=true
```

The workflow uses the existing `BALLDONTLIE_API_KEY` repository secret, scoped
only to the fetch step. Contents permissions are read-only; it uploads artifacts
and never commits generated data. It runs the complete offline test suite first.
No schedules are added. A missing API secret or insufficient API plan fails the run.

## Local use

Python 3.10+ with IANA timezone data (Linux runners include it; Windows may need
the `tzdata` package). Set `BALLDONTLIE_API_KEY` in the environment without
putting the key in code or command arguments, then run:

```sh
python -m unittest discover -v
python nba_daily_predictions.py --output-dir daily_predictions
```

## Model and causality

Fetch paginated history from 2022-10-01 through the day before the target date.
Only confirmed final games enter Elo. Initial ratings 1500, K=20, and home
advantage 65 match the audited v0.4/v0.5 pipeline. All games on each date use
pre-date ratings, with updates applied in a batch after that date. Same-date
and later outcomes never enter a prediction. Upcoming games are never updated
using hypothetical results. Previously unseen teams cause a failure.

Apply `nba_calibration.transform(round(raw_probability, 6), 1.23)` from v0.5.
Temperature is frozen, not fitted from daily data. The v0.5 validation period
was 2024-10-01 through 2025-09-30 (1,321 games); later evaluation had 1,322 games.
This is the recreated v0.5 calibration previously tested, not a new prospective
validation. It remains exploratory and has not established a trading edge.

Only scheduled games with period zero, a known timezone-aware future tipoff,
and the requested NBA league date are exported. Started, final, postponed,
canceled, delayed, unknown, or missing-tipoff games are skipped with reasons.
Time is checked after network retrieval so games starting during download are
excluded. Scores alone never establish that a game is final or upcoming.

CSV includes IDs, team abbreviations, UTC tipoff and generation timestamps,
raw and calibrated home probabilities, complementary away probability, ratings,
temperature, history cutoff and research-only mode. JSON records source hash,
CSV hash, included history count, last history date, and skip reasons. Zero
eligible games yields a header-only CSV and explicit zero count, not an error.
API failures, malformed pagination, repeated cursors, duplicate IDs and page
limits fail instead of silently exporting partial predictions. Requests pause
2 seconds between pages and queries, with bounded retries on rate limits/transient failures.
Cursor pages accept a positive integer continuation, explicit null, or an omitted
next_cursor with a valid per_page envelope. Missing/malformed metadata and legacy
page-number envelopes are rejected rather than interpreted as complete results.

Validated monthly history chunks are saved under `.nba_history_cache/` (override
with `--cache-dir`). Only fully retrieved, schema-checked chunks are saved, using
atomic replacement and SHA-256 integrity checks. Old months expire after seven
days; chunks ending within the last seven days or in the future expire after
five minutes. Invalid or expired chunks are fetched again; API failure never
falls back to stale data. Delete this directory to force a full refresh. The
schedule is always fetched fresh. The two daily workflow entry points restore
and save this cache, including completed chunks from a failed download. GitHub
cache eviction can still require a fresh download. Cache checks cannot certify
provider completeness or detect unpublished historical corrections.

Historical corrections can affect later runs; provider availability timestamps
and full independent schedule reconciliation remain unverified. The data is an
as-retrieved view, not a certified historical point-in-time database. Future-date
predictions are snapshots of currently available finals, not forecasts of future
rating updates. No odds, fees, liquidity, injuries or market settlement rules
are modeled. Existing scanner and paper simulator remain separate.

API contract: https://docs.balldontlie.io/ (Games, lifecycle, cursor pagination).

