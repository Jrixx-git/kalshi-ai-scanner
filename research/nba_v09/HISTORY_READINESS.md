# Receipt-time readiness audit — November 11, 2026

This first section records the initial history-only audit. The prospective
activation update below supersedes its zero-seal operational status.

Collection run: https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43081899525
Source commit: eb477cde487077a1c9c37bf2e7040b3c13fbb22f.
The existing BALLDONTLIE Actions secret was used without disclosure.
The original manual workflow was not registered in the Actions UI and local
GitHub sign-in was unavailable. A narrowly path-triggered bootstrap ran the
same collector on develop; no default-branch or operational workflow changed.

| Season starting year | Complete pages | Unique records | Verified finals |
| --- | ---: | ---: | ---: |
| 2025 | 14 | 1,322 | 1,322 |
| 2026 | 13 | 1,200 | 160 |

These are complete provider pagination responses, not an assertion that every
future fixture or canceled game is present. The 2026 response includes 1,040
non-final scheduled records. New receipts span 18:52:56–18:53:01 UTC on November
11 (12:52–12:53 PM Central). No history was backdated. All raw hashes, receipt
hashes, manifest hashes, season IDs and duplicate IDs passed verification.

The artifact contains 57 files: 27 raw pages, 27 receipts, 2 complete collection
manifests and 1 readiness report. ZIP size: 147,044 bytes. SHA-256:
`370bcca4acf0906844e02a46d89b383a063658888e9b7eb872ba5edd22d14217`.
Artifact ID: 13885021636; retention ends February 9, 2027.
Permanent isolated copy: branch `research/nba-team-history-evidence`, commit
`ee30520b91c013c39f1818c94f6b5b96aee95ef0`, under
`team-history-runs/43081899525-1/`. Preservation was verified after upload.

## Eligibility and older archives

All 28 operational bundle manifests and their referenced files passed hashes.
They contain 118 unique pregame Elo forecasts. Twenty-seven bundles contain
normalized historical game snapshots. Those snapshots retain genuine bundle
observation times, but do not provide the complete exact raw-page receipt chain
required by the new team-history verifier. They were not rewritten or converted
into invented historical page receipts or 60-minute input seals.

The separate pilot evidence branch at commit
`9c891428867808c563d11905b6e7621a9dafc2d6` contains one hourly slot: 14 upcoming
games (10 November 11; 4 November 12), 2 provider page receipts, independent
schedules and market evidence, with no source errors. It contains no completed
historical season collection or challenger input seals. It cannot supply the
missing training cohort or be relabeled as chronological validation.

Qualifying development seals: **0**. Eligible training: **0 / 100**.
Eligible later validation: **0 / 30**. Models trained/frozen: **0**.
Challenger shadow forecasts launched: **0**. The 1,482 final outcomes downloaded
today are available only from their actual receipt times onward.

## Safe prospective collection improvements

The new readiness workflow retains full and partial evidence in artifacts and
appends each run to a separate archive branch without force pushes. Later runs
restore prior content-addressed receipts, preserving first-observed finals.
It has no schedule. Manual `collect_development=true` additionally collects
provider and independent universes, then supervises the existing cutoff runner
for at most two hours. It uses `forward_test/state` explicitly, retains missing
independent identities, and has no model argument, fitting step or trading hook.
Late/missing games remain coverage records. Startup before the relevant cutoff
and successful archival still need operational demonstration; no reliable
ongoing worker or automatic daily deployment is claimed.

For later training, combine complete receipts and development inputs from the
isolated run directories without replacing conflicting files. Re-run the full
existing training verifier and select a chronological split only after at least
100 qualifying training and 30 later validation games exist. Never reconstruct
pregame seals for elapsed cutoffs. Freeze only at the actual fit time.

The original v0.8 code, forecasts, archives, ledger, $5,000 paper bankroll and
$50 position / $150 daily loss / $500 open exposure limits are unchanged.
No paid service, SportsDataIO values, real orders, or extra Work chats were used.

