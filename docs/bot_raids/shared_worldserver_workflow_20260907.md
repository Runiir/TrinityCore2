# Shared-worldserver workflow implementation

The user selected simultaneous individual boss tests in separate native raid
instances on one worldserver, followed by complete 10H and 25H raid runs.
This supersedes the earlier choice to work exclusively on asset reconstruction;
asset attribution remains a prerequisite for accepting a live run.

## Proven blockers at bc1023b03f0ede5bb3710819566aaacef1399531

- `MaxActiveCohorts = 1` rejects the second cohort start. `Update()` only
  schedules `_runningCohortId`, so increasing the cap alone is insufficient.
- Native combat callbacks read a process-wide selected cohort. Map updates
  run on a separate worker, which cannot inherit the world thread's scope.
- Cohort stop and trace reset call the global movement diagnostics `ClearAll()`.
- The current ownership probe assigns fabricated instance IDs. Its successful
  storage checks do not prove isolation of live instances or native callbacks.
- `IsValidationProfileName` requires ten-player normal Blackwing Descent.
  Heroic, 25-player, and other-raid profile admission need a separate repair.
- `CohortCommandExecutor.run` previously allowed commands outside its addressed
  verb set, including server shutdown and unknown global verbs.

## Implementation order

1. Restrict the worker command transport and clear only owned movement state.
2. Schedule both active cohorts; bind native callbacks through owner leases and
   native map/instance identity. Restore callback and update scope on exit.
   Initially admit at most two cohorts with at most one map worker. Multiple
   map workers remain unsupported while diagnostic stores lack synchronization.
3. Independently review the native change, compile, then run the real two-cohort
   isolation fixture. Both must advance; native events must reach the correct
   logs; stopping one must preserve the witness's leases, instance, and progress.
4. Generalize profile admission for declared raid size, difficulty, and map.
5. Use Magmaw to test the bounded repair workflow. Route missing scripts to
   native encounter implementation; route matched-cadence damage defects to
   native class mechanics and matched-damage cadence defects to role policy.

`tools/raid_program/shared_instance_observation.py` reads addressed native status
and diagnosis. It compares exact rosters and *current* member instance IDs,
rather than trusting retained admission snapshots alone. Its unit tests verify
the reader and rejection rules; they do not certify live isolation or completion.

One coordinator owns the shared binary, configuration, console, build, and
server lifecycle. Boss workers receive addressed cohort access. Preserve the
existing completion watchdog, typed termination, evidence attribution, and
ten-occurrence causal stop. A compile, storage probe, or diagnostic admission
never counts as a boss clear. No ML dataset admission follows from synthetic
fixtures.

## Verification state

The native kernel, scoped cleanup, command guard, and observation reader are
implemented and independently approved by Sol high. Focused native fixtures and
syntax checks pass; a complete server link and live isolation validation remain
outstanding. Independent review found
and drove corrections for unresolved player ownership, released versus foreign
lease cleanup, inactive shutdown cleanup, and native legacy command fallback.
The command executor now verifies cohort registration before addressed dispatch.

Calibration identity binds the actual native capacity. Serial attempts verify
that no foreign cohort is active and retain that verification in their report;
capacity-two aggregate evidence requires this proof. Historical capacity-one
evidence remains readable. These checks depend on the shared lifecycle owner
preventing out-of-band mutation between registry snapshots.

Validation included 20 native-focused tests and translation-unit syntax checks,
73 integration tests, and 29 Phase 9 qualification fixtures. Independent review
ran 56 capacity/exclusivity tests. These are offline checks.

The existing runtime asset attribution prerequisite remains unresolved. No live
attempt, boss clear, accepted repair, or training-data admission is claimed by
this implementation checkpoint. Unit-test payloads are synthetic counterexamples,
not raid evidence. DVC status still reports the pre-existing 576 changed/missing
stages; this work has produced no new experiment payload to publish.

The current read-only prebuild check used the repository as source checkout and
DVC workspace, `trinity-worldserver-test.conf`, `data` as DataDir, and map 669.
It reported one inventory hash mismatch, 16 mode mismatches, and one missing
provenance issue. Snapshot hash:
`b6bc5ac7429957736b9a3a9e90ff58785c39bb53f9a3df004b2d209aa2aacdd7`.
This was an input audit, not an admitted run. Resolve exact inventory/mode
differences and produce real extraction provenance before a live attempt.
