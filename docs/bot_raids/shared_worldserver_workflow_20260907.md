# Shared-worldserver workflow status

The shared-cohort native kernel is implemented and independently approved.
Runtime input reconstruction, full worldserver build, and remote publication
have passed. Two live isolation canaries closed on recovery-observation
rejections. Isolation remains unproven; no further unchanged run is admitted.
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
review ran 56 checks and approved the change. The full link passed at
`d82a1f88de`; the reviewed Python protocol repair at `06996cc142` passed an
incremental build and receipt verification before and after the live run.

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

The concrete pair is frozen in
`experiments/configs/cata_shared_instance_fixture_v1.json`: Magmaw cohort
`bwd_magmaw_diagnostic_10n` (GUIDs 30001–30010) and Omnotron witness
`bwd_omnotron_diagnostic_10n` (GUIDs 30101–30110), both map 669, difficulty 0.
The fixture proves isolation only. It cannot certify either boss, predecessor
state, heroic progression, or training-data admission.

The shared driver must prove advancing native outgoing outcomes and decisions
in both instances while both are active, stop Magmaw, collect a fresh witness
baseline after that stop, and then prove further witness outcomes with the same
identity and retained movement evidence. It stops both addressed cohorts and
verifies cleanup. Its successful observation ends as typed `interruption`, not
an encounter clear.

The coordinator entry point is `tools.raid_program.run_shared_instance_canary`.
Run it from the frozen checkout with `--source`, the Git common `--repository`,
the verified `--build-receipt`, and a new external `--output` directory. It
derives the authenticated shared base config, verifies source/build/assets,
provisions and reads back the exact pair under the lifecycle lock, starts an
attached server, binds the responding native PID, drives the fixture, and closes
the owned server. No SOAP credential or single-boss Chainwielder overlay is used.

Preparation found and repaired another cross-cohort defect: provisioning a
subset still deleted the entire validation item GUID range. Item cleanup now
joins through selected character ownership, and allocation retains offsets from
the full frozen layout. The regression compares selected item IDs with the full
layout and exercises preservation of excluded inventory and item-instance rows.
An older test explicitly required the destructive global-range deletion; that
assertion now requires owned cleanup.

Combat exports now carry the generic epoch/attempt/profile identity already
present in status and trace. Diagnostic polling no longer overwrites last real
decision history for detached bots. Independent Sol static review approved
these native changes. Compilation and linking passed; the first live outcome
is recorded below and does not accept isolation.

The final independent Sol review approved the repaired driver and launch
helpers. The combined shared-instance, provisioning/readback and transport
suite passed 108 tests; the focused existing provisioning suite passed 36.
These include real-process executable replacement and SQL cleanup regressions,
but the two-cohort protocol fixtures are synthetic and do not certify live
isolation. A read-only database preflight found all 385 planned item IDs owned
by the selected cohort names, with no foreign or orphan collision.

The driver rejects reused cohort identities and ambiguous create ownership,
uses independent unfulfilled-cohort progress budgets, reconciles every visible
new combat suffix with outgoing aggregates, and anchors actual witness movement
receipts across the stop. The narrow combat reducer was implemented by a
Luna max worker and included in independent Sol review.

One coordinator owns
the shared binary, configuration, provisioning, console and server lifecycle.
Workers receive addressed cohort access only. Individual interruption must stop
that cohort and preserve the shared server and every other active instance.

The frozen checkout is
`/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/source`,
Git-clean at `06996cc142`. It retains the verified independent runtime inputs
and the built binary. The live launcher used its derived shared config and
successful build receipt, provisioned only the selected pair, and passed both
fresh database readbacks.

## First real canary

The run at `06996cc142` admitted both cohorts on one server epoch. Its first
complete observations showed Magmaw in native instance 13 and Omnotron in
instance 2, with disjoint group IDs and ten leases each. The baseline measured
Magmaw DPS/HPS 0/0 and witness DPS/HPS 0/11323. These are brief startup
measurements, not class calibration or encounter performance results.