## Prospective activation — November 11 evening, Central time

Final collector source: `26b5c6ddda0336ff22fac4719163bfe2b4092243` on
`develop/paper-trading-v02`. Default-branch launcher:
`875156b810effb7e047e394ec25f9098df99e45c`.
The launcher pins that exact source and calls the separate research workflow.
Existing operational workflows were not edited.

The corrected live run succeeded:
https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43129916064
It started at November 12 01:00:11 UTC (November 11 7:00 PM Central),
checkpointed authentic source evidence before waiting, sealed two future games,
verified the complete cohort, uploaded the final artifact, and completed the
second durable append at 02:00:08 UTC. Both archive steps passed.
An actual scheduled follow-up also succeeded without duplicating any input:
https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43132082331

All **277 offline tests pass locally and in GitHub Actions**:
https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43127261290
Tests cover real Git staging/checkout byte preservation with Windows conversion
enabled, repeated depth-one fetches and unforced pushes, interleaved authentic
recovery appends, the first schedule response's receipt clock, missed cutoffs,
clock reversal, wait budgets, duplicate slots/games, independent omissions,
raw/receipt tampering and chronological outcome availability.

### Actual captures and readiness

The complete shared training-input verifier was rerun on the durable archive
at **2026-11-12 02:03:40 UTC**, November 11 8:03 PM Central.

| Measure | Verified count |
| --- | ---: |
| Unique development seals | **7** |
| Missing baseline Elo | **0** |
| Incomplete feature vectors | **0** |
| Eligible completed training games | **0 / 100** |
| Eligible later validation games | **0 / 30** |
| Challenger models trained/frozen | **0** |
| Challenger evaluation forecasts launched | **0** |

No sealed target yet has a qualifying final-outcome receipt in this audited
snapshot. Inputs are genuine prospective captures, rather than completed
training examples. The workflow never fits a model. Outcomes must arrive after
tipoff, and the existing 100-training/30-later-validation gate remains intact.

The seven games are `21718082`, `21718083`, `21718085`, `21718086`,
`21718087`, `21718089`, and `21718090`. All feature starts were less than
0.4 seconds after the planned T-minus-60 cutoff; every seal finished within
0.4 seconds of its actual feature start. The final corrected captures were:

| Game | Actual feature cutoff UTC | Actual seal UTC |
| --- | --- | --- |
| 21718089 | 2026-11-12 01:30:00.000129 | 2026-11-12 01:30:00.380998 |
| 21718090 | 2026-11-12 02:00:00.000157 | 2026-11-12 02:00:00.376467 |

The provider/independent universe includes ten November 11 games and four
November 12 games. Seven November 11 games qualified. The three missed IDs
`21718081`, `21718084`, and `21718088` remain missing, with their original
rejection/late-run records. The four next-day games remain future coverage
targets, not missing training labels. Coverage files are observations per run;
their summed reason counts are not counts of unique missing games.

### Durability, live fixes and authentic recovery

Corrected run's prepared artifact: **13905750484**, SHA-256
`5a2669ae3622d85e92d9a30f30667ba17f41271cf3e7ac523e105e28a838704c`.
Final artifact: **13907853856**, 8,194,171 bytes, SHA-256
`2ac0d220f067a44eb178f5b6d612029a3e69e2671e85ef2c22acaa0c723ac9ca`.
Both have 90-day retention, ending February 10, 2027.
The persistent copy is `research/nba-team-development-evidence`.
Corrected final append: `eaee36597a6e4a9a9721c2370a9b7b02dc7aa09a`.
Verified scheduled follow-up snapshot:
`12fb10ae1d0c8eeae6f12373aefa72f595a298e2`.
The exported durable ZIP's SHA-256 is
`244d952c3cda6743efa461f4d89d5369c83692fcfc946753f9dc62613a36c4da`.

