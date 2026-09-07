# Shared-worldserver workflow status

The shared-cohort native kernel is implemented and independently approved.
Runtime input reconstruction and remote publication have now passed. A full
worldserver build and real two-instance isolation validation remain outstanding.
No boss clear, accepted gameplay repair, or ML-data admission is claimed.

## Native implementation

Checkpoint `7daa4e0cbd` implements two active cohorts with at most one map worker,
per-cohort update scopes, lease/attempt/map/instance callback ownership, and
cohort-scoped cleanup. Ambiguous, stale, and foreign ownership fail closed.
Inactive shutdown cleanup also respects current lease ownership. Start-wrapper
scope restoration and denial paths preserve the selected cohort and profile.

The worker command executor permits only addressed known verbs, verifies native
registration before dispatch, and guards exclusive serial calibration against
foreign active cohorts. Calibration identity binds the actual native capacity.
Capacity-two serial evidence requires recorded exclusivity checks. Synthetic
ownership probes remain explicitly non-live evidence.

`shared_instance_observation.py` checks exact native rosters and current member
instance IDs. Sequential observations alone do not prove simultaneous execution
or callback/stop isolation. The live validation must observe both cohorts
advancing, correctly attributed native events, and continued witness progress
after the other cohort stops.

Native validation included 20 focused fixtures, translation-unit syntax checks,
73 integration checks and 29 Phase 9 checks. Independent capacity/exclusivity
review ran 56 checks and approved the change. A full link has not run.

## Runtime inputs: verified and published

The immutable historical inventory and extraction-negative fixture are unchanged.
The current input manifest now explicitly uses verified materialization, with
historical extraction origin recorded as unknown. No historical extractor
receipt was invented and no client-data extraction was needed.

The entire native DataDir matched all 40,976 pinned entries. The archive was
published, downloaded through a separate empty DVC cache, extracted on persistent
ext4 storage, and verified against the portable inventory. Only directory
allocation size is excluded from comparison; paths, types, modes, and every
file's size and SHA-256 remain exact. Physical source inventory is retained.

- Archive pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.tar.dvc`
- Archive SHA-256: `75ee7707bfca455868fb62f74be3c4a6667b4f2142f9161cd1caa224a18e10f1`
- Archive DVC MD5: `b1020765779cbccba103b8873dfb8c2e`
- Archive size: 5,256,591,360 bytes
- Materialization pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.materialization.json.dvc`
- Receipt SHA-256: `d1a1bfd6cc62bc0f54ab77104c0e6071cc7dddc8907f8033b675e47eef8fdaaf`
- Verification pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.verification.json.dvc`
- Verification SHA-256: `593821756506251785a2599c5c7e7f6463b3f3b1850e7a3ebcda129afb70dcbd`
- Promoted input manifest SHA-256: `ece9fd1784638946bfc324832dc857560a0633c4f27eb82fb4f66515394892a7`
- Passing input snapshot: `c5f8b77f264d0d3235670ea5bf23a46b27a0b20f96361c4375d9b5508ef02ead`
- Portable inventory: 40,968 files, eight directories, 5,224,209,638 file bytes
- Portable inventory SHA-256: `e6cd916f71b2a9bfb63694dbca78dcf3a5e510f9b00d9489552ef72b87440597`

Both metadata payloads were separately fetched through another empty DVC cache
and matched their SHA-256 hashes. Targeted local and cloud DVC status were in
sync before eviction. The verified reconstruction tree, workspace archive, and
exact archive cache object were removed, recovering roughly 25 GB. Native
DataDir, the small metadata, and required independent source inputs remain.
A missing local archive after this cleanup is deliberate; restore it through its
DVC pointer when needed. No broad DVC garbage collection was performed.

Code checkpoints are `03cb01db0b` (materialization), `d7e0900671` (explicit
archive resume), `831af130aa` (archive publication checkpoint), and `d3d8b87c5e`
(portable directory comparison). Root's final focused suite passed 85 checks;
independent final review passed 97 read-only checks. Real remote reconstruction,
not these fixtures alone, established the production input proof.

## Causes of the input loop that were repaired

1. Source and native roots aliased the same eight MMAP files while requiring
   modes `0444` and `0664`. Their bytes matched throughout. Changing modes only
   transferred failures between consumers. The new preflight reports the root
   contradiction before reading assets; independent copies satisfy both.
2. A missing historical extraction receipt was treated as essential even though
   its producer only records caller-provided extraction metadata. Verified
   materialization now proves current reproducibility without inventing history.
3. `/dataset/*` hid newly generated `.dvc` pointers. Narrow pointer exceptions
   and explicit verified archive resume avoid repeating a completed capture.
4. Reconstruction in `/tmp` hit its tmpfs quota. Exact failed copies were
   cleaned; multi-GB reconstruction now uses persistent storage.
5. Directory `stat.st_size` made reconstruction dependent on filesystem layout.
   The portable comparison excludes only that allocation detail.

The first two publication failures were local pointer visibility and extraction
quota failures. Neither was a live bot attempt. Historical failing snapshot
`b6bc5ac7429957736b9a3a9e90ff58785c39bb53f9a3df004b2d209aa2aacdd7`
is superseded by the passing current input proof, not rewritten as success.

## Next bounded work

Prepare the exact two-cohort live fixture before building. One coordinator owns
the shared binary, configuration, provisioning, console and server lifecycle.
Workers receive addressed cohort access only. Individual interruption must stop
that cohort and preserve the shared server and every other active instance.

The preparation checkout is
`/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/source`.
It currently holds 27 independent verified input copies totaling 46,561,614 bytes
and is Git-clean at `03cb01db0b`. It has not been built or sealed for a live run.
Advance this unused checkout to the final reviewed preparation commit, recheck
its inputs, then freeze its commit/tree before the attributable build and run.
The input audit used the coordinator's `trinity-worldserver-test.conf`; that
ignored config is not present in the detached checkout. Bind a concrete runtime
configuration through the existing config-authority workflow before launch.

After the concrete fixture passes offline checks and review, build once and run
one bounded Magmaw plus disjoint-witness isolation test with one map worker.
Require typed termination, DPS/HPS, decisions, movement, deaths, route progress,
callback attribution and witness preservation. Publish and clean the evidence.
A storage fixture, command smoke test, or emergency timeout is not a clear.

Then repair generic profile admission: `IsValidationProfileName` currently
accepts only ten-player normal Blackwing Descent. Heroic, 25-player and other
raid maps remain separate work. Route absent boss scripts to native encounter
implementation. Route matched-cadence damage defects to native class mechanics
and matched-damage cadence defects to role policy. Do not remain on Magmaw after
its current edge is accepted or replaced by a different proven blocker.
