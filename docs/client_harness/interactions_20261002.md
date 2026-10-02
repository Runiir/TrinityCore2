# Player interaction qualification, October 2, 2026

All changes and live trials use `feature/442-compat` in the isolated 4.4.2 lab.
The native worldserver retained its original PID/start identity throughout these
repairs. Only the standalone C++ packet bridge was rebuilt and restarted.

The versioned checklist contains 891 operation contracts across 45 families. The
installed client supplied 275 binding entries. These are inventories, not passing
coverage counts. A completed episode means the runner closed its batch; examine
each case status before counting a pass.

## Controller and observation

The user explicitly requested Laya for this interaction trial. The retained base,
text-only model at `127.0.0.1:8000` selects from bounded normal keyboard/mouse input
candidates. Each model request/answer, selected input and outcome is retained.
There is no fine tuning, screenshot reasoning or open-ended roaming qualification.
The model reads normal addon-visible state, including visible panels, bags, UI
errors and the active ground-targeting cursor. Screenshots support human review.
Code fixture preparation, diagnostic inputs, cleanup and manual interference remain
separately attributed. This exception does not reinstate Laya for other workflows.

Both accounts have separate characters, prefixes and owned process receipts. Every
input verifies the actor window on HDMI-1 and takes the shared physical-input lock.

## Repairs and qualified cases

| Area | Evidence and qualification | Remaining limits |
| --- | --- | --- |
| Raid health bars | `group_display_02` captures actual frame health bars and complete native member state on both clients. Native partial updates accumulate in a bounded cache. | Characters share map 0 but are in different zones and out of range. Nearby player objects, movement, pets and cross-map variants are unqualified. |
| Compact frame profiles | Modern load/save packets preserve native saved profiles. `raid_controls_01` sees Unlock/Hide captions before their first click, and verifies unlock, lock and hide. | The interrupted Show step does not count as a model pass. The user's shown/locked profile is preserved. Reconnect persistence needs a dedicated replay. |
| Assistants | `raid_controls_01` changes everyone-assistant both ways and confirms the peer's assistant flags. | Individual promotion has packet tests but still needs a live UI case. The user's everyone-assistant setting is preserved. |
| Role poll and assignment | `roles_trial_02/cohort.json` closes successfully. Laya initiates the poll and accepts Tank on Harnessone and Damage on Harnesstwo. Both clients agree on both roles. | Healer, permission rejection and larger rosters need separate cases. |
| World markers | `marker_code_diagnostic_01` confirms an ordinary blue-marker cast and a visible beam on outdoor Northshire ground. `world_markers_trial_02` passes all 18 Laya actions: eight selections, eight placements, individual removal and clear-all. Both clients agree on active and cleared state. Its protocol proof contains five native spell completions, three compatibility annotations and zero rejected casts. | Ground transport coordinates, other maps/phases, placement range boundaries, relog and endpoint restart persistence need qualification. |
| Social | `social_trial_07` verifies friend addition against native saved state, a normal invitation and Laya acceptance by the second account. | Notes, ignore, presence transitions, leave and larger groups remain open. |
| Macros | `macro_trial_03` creates and saves the temporary macro, reloads the UI, verifies it and restores zero temporary macros. | Executing the macro, dragging it to an action bar and full reconnect persistence remain open. |
| Panels and professions | Per-case panel and recipe observations are retained in `panel_trial_02` and `profession_trial_01`. | Those batches include failures. They are not complete qualifications of every panel or profession action. |
| Keybindings | Probes open the installed keybinding panels through normal UI controls. | Assigning, saving, executing and restoring a binding remain open. |

## Why ground markers reported invalid target

The rejection was a compatibility failure, not an instance restriction. The native
marker effect operates on the caster's current map without an instance-only gate.
Outdoor placement has been observed in the installed 60895 client.

The modern ground click contains destination coordinates, an optional orientation,
the map sentinel `-1` and a client send flag. The original translator refused this
target layout. That flag also has a different native meaning: forwarding it made
4.3.4 expect absent spell-weight data. Marker casts now validate and translate the
destination and strip that incompatible flag.

Two subsequent runtime defects prolonged the failure. Completion logging used an
unreviewed field and threw after placement. More critically, missing JSON fields
return numeric zero from the helper; checking `is_null()` incorrectly routed the
native five spells through the path for modern-only markers. The dispatcher now
tests actual field presence. Captured user clicks reproduce that failure, and the
same discriminator has a regression covering all five native marker spells.

Native dynamic-object creation can precede the group marker mask. Position capture
therefore happens before activation. Stale native mask bits without known locations
cannot block other valid markers. Locations are never fabricated. The native five
spells use authoritative native object coordinates. Markers 6–8, spells
171555–171557 observed in the installed client, are group annotations owned by the
C++ endpoint, with normal group permissions and a 100-yard placement range.

## Verification and failures retained

`regression_11.xml` reports **277 passed**. `raid_markers_packets_asan_03.xml`
reports **54 passed** under ASan/UBSan. `raid_markers_tests_09.xml` reports seven
marker regressions passing. The tests exercise captured ground clicks, native
dispatch, permission checks, eight-slot packets, clear commands, pending positions
and the actual completion logger.

Earlier failures remain in the checkpoint. Initial group/member and synthetic
marker fixtures needed correction; the first role selection had an unattributed
manual acceptance; `world_markers_trial_01` stopped when Laya opened the map instead
of clicking ground. That controller failure sent no placement cast. Adding the
normal targeting-cursor observation and a precise input goal produced the later
trial. `marker_dispatch_before_fix` fails against the buggy binary and the captured
reproduction records its array exception. `raid_markers_tests_08` initially expected
an omitted codec reply rather than its explicit null reply; the fixture expectation
was corrected. `regression_09` used a nonexistent test directory and ran no tests.
None of these receipts is counted as a passing result.

## Repeating a trial

Start the missing owned services in the runbook order and launch both actors on
HDMI-1. Enter both characters normally and retain the two-member raid with the
scout's assistant permission. Inspect the acting client's current camera and choose
a visible nearby ground point. Never reuse a point from a different camera view.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_world_markers --output /home/runiir/.local/share/trinity-client442-lab/evidence/new_marker_trial --actor scout --ground 800 450
```

The runner uses normal `/wm 1` through `/wm 8`, mouse clicks, `/cwm 6` and
`/cwm all`. It observes both actors without sending protected addon gameplay
commands. The setup clear is explicitly code fixture cleanup. Stop the run if
ownership, the expected UI or infrastructure is lost.

## Evidence checkpoint

The closed receipts, raw frames, pinned protocol/UI sources, safe packet journals,
test results, build receipts and Release binaries are archived with DVCLive in
[`442_interactions_20261002_01.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc).
The archive excludes credentials, authentication bodies, account caches, database
dumps, Wine prefixes and CASC caches. The checkpoint tool verifies every archived
file hash, runs scoped `dvc status` and `dvc push`, and requires empty cloud status
before permitting removal of raw data.

```bash
pixi run dvc pull artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc
```

Full client compatibility, indefinite bot operation and the remaining inventory
contracts are still open. The next group repair is public nearby-player object and
movement translation; the next interaction cases are binding assignment, macro
execution, complete panel/recipe trials and group leave/raid conversion.
