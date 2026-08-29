# Magmaw Canary113 native-recovery architecture stop

## Decision

Do not launch another Magmaw canary until the retained native-recovery fixture
passes on the exact source tree and the worldserver build contains the repaired
movement executor. This is a lifetime recurrence, not a new one-run blocker.

The sole causal family is `native_partial_death_recovery_lifecycle_failure`.
`native_bwd_ghost_runback_no_progress` is a diagnostic stage inside that
family, not a new counter. A fix is not closed by an accepted movement
submission, one successful member, one successful run, or a renamed terminal.
Closure requires the deterministic fixture plus two consecutive full
current-standard route clears with the family absent.

## Why the prior workflow regressed

The regression bank retained the partial-wipe reset gate but did not migrate
the downstream cross-map ghost-runback history. Existing tests checked source
shape, ownership, eligibility, one-repath bounds, and no-cheat constraints.
They did not prove that Trinity's chosen movement generator remained active,
changed the dead player's position, crossed area trigger 6581, reclaimed the
corpse, rejoined the roster, and released route generation 4.

Canary97 and Canary98 used the same source commit and binary. Canary97 completed
one Affliction runback; Canary98 stalled at the graveyard. That single success
was nondeterministic escape evidence, not closure.

## Ten retained failures in the family

| Observation | Broken lifecycle stage |
| --- | --- |
| `f3768b83d9` | Two dead tanks could not start ordinary recovery after the Drudge reset. |
| `04751b3306` | Recovery began, then terminalized as `native_runback_no_progress`. |
| `5756bb492f` | Three ghosts remained at the native graveyard while movement was reported retryable. |
| `ea84aba64a` | Initial movement occurred, then a non-monotonic corridor edge was rejected. |
| `d98451124d` | Ghosts moved to local endpoints, stalled, and never reached trigger/rejoin. |
| `a09d5a83c4` | The intended single repath was not exercised before terminalization. |
| `cedeb5c933` | One repath was submitted, then invalid-Z/native-long-path state stalled. |
| `a4cde51ec1/run1` | The same path was restarted repeatedly; a ghost moved about seven yards in 123 seconds. |
| `31322fb541/canary98` | A retained native long path stopped at `(-7482.93,-1383.73,416.785)`. |
| `4ba74f777b/canary113` | Two DPS ghosts retained accepted paths while stationary at the graveyard; one repath then terminalized. |

The detailed older receipts and hashes are retained in
`cata_raid_magmaw_convergence_handoff.md`, the Canary98 handoff, and the
recurrence ledger.

## Canary113 evidence

- Exact source: `4ba74f777b5db2f82c1f9d9201d310df21dd0637`
- Exact binary SHA-256:
  `197617f053fad03eb22e78eacf23c98356abd102730f1542d046a8d0b01e50aa`
- Route result: Chainwielder and both Drudges dead; generation 3 remained
  active; Magmaw was not reached.
- Survivors/deaths: eight alive, two dead DPS.
- Both ghosts: map 0, instance 0,
  `(-7433.60,-1384.00,418.784)`.
- Requested entrance: `(-7542.91,-1184.93,482.0)`, area trigger 6581.
- Final native motion: current type 0, active slot type 19, no position delta.
- Recovery sequence: release, movement submitted, retained in-progress,
  exactly one repath, then `native_runback_no_progress`.
- Report SHA-256:
  `893848b1b69866118ae7c74b87d9840446586b823e4aa1cbf0fd000b711aa56d`
- Raw JSONL SHA-256:
  `ffe7af461b19cdfcb2246bcae7e4a0655fa9f9b1586bac30ce697309800e84e3`
- Worldserver log SHA-256:
  `85f63cd3293521380514e639b5d0fdf681b453e1dcb7fc19416a8da1bbfe1702`

The forced terminal trace had a delta gap. The diagnosis and complete combat
log still prove the gameplay failure; the delta gap is a secondary evidence
defect and must not replace the causal classification.

## Bounded repair contract

The recovery brain continues to select a typed Recovery-owned move. The shared
movement executor must:

1. enable flight and disable gravity only for the exact authorized outdoor
   Burning Steppes ghost episode;
2. submit a persistent native point generator without ground-navmesh pathing;
3. reject the submission immediately if the native point generator or spline
   is inactive, instead of recording false progress;
4. retain a running generator without resubmitting it every decision tick;
5. require measurable position progress, then ordinary area-trigger worldport,
   corpse reclaim, full-roster rejoin, and route generation 4;
6. keep the one-repath and typed terminal bounds.

No teleport, forced resurrection, synthetic route progress, movement-speed
tuning, new hard-coded recovery waypoint, Drudge tuning, or watchdog extension
is authorized.

The diagnosis must expose the episode, exact current map/position, flight and
gravity flags, native current/active motion types, spline-finalized state,
requested destination, and planner/executor outcome. A later agent should not
need to infer execution from a generic `native_movement_submitted` label.
