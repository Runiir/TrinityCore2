# Magmaw convergence handoff — 2026-08-22

This is a diagnostic history, not an acceptance claim. All seven retained runs
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

The outcome-based trash gate and ordinary partial-death recovery are active.
The next work unit is one trace-backed repair of the native corpse-run/rejoin
edge exposed by `04751b3306`: determine why a dead bot outside map 669 makes no
progress after six attempts while living members remain inside, then repair
that policy-to-native-movement edge and run one clean Magmaw shard. Do not add
another lane, taunt, or DPS rule; this evidence does not implicate Drudge
throughput or formation.

## Evidence

The seven immutable diagnostic bundles are tracked by adjacent `.dvc` pointers.
The latest report hashes are:

- `198bac19d6`: `4c157675ff37d400c8ae0dba6672b40625c7262373115eedfaa2739057d80e2e`
- `43521ba995`: `ee2f8487b40d4d229e5d06f41b047cb9aea38e0a2637391e234d16b75986ddc2`
- `69b230aae5`: `5214b36af63b8082244bc167786467dedef5e91573ad3e467d79cd5685144f0f`
- `f3768b83d9`: `d928b29fcc08aba19fe2b25fe13b2bb3e769231b248e278ed849b8c3f26b4378`
- `04751b3306`: `e8e5e61996da532ce13ba478895b501ec256f849dcdc07b0b97791aa0add5869`

The DVC cache and configured remote were verified in sync after publication.
