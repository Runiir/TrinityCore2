# Magmaw convergence handoff — 2026-08-22

This is a diagnostic history, not an acceptance claim. All twelve retained runs
used exact clean source/build/config identities, produced classified telemetry,
observed native shutdown, returned bots and leases to zero, and recorded no
forbidden assistance.

## What worked

- Raid admission now forms one native raid before the seed leader enters the
  instance, adopts that group for the cohort, and survives the solo-map LFG
  cleanup path.
- Hunter pet and equipped-gear identities are frozen in the admission receipt;
  later checks reconcile against that receipt.
- Restarting an attempt clears stale raid-runtime state.
- Capture-side gear comparison ignores only trailing zero gem padding. Item,
  enchant, non-zero gem, and reforge mismatches still fail closed.
- The route consistently clears the entry regroup and Chainwielder nodes and
  reaches `bwd.magmaw.drudges`.
- Partial deaths on trash no longer wait for a manufactured full wipe after a
  stable native reset. Dead bots now enter the ordinary corpse-run path.
- The watchdog now emits a typed gameplay failure instead of misclassifying
  the Drudge failure as infrastructure loss.
- The `22282882a0` shard passed deterministic provisioning and exact ten-member
  DB readback, cleared the entry regroup and Chainwielder, and shut down its
  owned server cleanly after a typed gameplay failure.
- The `5756bb492f` shard proved the dead-hunter pet gate repair: the former
  `validation_active_hunter_pet_missing` failure did not recur, ordinary death
  recovery was reached, and the watchdog closed the next attributable edge
  without a retry.
- The `ea84aba64a` shard proved that the invalid-final-floor admission change
  can commit one ordinary local movement segment. Both dead tanks moved from
  the native graveyard to `(-7334.46,-1626.77,283.392)` before the greedy
  progressive planner rejected the next non-monotonic corridor edge.
- The `d98451124d` canary accepts `native_runback_nonmonotonic_path_rejected`:
  route generation 3, node index 2 (`bwd.magmaw.drudges`), recorded one kill,
  two deaths, and eight living bots. Cleanup passed with no forbidden
  assistance.

## What did not work

| Source | Result | Decisive observation |
| --- | --- | --- |
| `dd554843f7` | infrastructure abort | A real Drudge stall was hidden by the trailing-zero gem mismatch. |
| `8ef7d2f25c` | gameplay failure | Hunter pet admission failed before Drudge evidence converged. |
| `198bac19d6` | gameplay failure | Four Rushes landed, but exact ownership/re-separation never formed. |
| `43521ba995` | gameplay failure | Only one Rush landed; hunter pet admission regressed during the extended pull. |
| `69b230aae5` | gameplay failure | Four Rushes landed, but ownership/re-separation still failed and three bots died. |
| `f3768b83d9` | infrastructure abort | Chainwielder cleared and the raid recovered from early deaths, but two dead tanks waited for a manufactured full wipe while eight survivors idled at the reset Drudge pack. The semantic watchdog closed the run after 302.8 seconds without progress. |
| `04751b3306` | gameplay failure | The false full-wipe wait was removed. Two dead bots entered native corpse runback while eight survivors held inside the instance, but one bot exhausted six attempts with `native_runback_no_progress`; the watchdog closed the run at 278.8 seconds. |
| `22282882a0` | gameplay failure | The progressive native-rejoin repair was compiled, but no dead member left map 669, so that edge was not exercised. At 435.3 seconds a dead hunter had no active pet while its pet DB row remained intact; `validation_active_hunter_pet_missing` ran before dead-bot recovery and terminalized the shard with six survivors. |
| `5756bb492f` | gameplay failure | The dead-hunter pet gate did not recur. Three dead members released to map 0 while seven survivors remained inside. All three stayed at the same graveyard position while entrance movement returned `native_instance_runback_path_retryable`; the first tank exhausted six attempts and terminalized as `native_runback_no_progress` at 273.858 seconds. |
| `ea84aba64a` | gameplay failure | Two dead tanks released to map 0 and each committed three `native_instance_runback_moving` decisions, reaching one shared local endpoint. The next winding-corridor edge did not reduce straight-line distance to entrance trigger 6581, so the planner returned `route_destination_invalid_floor`; the first tank exhausted nine attempts and terminalized at 283.884 seconds. The full-wipe aggregate remained false because eight members were alive, but per-bot diagnose/trace proves individual recovery was active. |
| `d98451124d` | gameplay failure | The single canary reached Drudge generation 3 with one kill, two deaths, and eight alive. Ghost 30001 reached `(-7482.93,-1383.73,416.785)`, stopped for more than 30 seconds, and terminalized; ghost 30002 reached `(-7530.67,-1258.93,471.885)` and remained `native_instance_runback_moving`. No trigger/reclaim/rejoin was observed; the watchdog closed `native_runback_no_progress` at 304.114 seconds. |
| `a09d5a83c4` | gameplay failure | The one-run verification reached Drudge generation 3 with one kill, two deaths, and eight alive, but submitted zero `native_instance_runback_repath` actions. Ghost 30001 terminalized at `(-7482.65,-1383.71,416.664)` while ghost 30002 remained moving at `(-7482.93,-1383.73,416.785)`. No trigger/rejoin occurred; the watchdog closed `native_runback_no_progress` at 309.101 seconds. The prior `native_runback_progress_witness_and_single_repath` implementation is rejected because its repath branch was unexercised. |