Live checks exposed two errors before the final source was pinned. A fresh
schedule was initially checked against time sampled before its response arrived,
rejecting the first game in each group. The verifier now samples time after
receipt. A repeated depth-one fetch also rejected a shallow tracking-ref update;
archive refresh now uses FETCH_HEAD, while server pushes remain ordinary
fast-forwards. Archive staging preserves remote files added by authentic recovery
during a wait, rejects conflicting replacements and prevents deletions. The
corrected final append demonstrably retained those concurrent recovery records.

Bootstrap run **43086607501** succeeded and retained two original 23:00 UTC
seals. Scheduled run **43115044146** captured three more at 00:00 UTC, but its
final branch append failed. Its complete artifact **13901912182** was downloaded
and verified against SHA-256
`46870868cee9b0d9162767a41fc6bf27ce5c9e7db5c8af460a875476bc081ea8`.
Every overlapping archive file matched exact bytes. Only missing originals were
restored at `94a4da794446b437cf632f8f4ad1da2fadbc0025`, including all three input
files and their original receipt/seal times. This was recovery, not new sealing.

Superseded run **43122432936** added no new input. Its complete closure and
missingness records were retained from artifact **13905561119**, SHA-256
`19e23f01da56e66ad3d00063c5468f1e9cdeccbbff57acdbd729fc6098a1fdf7`,
at `71d5e0b4541f0b8a0582a7d62736e7c1a5f9bf76`. Original and corrected runs,
their failed attempts, and all missingness remain auditable.

GitHub [reported a major Actions outage](https://stspg.io/jdjlq5zjyl48) during deployment; delayed starts and
pending-run cancellation were observed. A separate local backup was prepared
from authentic already-archived raw history and original fixture/Elo references.
It resumed after its cutoff and wait budget and correctly created **zero seals**.
Its closed, noncanonical evidence is retained at
`research/nba-team-outage-backup-2026-11-11`, commit
`bf1d3cc7db25c4d22c4f27ad410255fdbc87b920`. It contributed no cohort records.

### Legacy evidence and future scheduled behavior

The deeper legacy audit verified **118/118** forecasts before their T-minus-60
cutoffs and all at temperature 1.23. **114** unique games have normalized history
snapshots across the 27 history-backed bundles; all 28 bundle manifests and
referenced files pass hashes. These legitimately establish baseline availability
and original fixture identity. They do not provide the missing exact raw-page
receipt chain or contemporaneous development seals. Their metadata explicitly
does not independently certify history availability or schedule completeness.
They were not converted into invented page receipts or old cutoff seals.
Even 118 games alone cannot meet the 130-example minimum cohort.

The original Elo archives are reused as baselines for still-future captures.
Features use only authentic raw receipts available by each actual cutoff.
First-observed finals remain immutable; later downloads cannot establish earlier
availability or replace an old seal. No historical forecast was regenerated.

Hourly calls at minute 07 UTC supervise at most one hour of upcoming cutoffs.
Actual UTC starts determine slots and eligibility, with monotonic wait limits;
late or unknown games remain explicit coverage. Exclusive actual-hour and worker
claims plus immutable per-game inputs prevent duplicate cohort admission.
Both provider and independent universes survive market/source missingness.
Full and partial evidence is checkpointed before waiting and retained again
afterward, in artifacts and on the isolated append-only evidence branch.
Raw/baseline bytes are protected across platforms, and evidence restoration
cannot replace the pinned executable source. See DEVELOPMENT_COLLECTION.md.

The collection window ends **November 25, 2026 at 18:00 UTC / noon Central**.
There is no automatic extension or model fit. Later events cannot collect new
provider/public-source data outside that window. The blockers are completed,
qualifying outcomes and sufficient chronological cohort size; no safety gate
was relaxed to fill either count.

The v0.8 operational source, original forecasts, paper ledger, $5,000 simulated
starting bankroll and $50 position / $150 daily loss / $500 open exposure limits
are unchanged by this work. Only the existing BALLDONTLIE secret and public
Kalshi/settlement-schedule/official NBA sources were used. No new subscription,
SportsDataIO values, real-money order, or additional Work chat was introduced.
