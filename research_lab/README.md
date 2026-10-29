# Isolated comparative research lab

Research only; no order/RFQ calls, production module imports, ledger writes, scheduling,
hosting changes or trial enrollment. This package is additive to development commit
`c218ab6de2003c3b50e55c93a9f45d97d1daa26d`. It does not replace NBA v0.8.

The mission remains a solo-operated, 24/7 information-advantaged platform across sports,
weather and finance. NBA/NHL/NFL/MLB/tennis/European soccer including Turkish Süper Lig
remain in scope. The phases remain viability/thesis challenge → independent provider
research → architecture/latency/economics. Current implementations are deliberately small
tests, not commitments to a provider or a reduced long-term mission.

## Run locally (Python 3.12+; standard library only)

From repository root:

```shell
python -m unittest discover -s research_tests -v
python -m research_lab.demo
python -m research_lab.runner path/to/normalized_dataset.json --evidence-root research_outputs/raw --output research_outputs/reports
python -m research_lab.diagnose
python -m research_lab.collect weather --latitude 40.7789 --longitude -73.9692 --run 2026-10-20T00:00:00Z --model gfs_seamless
python -m research_lab.collect observations --station USW00094728 --start 2026-09-01 --end 2026-10-20
python -m research_lab.collect alfred --series CPIAUCSL --cutoff 2026-10-29T12:00:00Z
python -m research_lab.collect alfred-csv --series CPIAUCSL --cutoff 2026-10-29T12:00:00Z
python -m research_lab.collect sportsdataio --resource StartingLineupsByDate --date 2026-10-29
python -m research_lab.collect balldontlie --resource player_injuries
```

`demo` creates clearly marked SYNTHETIC inputs and reports. Those scores test software,
not prediction skill. Do not present their numbers as empirical results. `runner` is an
offline walk-forward evaluator, not a prospective forecasting service. It requires labels
for evaluation, then restricts each training set to labels available strictly before that
decision. Unresolved events should stay in a separate collection inventory until labeled;
do not silently infer a loss or include them in training. A collector success is not yet
benchmark eligibility. No background process is installed.

Set existing authorized credentials via environment only: BALLDONTLIE_API_KEY,
SPORTSDATAIO_API_KEY, FRED_API_KEY. These are absent from the implementation session.
Keys are not copied from GitHub secrets or committed. The FRED key-free CSV fallback
checks the exact vintage header, rejects fallback-to-current headers, and is experimental
because that CSV endpoint has no stable documented API contract. Prefer the documented
FRED JSON interface. Missing credentials fail explicitly. Network requests use verified
HTTPS, bounded reads, no redirects, GET only, and fixed provider endpoints. Collection
errors are archived without credential-bearing URLs. No automatic retries conceal gaps.

## Common dataset contract

`demo.fixture(family)` is an executable schema example. To inspect it:

```shell
python -c "import json; from research_lab.demo import fixture; print(json.dumps(fixture('weather',1),indent=2))"
```

Top level: `family` (sports/weather/finance), `synthetic` (false for real data), `events`.
Each event: unique `event_id`, aware `decision_at`, later `target_at`,
`outcome_available_at`, nonempty dependency `cluster`, `inputs`, `outcome`.
Each input and outcome requires provider, issued_at, available_at, retrieved_at,
availability_basis and evidence_sha256. Real records require matching sealed raw envelopes.
`captured` means availability equals actual receive time; `provider_vintage` requires an
explicit availability_evidence attestation. Date-only data cannot certify intraday release
access. Imported claims must be independently reviewed: a hash proves bytes, not truth of
provider metadata or correctness of a manual feature transformation. The evaluator does
not infer historical availability from a current download, or from model initialization.

Raw JSON envelopes retain exact UTF-8 response text, public endpoint, sanitized parameters,
request/receive timestamps and status. Their SHA-256 addresses are immutable under ordinary
writes; attempted conflicting content raises an error. This is not administrator-proof
write-once storage. Results include input and implementation hashes when run via `runner`.
Keep raw snapshots private unless redistribution rights have been established.

### Sports

Legacy input is a sealed home-win probability with canonical game ID. Challenger requires
the same canonical ID, verified_unscrambled data quality, and three fixed features:
advanced_player_rating_diff, injury_minutes_diff, lineup_rating_diff. Optional `market`
is a contemporaneous home-win comparator, not an executable price or promised fill.
Use separate datasets for BDL-only enrichment and SportsDataIO enrichment on identical
game populations/cutoffs. This initial adapter does not automatically reconcile provider
player IDs, parse free-text injuries or certify historical lineups.

`normalization.player_features` combines mapped pregame minutes, lagged ratings,
availability probabilities and projected/confirmed starter probabilities. It rejects
realized minutes and mixed/duplicate identities. Archive the upstream raw evidence for
every component and use the latest component availability for the derived feature record.
Never treat a missing player as healthy. Review roster completeness before accepting a
record. The current helper is a transparent aggregation, not a validated player model.