The three Drudge policy edits after `8ef7d2f25c` did not converge and are not
promotion-ready. Affliction SQL changes are also unpromoted until a fresh exact
300-second self-provided-consumables canary proves the result.

## Current acceptance policy

Trash does not need a flawless formation. Individual deaths are acceptable
when the trash pack dies, the raid does not wipe, native recovery succeeds,
and the route continues. A re-separation deadline is therefore diagnostic; it
must not terminate a run while hostile-health or kill progress is monotonic.
Raid and dungeon success remains completion-driven, never time-driven.

## Next bounded work unit

The dead-hunter pet gate and invalid-final-floor hypothesis remain consumed, but
the `native_runback_progress_witness_and_single_repath` implementation is
rejected because the a09 canary never exercised its repath branch. The single
next work unit is `native_repath_lease_expiry_predicate`, owned by
`raid-bot-runtime-implementation`: `BuildMovementRequest` sets
`ExpiresAtMs=nowMs+1500`, while recovery decisions recur at about 1500 ms, and
`matchingNativeRecoveryPath` checks `ExpiresAtMs>nowMs` before the typed move can
refresh the lease. Remove lease freshness only from observation/repath matching
of an already-admitted active recovery native path; preserve the recorded
Recovery owner, active path, attempt/wipe/route/destination/traversal scope,
and every existing terminal bound. Add deterministic before/equal/after expiry
predicate coverage. Use one implementation hypothesis and one matched
completion-watchdog shard. Do not add coordinates, waypoints, teleport,
resurrection, or boss/class/pet/Drudge tuning.

## Evidence

The twelve immutable diagnostic bundles are tracked by adjacent `.dvc` pointers.
The latest report hashes are:

- `198bac19d6`: `4c157675ff37d400c8ae0dba6672b40625c7262373115eedfaa2739057d80e2e`
- `43521ba995`: `ee2f8487b40d4d229e5d06f41b047cb9aea38e0a2637391e234d16b75986ddc2`
- `69b230aae5`: `5214b36af63b8082244bc167786467dedef5e91573ad3e467d79cd5685144f0f`
- `f3768b83d9`: `d928b29fcc08aba19fe2b25fe13b2bb3e769231b248e278ed849b8c3f26b4378`
- `04751b3306`: `e8e5e61996da532ce13ba478895b501ec256f849dcdc07b0b97791aa0add5869`
- `22282882a0`: `1194187be0ba4581b5cbb1da2c5cc9aef9f24f95332598f5a554e8e4daf54b0a`
- `5756bb492f`: `85e88cfff9ca7fada210217ac64760bba7a2a778d69ca3fd0429cc1f7b928db1`
- `ea84aba64a`: `b54847e3be211261a9f49673cbb5cb3a65fa90d9259ebd5305074bcedecfc9ed`
- `d98451124d`: `462dcd4b06c3e729ec87d5e7dcccb1efc1e10617ec77036a8f93aaf78807ff10`
- `a09d5a83c4`: `df293bf0c94d3d28c5a6b36e5b48cdd58aa419cb35535a07151fcde50f99c9d9`

The d984 canary is bound to source commit
`d98451124d343fdb49ae6718c70cd4dfdfb9f762`, worldserver binary SHA-256
`0b74313eea45f657d983dec6d11a7b2d4340811e64822ca91cf8162962cc7eb8`, and
the DVC pointer
`artifacts/cata_raid_program/phase1_foundation_d98451124d_magmaw_run01_20260822.dvc`.
The retained report file SHA-256 is
`6527e539440cf93a096d4b6bafd247db1595a2ec9b8f5424b60c7503e179f7e8`.

The a09 canary is bound to source commit
`a09d5a83c4052a685f38c705765ee6edb6c12f38`, worldserver binary SHA-256
`b8d7bf129ce9324dd01048b3931b02305f4611151baf68d8ca2fe888e6a418a8`, and
the DVC pointer
`artifacts/cata_raid_program/phase1_foundation_a09d5a83c4_magmaw_run01_20260822.dvc`.
The retained a09 report file SHA-256 is
`81e72636605d03bcb5ffa72981aa5e28a8fedc7d1ad4b3c366dfed3e95da15e9`.

The DVC cache and configured remote were verified in sync after publication.
