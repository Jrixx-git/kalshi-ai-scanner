# Receipt-time readiness audit — November 11, 2026

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
