# Magmaw convergence handoff — 2026-08-22

This is a diagnostic history, not an acceptance claim. All five retained runs
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

Change the Drudge watchdog from formation-contract termination to outcome
tracking: continue while hostile health decreases, fail on a real wipe,
semantic no-progress, repeated decisions, or failed recovery, and require
native recovery before advancing after deaths. Then run one clean Magmaw shard
against the resulting exact build. Do not add another lane/taunt tuning rule
before that run shows the first remaining native edge.

## Evidence

The five immutable diagnostic bundles are tracked by adjacent `.dvc` pointers.
The latest report hashes are:

- `198bac19d6`: `4c157675ff37d400c8ae0dba6672b40625c7262373115eedfaa2739057d80e2e`
- `43521ba995`: `ee2f8487b40d4d229e5d06f41b047cb9aea38e0a2637391e234d16b75986ddc2`
- `69b230aae5`: `5214b36af63b8082244bc167786467dedef5e91573ad3e467d79cd5685144f0f`

The DVC cache and configured remote were verified in sync after publication.
