# NBA retrospective Elo-offset research v1

This is a separate protocol (`nba-retrospective-elo-offset-v1`). It does not replace or change `nba-team-offset-v1`, its genuine receipt gates (100 training + 30 later validation games), its collector, immutable operational Elo, v0.8 forecasts, ledger, risk limits or trading settings. No orders, subscriptions or SportsDataIO data are used.

## Provenance and reconstruction

Training source: the original BALLDONTLIE raw pages, real download receipts and complete collection manifests in `team-development/team-history` at evidence commit `09dfa3f7333356cb46a5f963e36eb6586be92619` on `research/nba-team-development-evidence`. The loader verifies their exact hashes and selects the first observed final for each game. It retains actual receipt times. These are retrospective downloads, not historical pregame availability evidence. Historical corrections may already be reflected in the downloaded scores; original release versions are unknown.

Use completed games from 2025 and 2026 seasons, starting 2025-10-01. Exclude the entire target league date and every later date from each feature and Elo state. All games on one date use the same pre-date ratings; apply K=20 updates after that entire date. Initialize ratings at 1500, home advantage 65, fixed temperature 1.23. This historical Elo is reconstructed from the available 2025-onward history and is **not** a claim to reproduce the operational baseline's longer history or archived forecasts.

Seven home-minus-away features: rest (capped at 7), back-to-back indicator, mean score margin and win rate over the last 5 and 10 games, and home/away venue win rate over the last 20 venue games. Require full windows; missing features abstain. History carries across seasons. No injuries, future schedules, market prices or postgame player statistics are features. Provenance metadata never enters fitting.

## Fixed split and model

Training dates strictly before 2026-10-01; validation dates on or after 2026-10-01 and strictly before the actual data cutoff date. Fixed L2=0.1, 2,000 full-batch steps, learning rate 0.1; no hyperparameter selection or refit on the holdout. Mean/scale fit only on training. Logistic regression uses reconstructed calibrated Elo log-odds as a fixed offset. Minimum historical counts are 500 training and 100 validation; these are independent gates, not exceptions to the original prospective protocol.

The initial frozen artifact contains 689 training games (2026-01-11 through 2026-06-13) and 174 validation games (2026-10-20 through 2026-11-12). Earlier games initialize Elo and feature windows. Exclusions are archived with the dataset. Holdout results: reconstructed Elo Brier 0.20276872, log loss 0.58894489; challenger Brier 0.20335184, log loss 0.58715581. Calibration bins and ECE are stored in the model. Mixed results do not demonstrate an improvement or a tradable edge. This is a retrospective validation set, not a blinded or prospective market test; no historical Kalshi result is claimed.

The deterministic model hash covers policy, implementation hashes, dataset hash, scaling, weights and validation. Actual UTC freeze time is stored separately and never backdated. Frozen artifact: `research/nba_retrospective_v1_final/frozen.json`. Model SHA-256: `c09d05fad7e7dc56b79ef5e9b42d3d36dac0a367edddacbc07a2f009104d26ee`.

## Reproduction

Extract `team-development/team-history` from the pinned evidence commit, then run:

```text
python nba_retrospective.py reproduce --history TRAINING_SOURCE/team-development/team-history --output research/nba_retrospective_v1_final --frozen research/nba_retrospective_v1_final/frozen.json
python -m unittest discover -q
```

The reproduction command refits from verified raw evidence at the frozen data cutoff and requires exact equality with the complete frozen model, including validation. The dataset archive records all rows and exclusions; its metadata contains the verified source-game digest and honest retrospective provenance.

## Genuine forward evaluation

The separate shadow workflow reads existing prospective development seals and original baseline archives without writing them. Freeze must actually precede the feature cutoff. Features are reconstructed again using only raw responses genuinely received by that cutoff; baseline identity and digest must match. Inputs must be sealed in the existing 60-minute window; actual shadow publication must be before tipoff, with 30–60 minutes remaining. No late game is backfilled. Each model/game forecast is immutable.

After sealing, obtain a fresh independent schedule and public Kalshi quotes using the existing bounded GET-only capture. Score with the existing contract-identity and quote verifier, using only the same future games with Elo, challenger, verified market quote and verified final. Reports retain missing shadows/quotes/finals and their reasons, calibration, paired counts, date-block uncertainty and the existing 200-game/30-date evaluation gate. The canonical market midpoint is a forecast comparator, not proof of an executable fill. Forecasts can exist without a market comparison; unpaired games remain excluded from three-way metrics.

Forward evidence is append-only on `research/nba-retrospective-v1-evidence`, separate from historical training and original prospective evidence. Scheduled workers remain bounded by the existing approved collection window ending 2026-11-25 18:00 UTC. A schedule activation is not evidence that a first eligible forecast or completed comparison exists; verify workflow artifacts and durable commits. No automatic retraining, promotion or trade execution occurs.
