# Team-only challenger: scoped, not activated

The frozen operational Elo implementation, temperature 1.23, sealed forecasts,
paper ledger and risk limits remain the control. No production substitution.
The historical 102-game matched sample is exploratory and cannot be a new test set.

## Inputs and cutoff

Use only authentic BALLDONTLIE completed team games from the existing entitlement.
For each team compute rest calendar days since its previous final game (cap at 7),
back-to-back indicator (previous game on preceding league date), mean point
differential and win fraction over its preceding 5 and 10 final games, plus
home/away win fractions over preceding 20 games in the relevant venue. Retain
sample sizes; insufficient history means missing, never zero or imputed health.
Home indicator is explicit; travel, injuries, players and SportsDataIO are excluded.

Archive each raw history page with real request/receipt times and its SHA-256.
Require valid team identities, unique games, verified final status and final
scores. A history game must have occurred before the target league date AND
its final result must be retrieved before the forecast cutoff. Later corrections
cannot rewrite an earlier feature or forecast record. Revised tips require new
versioned schedule evidence and must never move an old forecast backward.

## Fit and freeze before prospective evaluation

Candidate: regularized logistic regression using frozen Elo log-odds as an
offset plus standardized home-minus-away features. Fix transformations,
coefficient fitting window, regularization, missingness rules and model hash
in a separate implementation review before any evaluation forecast. Train
only on games before that freeze, with chronological validation for all tuning.
Do not select coefficients from the current prospective evidence pilot.

## Prospective evaluation

Seal challenger and baseline probabilities before tipoff at a preregistered
60-minute target cutoff. Select the first complete quote received in the
60-to-30-minute pregame window; hourly collection alone may miss that window,
so a dedicated cutoff scheduler is a prerequisite to launching this protocol.
Use actual receipt times, never idealized target timestamps. No retrospective
reconstruction, quote selection by price/outcome, or replacement of the frozen
operational baseline. If a paired forecast or quote is absent, retain the game
and reason in the full provider/independent-schedule denominator.

Compare home-team probabilities on identical games: frozen Elo, challenger,
Kalshi home-contract bid/ask midpoint. Report Brier score, log loss, calibration,
coverage and missingness, and prespecified disagreement bins; show date-block
uncertainty intervals. Score only verified final outcomes. Evaluate after 200
paired games and at least 30 league dates; publish interim coverage without
changing model parameters. Market midpoint is not an executable fill.

Any fee-adjusted trading analysis remains a separate counterfactual requiring
contemporaneous fees, depth and slippage. No promotion to the paper engine or
live trading is authorized by prediction accuracy alone.

## Implementation status, November 11

The timestamped archive, feature builder, fixed regularized fitter, immutable
model writer, bounded cutoff runner, separate forecast stream and same-game
comparison are implemented in `nba_v09_challenger.py`. See
`TEAM_CHALLENGER.md` for the frozen candidate specification and run commands.
Real history collection, qualifying sealed development rows, a fitted model
and deployed cutoff-service reliability remain unverified. No trained
challenger, real shadow result or prospective edge is claimed.
