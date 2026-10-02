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
contracts are still open. Public nearby-player object and movement translation,
guild services, recipe mutations and the remaining interaction families are pending.

## Continued UI qualification

The saved [workqueue](../../experiments/configs/client_harness/442_interaction_workqueue.json)
keeps the parent interaction objective open between batches. The follow-up trials
use `client_interactions_20261002_followup` in the private evidence directory.

`panel_trial_01` records 22 successful opens, 10 successful closes, 13 incorrect
Laya selections and one guild-window failure. `panel_diagnostic_01` then sends
ordinary installed inputs directly and passes 23 opens and 23 closes. Guild opening
still fails with the default UI on the unguilded account; clubs and Battle.net are
disabled. These diagnostics do not count as model passes or qualify panel contents.

`keybindings_trial_03` passes ten Laya actions through the installed editor:
opening Settings, locating the action, assigning Ctrl-Shift-F12 as a secondary
framerate binding, saving, reloading and toggling the framerate display twice.
Ordinary-input cleanup restores the original Ctrl-R binding and the unused chord.
The first two trials exposed measurement errors: the search-field placeholder
changes after typing, and closing Settings returns to the Game Menu. Those failed
receipts are retained. Conflict handling, character-specific bindings and full
reconnect persistence still need their own cases.

`macro_trial_01` creates and saves TC442Test, physically drags its icon onto an empty
action button, verifies it after reload and clicks it. An attributable native
spell completion confirms Battle Shout (6673). Cleanup deletes the temporary macro
and restores the empty action slot. Editing, character-specific variants and full
reconnect persistence remain open.

Two further repairs preserve the native worldserver. Valid late party health reads
after logout are parsed and ignored instead of disconnecting the realm session.
Native rest state and rested XP now populate Classic RestInfo, including ongoing
updates. `rest_live_01` observes `GetRestState()` returning Normal and no XP-bar Lua
error. Live logout cancellation, completion and re-entry are still queued.

`regression_02.xml` reports 284 passing auth/world tests. `packets_asan_02.xml`
reports 54 passing selected packet tests under ASan/UBSan. The initial rest-test
collection failed because of a relative import; its corrected run passes all six
rest cases. No earlier failed receipt is discarded or counted as a pass.

The follow-up batch is synchronized in
[`442_interactions_20261002_02.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261002_02.tar.gz.dvc).
Its verified raw frames and local archive were removed after the remote checkpoint.

## Ready checks and inventory mutations

The next batch, `client_interactions_20261002_ui02`, keeps the same native worldserver
PID and start time. It runs both owned accounts on HDMI-1. The C++ bridge is the only
server rebuilt and restarted for these repairs.

`profession_trial_01` passes ten Laya actions opening the Alchemy, Tailoring, Cooking
and First Aid recipe catalogs and the archaeology panel. This qualifies the displayed
catalogs and panel opening; recipe selection, crafting and skill changes remain open.
`raid_controls_01` passes assistant toggles, lock/unlock and show/hide, including peer
permissions and restored visible health bars.

`ready_checks_04` qualifies both Ready and Not Ready. The peer sends a real client
response, native confirmations preserve its answer, and completion closes both
dialogs. The duration must be signed 64-bit milliseconds. Captured Whitemane 60895
responses put the optional party-index flag before the answer bit, differing from
the later pinned handler. The bridge completes checks after native-confirmed answers
or its 30-second timer because the legacy backend does not implement completion.
The initial trials retain missing responses, a rejected diagnostic field, and the
negative-answer decoder failure. They are separate from the passing retry.

`group_conversions_02` converts raid to party and back using the actual portrait menu.
Both clients and the native group agree. Conversion clears the native everyone-assistant
flag; ordinary-input cleanup restores it. The runner now preserves its baseline
group type and raid controls even when a trial fails.

`inventory_moves_03` moves the hearthstone from backpack slot 1 to slot 16 and back.
Native and visible item identity/count agree. The earlier drag failed because inventory
requests were unmapped. New translations cover swap, split, auto-equip and auto-store
requests, with native slot validation. Sparse inventory, item, container and equipment
updates replace stale client state; newly created items and removals are tracked.

`stack_split_01` uses Shift-click and the normal split dialog, places one Dwarf Keystone
from a stack of five, then merges it back. Native item creation, stack counts and removal
agree with the UI, and the original five-item stack is restored. Cross-bag, equipment
and crafting trials have separate receipts and acceptance checks.

`cross_bag_01` transfers the hearthstone from the backpack into an equipped bag and
back. Native item identity/count and both visible slots agree throughout, with the
original inventory restored. `ready_timeout_01` starts a check without a peer answer;
the bridge's timer completes it on both sessions and closes both dialogs. It records
zero client response packets, separating timeout from an answered check.

Equipment stats and crafting outcomes remain pending.

The latest full auth/world regression passes 298 tests. The selected ASan/UBSan
packet regression passes 58. The first ready-check test fixtures omitted required
empty metadata and failed two tests; their corrected runs pass. An initial invocation
through the `pytest` executable failed collection because the repository was absent
from its import path; run `pixi run ... python -m pytest` as shown in the runbook.

These receipts remain bounded Laya input selections. They do not qualify all 891
contracts, an entire interaction family, screenshot planning, or long-duration autonomy.
