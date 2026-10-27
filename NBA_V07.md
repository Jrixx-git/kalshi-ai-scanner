# NBA v0.7 automated forward testing

Research only. No trading modules are imported by the scoreboard or its workflow.
The v0.6 model, frozen temperature 1.23, and baseline probabilities are unchanged.

## Immutable baseline

Repository: Jrixx-git/kalshi-ai-scanner. Branch: develop/paper-trading-v02.
Run: 40576182725. Artifact: 12768305225. Source commit:
e58267c2a79ca43625a6cb7012c89d5940dd1bc6.

The original ZIP is preserved byte for byte at `forward_test/baseline/artifact.zip`.
Its SHA-256 is `776d8acdcf04168b4f182cb5ea59c813869ee0fcf598878e99699320fec03171`.
The importer pins that digest, commit, run ID and GitHub artifact publication
time 2026-10-27T20:17:26Z. It verifies the CSV against its original metadata.
Four predictions are eligible: BKN at BOS, DET at NYK, SAC at SAS, POR at LAL.
This is the observed four-game slate, not a claim of independently verified
league-wide coverage. Baseline history and schedule snapshots were not provided
in v0.6 and cannot be reconstructed from the artifact. That limitation persists.

## Rules

* Archive eligibility: generation <= archive observation < listed tipoff; aware
  timestamps only; history strictly before the target NBA date; research mode;
  valid complementary probabilities; unique game IDs and distinct teams.
* Provenance: exact CSV, metadata, raw history/schedule snapshots for new runs,
  full source commit and Actions run ID. Hash-addressed manifests are written
  last as bundle completion markers. Existing bytes cannot be overwritten by
  the application. Git history supplies persistence and change audit, not WORM
  storage against a repository administrator. New-run observation timestamps
  trust the runner clock; the baseline uses GitHub's publication timestamp.
* First eligible archived forecast per BALLDONTLIE game ID is scored. Later
  versions remain archived but never replace it; conflicting team/date identity
  fails closed. Equal archive timestamps use manifest hash as deterministic tie
  break. Model changes should use a separate cohort/root, not pool variants.
* Results use authenticated GET `/v1/games/<ID>`, not fuzzy team-name matching.
  IDs survive rescheduling. Both home/away IDs must match; switched teams fail.
  A changed date with the same ID is accepted, retaining the original forecast.
  Replacement IDs are never guessed: old IDs stay missing/unresolved.
* Final requires provider status Final, no conflicting lifecycle, positive
  integer unequal scores, valid provider datetime after archive observation
  and before retrieval. Missing fields, ties and contradictory states are not
  scored. Postponed, cancelled, unknown, missing, invalid final and identity
  mismatch states are visible and excluded from metric denominators.
* One Bernoulli home-win outcome per game: accuracy uses p >= 0.5 as home pick;
  Brier = (p-y)^2; natural-log loss clips p to [1e-15,1-1e-15]. Empty denominators
  are JSON null, never zero. Daily metrics use original prediction league dates.
* Raw provider result snapshots and their retrieval timestamps are retained
  with SHA-256; the scoreboard points to its result snapshot hash and each
  result observation time. Identical result duplicates are deduplicated;
  conflicting duplicates fail. Results cannot alter archived forecasts.
* Finals are refreshed daily until a retrieval at least seven days after
  provider tipoff, then cached. `score --refresh-all` checks later corrections.
  Unresolved games are retried daily. 404 means missing; auth/network failures
  fail the run and preserve the prior scoreboard rather than publish zeros.
* This measures forecasting performance, not profit, calibration certification,
  or an established edge. BALLDONTLIE is the result provider; no independent NBA
  league-source reconciliation has been performed.

## Commands (Python 3.11+ with system timezone database or tzdata)

Run at repository root:

```sh
python -m unittest discover -v
python nba_forward_test.py baseline
# BALLDONTLIE_API_KEY must already be set in your environment; do not commit it.
python nba_daily_predictions.py --output-dir daily_predictions
python nba_forward_test.py archive --csv daily_predictions/nba_predictions_YYYY-MM-DD.csv --commit FULL_40_CHARACTER_SOURCE_COMMIT --run-id ACTIONS_RUN_ID
python nba_forward_test.py score
python nba_forward_test.py score --refresh-all
```

