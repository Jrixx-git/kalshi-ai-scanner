# Authentic research inputs

These modules remain research-only. No operational code, historical evidence,
ledger, risk settings or scheduled NBA workflow is changed by this PR.

## Executable paths

```shell
python -m unittest discover -v
python -m research_lab.continuity --days 2026-10-28 2026-10-29
python -m research_lab.survey
python -m research_lab.authentic panel.json --evidence-root research_outputs/authentic/raw
```

The survey uses existing BALLDONTLIE and optional FRED credentials from environment
variables. On GitHub these remain inside the trusted push/manual job; PR jobs run
offline tests without provider credentials. There are no signups, trials or orders.
Raw captures and reports are content-addressed and exported as 90-day artifacts.
Missing access, empty responses, rate limits, parser failures and predictive
eligibility are reported separately. A successful survey does not mean every
provider succeeded. Re-run manually before artifact expiry if preservation is needed.

The first survey (run 40936606385, 2026-10-29 19:04 UTC) returned authentic samples
for games, basic player stats and injuries. Advanced v2 statistics and lineups
returned HTTP 401. This measures endpoint access, not an independently verified
account tier. These one-row samples are incomplete and are not training panels.

## NBA challenger

The new `lagged-pie-injury-v1` specification joins full-game advanced PIE with
basic minutes by player/game/team, aggregates only earlier completed games over
15 days, and adds captured out-player counts and history coverage differences.
It is distinct from the earlier projected-player feature prototype. No completed
current-game minutes, current lineups, assumed player projections or imputed
missing injuries are used. BALLDONTLIE documents lineups as post-tipoff data.

An NBA panel descriptor contains `game_id`, `decision_at`, the frozen `archive`
hash, `advanced_pages`, `basic_pages`, `injury_pages`, and `result_digest`.
Optional `market_digest` and `book_digest` must identify the same game and a book
within 30 seconds of decision. Every value is reconstructed from hashed raw
captures; caller-supplied numeric features are not accepted by the panel runner.
The Elo comparator retains temperature 1.23. Training requires at least 20
earlier available outcomes; uncertainty uses the shared cluster comparison.
The single-contract midpoint comparator is correctly oriented to the home team;
it is not an executable fill or profitability claim. Missing panels are rejected.

An advanced-data trial would need authentic, unscrambled historical advanced
stats and separately timestamped pregame projected minutes, injury updates and
projected/confirmed lineups, stable IDs, capture/publication timestamps, and a
sample covering both teams before the fixed decision cutoff. A trial is not
activated by this code. NHL/NFL/MLB/tennis/European soccer/Turkish Super Lig remain
in `EXPANSION_SPORTS`; no non-NBA eligibility is assumed.

## Weather

The survey captured 31 GFS ensemble trajectories before the target day, an
archived deterministic run and official station observations. These are authentic
captures, not a matched historical performance comparison. Latest ensemble
snapshots do not prove an exact model initialization or historical availability.

Captured KXHIGHNY contract rules in the first survey explicitly named **The
Weather Company**. This differs from a generic NWS assumption. The source-bound
contract parser preserves strike type/bounds and rules hashes and blocks NOAA/NWS
labels from serving as Weather Company settlement labels. Final source values,
station mapping, day boundaries, rounding and revision policy remain unverified.
The window helper supports 23/25-hour civil days and 24-hour local-standard days;
the contract, not a guessed timezone, must select the rule. Do not score the
prospective civil-day member maxima against an unverified contract window.

## Finance and hosting

The FRED path requests `output_type=4, units=pch`; revised levels are not accepted
as first-release MoM labels. FRED's daily vintage dates get conservative next-UTC-
day training availability, not an invented intraday release time. The public BLS
archive fallback parses the original headline, target month and embargo timestamp,
with its published rounding retained separately from raw transformed FRED values.
The first survey found no existing FRED credential and the ALFRED CSV timed out.
One vintage or one authentic label is not a matched predictive panel.

Survey runtime records CPU, elapsed time and Linux peak RSS for a bounded smoke
workload. Those measurements are not a 24/7 reliability or latency benchmark.
Lightsail remains a candidate; no instance, storage, account or subscription is
created. A hosting decision still needs prospective load, retention, retry,
backup/restore and operational availability measurements.

Primary references: https://docs.balldontlie.io/ ;
https://open-meteo.com/en/docs/ensemble-api ;
https://fred.stlouisfed.org/docs/api/fred/series_observations.html ;
https://www.bls.gov/news.release/archives/cpi_02132024.htm ;
https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html
