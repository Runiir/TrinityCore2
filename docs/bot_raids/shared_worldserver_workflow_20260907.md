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
This was an input audit, not an admitted run.

Further inspection identified the cause: source checkout `data/mmaps` and native
DataDir `mmaps` resolve to the same eight files, while the offline contract
requires mode `0444` and the native contract requires `0664`. Every file matches
its pinned content hash. Changing permissions simply transfers the failures to
the other consumer. The files have been restored to their original `0664` mode.
Use independent copies in the immutable source checkout; do not hard-link them
to native runtime inputs. `runtime_asset_root_aliases.py` detects contradictory
requirements for the same absolute path before expensive inventory checks.

The historical extraction receipt is absent. The existing receipt producer
inventories files and records caller-supplied extraction metadata; it cannot
attest how existing files were originally extracted. Do not manufacture that
history. Current input provenance must instead bind an exact materialization,
its DVC content address, and a verified reconstruction from the remote using an
empty cache. Record historical extraction origin as unknown. Historical
manifests and their missing-receipt negative fixture remain unchanged.

`tools/raid_program/runtime_asset_materialization.py` implements that publication
and reconstruction path. The current input manifest can explicitly select it;
the verifier still checks all asset classes, the exhaustive native inventory,
and the current DVC pointer. The producer rejects changed inputs and malformed
archives and hashes the complete archive without loading it into memory.

Offline validation passed 70 materialization/closure/root-conflict checks and
56 parent-caller/launcher checks. The tests include actual DVC publication and
empty-cache reconstruction against a temporary filesystem remote using two
synthetic files. This does not certify the production input set. The integrated
production preflight now identifies all eight root conflicts before reading any
asset payloads, with an empty snapshot in approximately 0.3 seconds.
A separate full DataDir comparison found zero differences across all 40,976
entries against the pinned exhaustive inventory. Fresh extraction or inventory
replacement is unnecessary. Six additional root-detector tests cover malformed
manifest records and require a typed validation failure instead of a traceback.

Independent Sol high review approved the materialization implementation for
production publication. Review ran 88 relevant checks and 24 final focused
checks. Production publication and reconstruction remain unexecuted at this
code checkpoint.

The first production materialization captured its archive but stopped before
upload: the repository's `/dataset/*` ignore rule hid the `.dvc` pointer.
Narrow pointer exceptions and an explicit existing-archive resume path repair
this publication edge. Resume retains the full remote reconstruction and source
drift checks. Its focused suite passes 79 checks.

A detached clean source checkout at `03cb01db0b` now holds 27 independent input
copies (46,561,614 bytes), each verified against the manifest. Preflight using
this checkout and the configured native DataDir has no hash or mode failures;
only the still-unbound provenance receipt remains. Input snapshot:
`c5f8b77f264d0d3235670ea5bf23a46b27a0b20f96361c4375d9b5508ef02ead`.

Independent Sol high review approved the bounded archive-resume and pointer
visibility repair; its read-only verification passed 91 checks.

The resumed publication uploaded the exact archive and verified its downloaded
SHA-256, MD5, and size through an empty cache. Extraction then failed with
`EDQUOT` because `/tmp` is a 16 GiB tmpfs with a per-user quota. The exact failed
temporary reconstruction was removed; production DataDir and archive remain.
Future reconstruction uses the persistent filesystem under the validation root.
Both targeted local and cloud DVC status report the archive in sync. Its pointer
is `dataset/runtime_assets/native_inputs_03cb01db0b.tar.dvc`, MD5
`b1020765779cbccba103b8873dfb8c2e`, size 5,256,591,360 bytes.

A second verifier defect needs correction before another reconstruction:
directory `stat.st_size` describes filesystem allocation rather than asset
contents. Portable reconstruction must preserve exact paths, types, modes and
all file bytes/sizes/hashes while excluding directory allocation size from the
comparison. Historical inventory authorities remain unchanged. No production
materialization receipt or accepted live-input closure exists yet.
