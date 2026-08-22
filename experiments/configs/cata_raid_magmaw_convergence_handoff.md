# Magmaw convergence handoff — 2026-08-22

This is a diagnostic history, not an acceptance claim. All ten retained runs
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

The dead-hunter pet gate is proven fixed, and the invalid-final-floor hypothesis
is consumed. The next work unit is the non-monotonic native entrance path:
restore a recovery-only native long-path intent equivalent to the previously
live-proven `MovePoint(..., generatePath=true)` behavior while keeping
`MotionMaster` exclusively in the movement executor. The brain still submits
only a typed move to the corpse-authorized entrance; the executor must preserve
the active native path and use `forceDestination=false`. Do not hardcode an
unproven corridor, require Euclidean distance to the final trigger to decrease,
teleport, or force resurrection. Add focused regression coverage, then run one
clean Magmaw completion-watchdog shard. Do not tune Drudge damage, formation,
taunts, class rotations, pets, or boss scripts.

## Evidence

The nine immutable diagnostic bundles are tracked by adjacent `.dvc` pointers.
The latest report hashes are:

- `198bac19d6`: `4c157675ff37d400c8ae0dba6672b40625c7262373115eedfaa2739057d80e2e`
- `43521ba995`: `ee2f8487b40d4d229e5d06f41b047cb9aea38e0a2637391e234d16b75986ddc2`
- `69b230aae5`: `5214b36af63b8082244bc167786467dedef5e91573ad3e467d79cd5685144f0f`
- `f3768b83d9`: `d928b29fcc08aba19fe2b25fe13b2bb3e769231b248e278ed849b8c3f26b4378`
- `04751b3306`: `e8e5e61996da532ce13ba478895b501ec256f849dcdc07b0b97791aa0add5869`
- `22282882a0`: `1194187be0ba4581b5cbb1da2c5cc9aef9f24f95332598f5a554e8e4daf54b0a`
- `5756bb492f`: `85e88cfff9ca7fada210217ac64760bba7a2a778d69ca3fd0429cc1f7b928db1`
- `ea84aba64a`: `b54847e3be211261a9f49673cbb5cb3a65fa90d9259ebd5305074bcedecfc9ed`

The DVC cache and configured remote were verified in sync after publication.