A ridge logistic offset learns whether the features improve the frozen baseline, scaling
only on training data. Separate one-feature ablations test advanced ratings, injury minutes
and lineup ratings. Default hyperparameters are fixed, not chosen on reported test scores.
At least 20 prior labeled games are required to fit; this is a software minimum, not a
statistical success threshold. Refit is expanding and prequential, not an untouched fixed
holdout; freeze a model before a later confirmatory experiment. Models from one provider
must not be compared on cherry-picked subsets against another provider.

### Weather

Normalized records must have matching station, day, unit C and day_definition. Only strict
`>` temperature thresholds are supported in v1; other contract rules fail closed. Inputs
must be forecast_run with run_id, not reanalysis. Public input supplies a deterministic
maximum, ensemble input supplies each member's daily maximum. `member_maxima` checks full
hourly coverage over explicitly provided UTC boundaries, including 23/25-hour days. It
does not guess the station reporting day. Open-Meteo naive hourly timestamps may be made
UTC-aware only after confirming the response's utc_offset_seconds is zero.

Truth must be an official_station_daily_max observation with matching identity. NCEI
quality flags are checked by `official_tmax`; current NCEI values may include revisions.
Official station truth is not automatically the exchange settlement value: current NYC
series metadata previously named TWC, and exact rule/source/day mapping remains required.

Compare calibrated public forecast, ensemble mean plus calibrated spread, ensemble mean
with fixed residual variance (spread ablation), and smoothed station climatology. Gaussian
bias/spread calibration uses only earlier available station outcomes. Station-specific
minimum 20 prior observations. This distributional assumption is unvalidated; add season,
lead and weather-regime validation before interpreting gains. Historical member runs and
their availability evidence are not supplied by the deterministic archive. The Open-Meteo
member API documents only a short retrospective window; archive prospective members or
obtain a verified run archive. Do not substitute reanalysis or stitched short-lead forecasts.

### Finance

Initial target: CPIAUCSL monthly index growth, expressed in percent, strictly greater than
a chosen threshold. Inputs must exclude the target period and include contiguous preceding
monthly index levels from a single verified ALFRED vintage. Unknown gaps/horizons reject.
Compare last observed month growth against trailing-three growth; both have residual bias
and uncertainty fitted on earlier available first-release outcomes. GDP, unemployment,
Fed decisions and other units require explicit separate adapters/target definitions.

FRED JSON requests explicitly set both realtime_start and realtime_end to the UTC date
before the decision; defaults would return today's revised history. A previous-day vintage
is a conservative date-resolution restriction, not an intraday release timestamp. Training
targets must be separately archived first-release MoM values. Do not use current revised
CPI or incorrectly computed rounded-index differences as a contract's official release.
No nowcast scores are claimed from the API documentation's example observations.

## Evaluation and gates

Reports contain Brier score, clipped log loss, reliability bins, paired Brier improvement,
coverage counts, explicit rejection reasons, forecasts and cluster bootstrap intervals.
Intervals are suppressed below 20 clusters; bootstrap uses caller-defined dependency blocks
(e.g. weather weeks including all correlated stations). Choose block definitions before
looking at outcomes. The exploratory intervals are not multiple-comparison adjusted and
do not establish superiority. Feature/market/spread ablations are exploratory. Preregister
one primary test per family and apply multiplicity correction in the confirmatory analysis.

No empirical performance is reported in this implementation: valid comparative inputs are
not yet available. Proper scores do not imply economic advantage. The lab has no paper
entry or settlement simulator; NBA v0.8 continues separately. A later economic comparison
must use contemporaneous arrival-time books, verified event fees, partial/no fills, realistic
slippage and correlation limits. Preserve existing one-contract sizing, 30s quote/24h
forecast limits, $50 ticker/shared-team cap, $150 worst-case reservation, $500 aggregate
open cost and $5,000 simulated bankroll. No new capital budget is created by this lab.

Illustrative paired power: delta=.01 Brier and SD=.10 require about 784 independent events
for 80% power at two-sided 5%, before dependence/multiplicity. Use a pilot to estimate
variance and missingness; 20 training points or 30-50 pilot outcomes are not evidence of
edge. Predefine minimum useful effect, maximum time/cost and stopping criteria. A wide
interval means inconclusive, not failure of the entire platform mission.

## Expansion roadmap

NBA establishes provenance and comparative tooling. NHL/NFL/MLB, tennis, European soccer
and Turkish Süper Lig follow only after contract inventory, stable IDs, settlement rules,
as-of input coverage and independent sample sizes are demonstrated. Props/spreads require
appropriate score/stat distributions; winner Elo cannot price them. Weather expansion
requires station/source mapping; finance expansion requires release-specific vintages.
No provider's league coverage or premium value is assumed from marketing claims.

See `research_evidence/IMPLEMENTATION_REPORT.md` for actual access evidence, NBA audit,
provider-trial recommendations and Lightsail assessment.