Later witness status reported two deaths and diagnosis reported six alive
members. The driver stopped at `native_instance_identity_invalid`, with typed
termination `contamination`. Independent replay traced the rejection to status sequence 43: difficulty
readback became incomplete while ghosts were outside the raid during native
corpse recovery. Diagnosis sequence 44 retained exact frozen instance and
attempt-bound recovery for those ghosts. Native ownership allowed this state;
the Python validator did not. No cross-cohort ownership leak was observed.
The next repair recognizes only that exact native recovery state and preserves
the chained diagnostic reason. The failed run remains unchanged.
Both addressed cohorts were stopped, all leases were released, and the owned
worldserver exited with code 0. No witness-after-subject-stop proof was reached.

Before launch, a real protocol mismatch was repaired: successful native start
returns `botauto_status`, while the transport and its fake test expected
`botauto_start`. Native combat-log rejections also need prompt recognition
rather than waiting for chunk completion. Focused real-child transport tests
now cover these variants, including incomplete chunks. Independent Sol review
approved the repair; the shard skill now requires native handler-derived reply
fixtures. No native gameplay change was needed for this correction.

The closed run, raw console/command responses, exact config, provisioning SQL,
readbacks, and both build receipts were archived to
`artifacts/cata_raid_program/shared_instance_06996cc142_20260907.tar.gz.dvc`.
A fresh empty-cache remote download matched archive SHA-256
`cd7264c204d2305172879144231a32e6f8a094c66bc53a9360a9bd086053a35e`.
Targeted local and remote DVC status passed. The retained publication receipt
records the round trip. The run is closed and training-ineligible.

Then repair generic profile admission: `IsValidationProfileName` currently
accepts only ten-player normal Blackwing Descent. Heroic, 25-player and other
raid maps remain separate work. Route absent boss scripts to native encounter
implementation. Route matched-cadence damage defects to native class mechanics
and matched-damage cadence defects to role policy. Do not remain on Magmaw after
its current edge is accepted or replaced by a different proven blocker.

## Revised canary and next bounded repair

Commit `3490069d1c` recognizes native-authorized in-world ghost runback with
exact corpse, frozen-instance and recovery-attempt evidence. Its exact replay
and ownership negatives passed with the other focused checks (65 total), and
independent Sol review approved the change. Error reports now retain the
chained cause and precise pre-cleanup raw command sequence (`565a7f5a65`).

The revised run again admitted both instances, then stopped at raw sequence 44.
GUIDs 30102 and 30104 were temporarily `in_world=false` during
`released_ghost_observed`, while native `matches_cohort=true`, corpse presence,
locked map669/instance2 and attempt1 remained intact. The native ownership
predicate explicitly supports released ghosts through their corpses before its
ordinary in-world check. The Python observation still required in-world on
every poll, so it rejected this earlier transfer boundary. This is the second
recovery-observation failure, not evidence of foreign ownership or a boss clear.
Both cohorts released all leases and the worldserver exited normally.

The next work unit must cover release, worldport, runback, return and stable
in-instance observation together. It must distinguish a legitimate transient
observation from accepted progress and from a foreign identity; no dead or
absent member may fabricate the witness-continuation proof. Replay both closed
runs and all foreign/stale-ownership negatives before any further live attempt.
Do not repair these transitions by repeatedly launching Magmaw. The broad
recovery-observation recurrence count is two; changing sub-error labels must
not reset it.

The revised evidence is published at
`artifacts/cata_raid_program/shared_instance_3490069d1c_20260907.tar.gz.dvc`,
archive SHA-256 `b40acec9cceec76256e9e733a50660c41b807a654681cff62871a6cc88851a26`.
An empty-cache remote download matched; local/cloud status passed before exact
archive-copy eviction. Raw command/console data remains remote reconstructible.
Both runs remain training-ineligible. Class balance and boss fidelity cannot
be assessed from these short isolation failures.

## Recovery sequence revision

The validator now accepts temporary absence only during the three native
release/entrance transfer phases, with the same exact corpse, attempt, group,
roster and frozen-instance authority. In-instance ghosts remain attributable
through reclaim; a complete later difficulty diagnosis can supersede an earlier
incomplete status sample. Transfer GUIDs are retained in heartbeat evidence and
neither boundary of such a sample may certify outgoing progress. Both original
closed native failures are retained as exact field projections, with additional
release/runback/re-entry/reclaim sequence and foreign/stale negatives.

The focused suite passed 76 checks and independent Sol review approved this
revision. The next action is one incremental build and bounded isolation canary,
then the user's requested Magmaw completion attempt under the completion
watchdog. No boss clear or full isolation claim exists yet.
