# Comparative research implementation — 29 October 2026

**Working isolated prototypes; no empirical predictive-superiority finding.**

Base audited: development commit `c218ab6de2003c3b50e55c93a9f45d97d1daa26d`.
Only new research_lab, research_tests and research_evidence files are proposed remotely.
No operational code, ledger, historical forecasts, workflows or risk controls are modified.
No new scheduler, API purchase, cloud resource or live execution is enabled. Abey is not involved.

| Track | Implemented | Actual evidence / current limit |
|---|---|---|
| Sports | Provider interface, BDL collector, SportsDataIO projected lineup/player projection collector, canonical identity and provenance gates, regularized challenger and three feature ablations | No local BDL/SDIO credentials. No paired authentic challenger sample or predictive comparison. |
| Weather | Archived deterministic-run and NCEI collectors; hourly/member aggregation; official quality gates; calibrated public/ensemble/spread-ablation comparators | HTTP 200: 168 hourly forecast values and 50 official daily observations. Matched historical ensemble availability and settlement day/source mapping remain absent. |
| Finance | Explicit ALFRED vintage collector, strict experimental CSV fallback, CPI persistence/three-month nowcast baselines with prior residual uncertainty | FRED key absent; key-free ALFRED CSV request timed out. No valid release-vintage evaluation dataset. |
| Shared | Content-addressed evidence, UTC availability checks, chronological training, Brier/log loss/reliability, clustered intervals, rejection inventory | Imported metadata/feature mappings still need human verification. Synthetic runs validate execution, not skill. |

## Existing NBA model audit

At the pinned base, nba_daily_predictions.py consumes BALLDONTLIE completed game outcomes.
It starts ratings at 1500, uses K=20 and home advantage 65, updates after each league date,
then applies fixed temperature 1.23. It excludes games on/after the target league date and
rejects already-started schedule entries. Inputs are archived by the existing forward flow.
It uses no advanced player, injury, lineup, projected-minutes or tracking features. This is
calibrated Elo, not an injury-informed predictive service. nba_calibration.py explicitly
labels its retrospective test as previously reviewed/exploratory. Historical provider
corrections are not independently certified point-in-time. The lab therefore consumes sealed
legacy forecasts rather than regenerating or replacing operational forecasts for comparison.

## Connectivity investigation

At 18:01 UTC (21:01 Istanbul), restricted execution returned DNS errors for all seven tested
hosts. The same diagnostic with network access granted resolved all seven. Verified TLS
succeeded for BDL, SDIO, FRED, Open-Meteo, NOAA and GitHub. Kalshi external-api alone failed
with verification code 18 (self-signed certificate). This establishes two separate failures:
restricted network access and a Kalshi-specific certificate trust failure on this route.
It does not prove the origin is misconfigured or identify interception versus local policy.
No certificate verification was disabled and no unknown certificate was installed.

Next diagnostic action: have the network administrator inspect the trusted route/certificate
chain for that exact host or verify from an independently trusted machine. Use an approved CA
bundle only if its provenance is established. Moving to Lightsail is not a demonstrated fix.

Diagnostic evidence hashes:
- Restricted: a5aa65814f4795c90ac1d05d905b4fda26c83e84ac503a42b5b51337a46eb630
- Network access granted: d15e369828a183727fdaefea9f219b4ea04dbd71946c7bbc19214161b7153dcf

## Actual weather/access evidence

At 18:02 UTC, the archived-run endpoint returned 168 hourly Celsius values for GFS,
initialization 2026-10-20 00 UTC, near Central Park. This is an actual forecast archive,
not reanalysis. NOAA returned 50 daily TMAX records for USW00094728, Sep 1–Oct 20.
The parser checked units, full hourly coverage on a sample UTC day and an official quality
flag. The example UTC-day forecast and station observation have different dates/windows;
they are not compared or turned into a score. No as-of release claim is inferred from HTTP 200.

- Forecast raw envelope: 4f58119a55b3fedbed7190c41aead5c7b6ca17399e518b40c9e8337f9d56df9f
- NOAA raw envelope: 600fc8d6044a3a3a5e99386e0c6c6abc2ce4756bcf8f098504774c3a7fd871f8
- ALFRED CSV timeout: cca092305820079d14ec123ad9ecbd32ebfdd3462f9669efb8c02024294e7492
- Access assessment: 0792cfb6d71dd7d2eccae562c13fe9c96eef367bfe267f8e211807be9342757c