The root defaults to `forward_test/state`. An alternative root must be supplied
before the subcommand: `python nba_forward_test.py --root other/state score`.
Reports are `forward_test/state/scoreboard.json` and `scoreboard.md`.
No historical forecasts are regenerated to fill missed pre-tipoff predictions.
Future prediction retrieval failures still allow existing forecasts to be scored;
the workflow ends red to surface the coverage gap. Archive/push failures stop
before results retrieval. Pushes reject concurrent branch changes without force.
The pregame commit can succeed even if later result retrieval fails.

## GitHub Actions and daily scheduling

Deployment on 2026-10-27: write access was restored by installing the ChatGPT
Codex Connector on the repository owner's account. NBA v0.7 was published only
to develop/paper-trading-v02 in commit 92d561c935dd4256145a09f7da1aadc5b0849ffd.
A Codex chat automation named "Daily NBA v0.7 forward test" is ACTIVE at 19:00
Europe/Istanbul and updates only forward_test/trigger.txt on the development
branch. It is idempotent per local date and reports failures or required action.
This external Codex trigger starts GitHub Actions without changing main or the
default branch; GitHub's native cron limitation below still applies.

The initial run succeeded end to end:
https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/40579880651
It passed offline tests, verified the pinned baseline, generated and archived
new raw input snapshots, pushed the pregame archive, retrieved provider results,
pushed the scoreboard and uploaded evidence. At 2026-10-27T20:42:43Z, the four
baseline games were unresolved (unknown/non-final), so scored=0 and all three
metrics were null. No forecasting-performance claim is made before finals arrive.

`nba-forward-test.yml` tests offline first, imports the baseline idempotently,
generates today's predictions with raw snapshots, seals and pushes the pregame
archive, retrieves results and pushes the scoreboard. Both pushes explicitly
target develop/paper-trading-v02. Workflow concurrency serializes runs. Existing
scanner, paper engine, main and live-trade settings are untouched. The workflow
only needs BALLDONTLIE_API_KEY plus its repository GITHUB_TOKEN with contents
write. It uploads evidence for 90 days; Git commits are the durable archive.

The cron is 16:00 UTC daily (19:00 Istanbul, 12:00 or 11:00 New York depending on
US daylight saving). Games already started by then are skipped by v0.6. This
schedule does not promise full slate coverage. The job allows 120 minutes;
large unresolved backlogs or full-refresh audits can require a manual run with
a larger timeout. API requests are spaced 13 seconds apart for the free tier.

IMPORTANT: GitHub executes cron ONLY on the default branch. Keeping this
workflow solely on a non-default develop branch does not activate the cron.
This delivery does not change main or repository default-branch settings.
Use an existing external scheduler to dispatch this development workflow daily,
or deliberately choose develop as the default branch in repository settings.
Changing the default may affect unrelated workflows; it is not performed here.
An external scheduler with GitHub CLI authenticated for Actions write can run:

```sh
gh workflow run nba-forward-test.yml --repo Jrixx-git/kalshi-ai-scanner --ref develop/paper-trading-v02
```

Set the scheduler to `0 16 * * *` in UTC. The same command starts a manual run.
If GitHub does not register a branch-only workflow for dispatch (workflow_dispatch
also depends on default-branch registration), use the push trigger instead.
From a dedicated clean clone of develop/paper-trading-v02, an authenticated
external daily scheduler can run these commands; no default-branch edit is needed:

```sh
git pull --ff-only origin develop/paper-trading-v02
date -u +%FT%TZ > forward_test/trigger.txt
git add forward_test/trigger.txt
git commit -m "Trigger daily NBA research forward test"
git push origin HEAD:develop/paper-trading-v02
```

The push trigger is restricted to that exact branch and trigger file. Archive
commits do not match it, preventing recursion. The download includes a Windows
helper with branch, remote and clean-worktree checks for this push-trigger route.
Do not run the workflow against main. Confirm the first run is green and both
archive commits appear on develop before relying on unattended collection.

## Validation

100 offline unittest tests passed locally, including the 74 pre-existing tests
and 26 forward-test tests. Tests include real baseline import/hash/idempotence,
hand-calculated metrics, no future leakage, late archives, first-forecast wins,
identity conflicts, non-final states, malformed scores, duplicate results,
reschedules, frozen final cache/full refresh, GET-only HTTP and auth redaction.
No live API call or live trade was used for this validation. Result metrics are
not reported as measured until authenticated provider retrieval succeeds.

API contract: https://nba.balldontlie.io/#get-a-specific-game
Schedule behavior: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