Actual local raw envelopes remain under research_outputs/raw; diagnostic/access summaries
are included with this change. Full provider data is not automatically redistributed in Git.

## Provider-trial decisions for user approval

1. **SportsDataIO: conditional first candidate for an evaluation sample.** Require authentic,
   unscrambled historical pregame lineup/injury/minutes projections, publication/update
   timestamps, revision policy and stable player/game IDs for the same games as BDL. Verify
   rights to retain research snapshots and compare outputs. Generic scrambled trial data can
   test parsing only. No superiority, historical entitlement or price is established.
2. **Existing BALLDONTLIE entitlement: inspect before any incremental purchase.** Its docs
   list advanced stats, injuries and lineups, but current endpoint existence does not establish
   historical as-of snapshots or entitlement in the existing subscription. Capture prospective
   updates and evaluate identical features with identical model/cutoff before comparing vendors.
3. **Weather premium trial: defer.** Public deterministic run and station access already work.
   First establish member archives and publication timing; a paid trial is worthwhile only if
   it fills that demonstrated gap with real historical samples. Reanalysis does not qualify.
4. **Finance premium trial: defer.** Obtain an authorized FRED key and first-release target
   archive. Candidate paid gaps are timestamped consensus distributions, revision histories,
   nowcast vintages and licensed high-frequency inputs. No premium provider is validated.

Approve a tightly bounded, no-renewal SDIO sample only if those conditions are met; no signup,
sales contact or trial activation was performed. No recommended premium purchase at this stage.

## Lightsail suitability (assessment, not deployment)

AWS's official Linux/public-IPv4 table lists $7/month for 1 GB, $12/month for 2 GB with
60 GB SSD, and $24/month for 4 GB with 80 GB SSD. These are instance prices, not an all-in
quote; region, storage/snapshots, transfer overages, taxes, logging and provider licenses
need a scoped budget. IPv6-only savings require provider reachability checks.

Inference: a 2 GB instance is a plausible starting candidate for bounded collectors and
small standard-library models. This is not a measured capacity claim. Full weather grids,
large ensemble retention or batch retraining may exceed it. Measure peak memory/disk growth,
request completion time and uptime on representative workloads first. A single instance is
a failure domain; supervised jobs, clock sync, durable external backups, tested restore,
secret handling and alerts are necessary before a 24/7 reliability claim. Do not migrate
the operational NBA pipeline merely to host these prototypes. Region-to-provider latency
has not been measured, and no low-latency trading claim is supported.

## Verification and open gates

The reproducible offline suite tests hash tampering, timezone/availability rejection, future
and delayed labels, scrambled/reanalysis rejection, source identity, missing vintage periods,
public endpoint restrictions, official observation quality, full-day coverage and synthetic
labeling. All three synthetic demos execute. See validation.json for the final executed count.
Existing production tests are not claimed rerun locally; remote CI is a separate check.

Next data gate: matched authentic records at one fixed decision cutoff, all eligibility and
missingness reasons, archived labels and market benchmarks. Next inference gate: a frozen
holdout with proper scores, useful effect size and dependence/multiplicity-aware uncertainty.
Next economic gate: executable prices/fees/latency and net utility after all recurring costs.
No current result clears these predictive or economic gates.

## Primary sources consulted

- BALLDONTLIE NBA documentation: https://docs.balldontlie.io/
- SportsDataIO NBA endpoints: https://sportsdata.io/developers/api-documentation/nba
- SportsDataIO trial scrambling: https://sportsdata.io/help/faq
- Open-Meteo run archive and initialization/availability distinction: https://open-meteo.com/en/docs/single-runs-api
- Open-Meteo ensemble archive limits: https://open-meteo.com/en/docs/ensemble-api
- NOAA NCEI data API: https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation
- FRED observations/vintage parameters: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- ALFRED real-time semantics: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- AWS Lightsail pricing: https://aws.amazon.com/lightsail/pricing/

Documentation was retrieved October 29, 2026. API availability and pricing may change;
documentation supports capabilities, not this account's entitlement or predictive accuracy.
