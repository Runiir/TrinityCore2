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

## Equipment, chat and lifecycle continuation

The `client_interactions_20261002_ui03` batch continues the parent workqueue.
`equipment_01` proved ordinary unequip/reequip and native item identity, but exposed
zero damage and stale strength/armor in the client. The C++ bridge now translates
the native initial stat arrays and sparse owner stat/damage updates, including
zero values and signed modifiers. `equipment_02` passes the Laya helmet removal
and replacement and independently compares the visible and native strength,
armor, damage range and maximum health before, during and after the change.
The original equipment and inventory are restored. Crit, hit, mastery and the
remaining character statistics still need live qualification.

`chat_01` exposed an incorrect world-channel-only guard. Ordinary chat arrives on
the authenticated realm connection, which must still have an active owned player
and instance connection. `chat_02` then passed five sends but disconnected on
whisper. The actual Whitemane 60895 whisper request uses a nine-bit target-name
length and local realm ID 1; the pinned upstream packet reference used seven bits.
The adapter now decodes the installed client's captured request. `chat_03` passes
six Laya sends (say, yell, emote, raid, raid warning and whisper) and three peer
delivery checks against native packets and normal `CHAT_MSG` addon events. Only
bounded synthetic probe messages are admitted to packet diagnostics; arbitrary
player chat and GM fixture command text are excluded.

Reconnect attempts with old launcher credentials exposed a separate ten-minute
ticket expiration problem. New cached credentials last 24 hours, and REST refresh
extends a still-valid ticket. Expired, revoked and disallowed-account credentials
are not renewed. `ticket_refresh_live.json` verifies renewal and expired-ticket
rejection through the running REST service using a disposable owned credential,
then deletes it. This is a code fixture check, not a model/UI reconnect pass.

`crafting_03` prepared matching native/UI reagent counts but stopped when Laya
selected Tab instead of typing the recipe search. It attempted no craft and
restored zero reagent/product counts and the temporary permission. The clarified
search goal passes in `crafting_04`: recipe search and selection, one craft, then
a two-craft batch. Native spell completions and native/UI reagent and product
counts agree. Cleanup restores the original zero counts and temporary permission.
Craft cancellation, filters, recipe learning and skill gains remain open.
Earlier `crafting_01` used an unsuitable general
`IsSpellKnown` recipe oracle; learned recipes now come from the native spell
catalog and normal visible recipe links. `crafting_02` stopped because its chat
fixture commands were not translated. Neither counts as a successful craft.

The logout trials retain their failures. `lifecycle_01` used the wrong installed
button caption. `lifecycle_02` cancelled correctly but final character-cache writes
after native logout disconnected the realm. The bridge now retains the last owned
cache identity while refusing gameplay and unrelated character cache requests.
`lifecycle_03` used an invalid measurement of omitted native zero fields; the
fixture now interprets omitted flags as zero only after a full player create.
`lifecycle_04` completes logout and shows the member offline on the peer, but fails
reentry. Legacy aura and bind packets reached the new instance before its world
entry packet. A bounded initialization queue now sends world entry first, and
logout clears previous world, item, aura, cast and movement state. `lifecycle_05`
still fails before world entry: the prior instance socket was never closed.
The pinned native modern session explicitly retires that socket on logout. The
adapter now closes it after detaching it from the realm. `lifecycle_06` passes
ordinary logout cancellation, completed logout and Laya reentry. The peer observes
offline then online membership, and equipment, group and raid profile match the
pre-logout baseline. Character-selection avatar rendering has separate retained
frames. Persistent character-specific keybindings and macros still need trials.

`guild_open_01` is an invalid membership fixture. The installed Classic guild
window intentionally does nothing for an unguilded player. Native membership is
also absent. Guild membership, roster packets and normal guild mutations require
a separate disposable owned guild trial.

The native worldserver retained its original process identity. These repairs
rebuilt only the C++ adapter and restarted the owned login/packet adapters.
`login_barrier_regression.xml` passes all 340 authentication/world tests. The final
`logout_socket_asan.xml` passes nine selected lifecycle/cache tests under ASan/UBSan.
The first sanitizer invocation named a nonexistent test file and collected no
tests; its log is retained separately from the corrected passing run.
`whisper_regression.xml` reports 327 passes, `whisper_asan.xml` reports 25 selected
ASan/UBSan passes, and `ticket_refresh.xml` reports 17 authentication passes after
the renewal change. The failed pre-fix whisper replay is retained. Two earlier
test invocations failed during collection because of the wrong runner import
path and codec filename; they ran no qualifying tests. The initial stats fixture
failure was corrected to match the existing server object-update flag.

Additional repeatable runners cover crafting, logout cancellation/completion and
reentry, and the installed Classic guild UI preference. Their existence does not
qualify their pending live cases. The workqueue remains open beyond this batch.

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

This closed batch is synchronized in
[`442_interactions_20261002_03.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc).

The latest full auth/world regression passes 298 tests. The selected ASan/UBSan
packet regression passes 58. The first ready-check test fixtures omitted required
empty metadata and failed two tests; their corrected runs pass. An initial invocation
through the `pytest` executable failed collection because the repository was absent
from its import path; run `pixi run ... python -m pytest` as shown in the runbook.

These receipts remain bounded Laya input selections. They do not qualify all 891
contracts, an entire interaction family, screenshot planning, or long-duration autonomy.

## Guild membership and disk retention

`client_interactions_20261002_ui04` uses a disposable native guild, `Harness Ui Test`,
and the same isolated native worldserver. No existing guild membership was present
on either owned account before preparation. The initial guild trial exposed missing
native guild GUID translation; the first reconnect fixture also exposed an incorrect
legacy GUID high-part assumption and a warming friend-cache observer error. Corrected
reconnects preserve the native guild identity and tolerate an unavailable friend count.

`guild_open_02` opens the window but fails its roster oracle with blank member rows.
The rank and permission queries are missing from that trace. After their translation,
`guild_open_03` displays the native name, level and rank. Its Classic guild permission
Lua error remains recorded; it is not a clean guild-control qualification.

The shipped Classic guild XML contains six permission tabs while its script loops
over Cataclysm's eight. `Client442Compatibility` supplies the missing two stock-template
widgets for build 60895. It is separate from the read-only observation addon and does
not send gameplay commands. `lab_runtime prepare-client` installs it in the private
client. Restart the game when first installing a new addon; subsequent file updates
can use ordinary `/reload`. **This version 1 repair was later removed because it
taints protected guild controls; see the live rank qualification below.** A corrected build guard handles Lua's multiple return
values. `guild_tabs_reload_fixture` verifies the active eight-tab repair and no Lua
errors on both clients. Receipts record the compatibility addon's file hash.

`guild_membership_01` is a controller failure: Laya opens Friends for the invitation
goal. Clearer input descriptions and normal addon-visible guild state produce
`guild_membership_02`, which passes invitation, decline, reinvitation, acceptance,
both two-member rosters, message-of-the-day mutation and peer delivery, and leaving.
Native membership and visible state agree. Cleanup restores the original message,
client preferences and the unguilded peer. This does not qualify every guild operation.

The full guild regression passes 355 auth/world tests. The selected guild wire
regression passes 15 cases under ASan/UBSan. The first rank build failed compilation
because of mixed integer types in one `auto` declaration; its corrected build and
six rank/query tests pass. A later source review finds this backend passes the wire
public-note flag to an officer-note implementation argument, then broadcasts the same
flag. The bridge adapts both directions to the implemented native semantics. Its six
membership/note tests pass in Release and under ASan/UBSan.

`guild_notes_01` passes separate public/officer note mutations with the correct native
columns, visible text and preservation of the other column. It also passes nonempty
guild information save/refresh, opening Guild Control without Lua errors, and self
guild/officer chat delivery. Its cleanup fails: clearing the information edit box
sends no `CMSG_GUILD_UPDATE_INFO_TEXT`, so the backend retains the previous information.
This is a client/API boundary, not a successful empty-text qualification. The rerun
`guild_notes_02` uses a distinct information probe and a nonempty reversible baseline;
it passes every listed case and restores notes, information and client preferences.
The disposable guild remains an explicitly owned fixture until the remaining guild
trials finish. Future private-client launches select `useClassicGuildUI 1`, because
the local server provides Classic guild services without Battle.net clubs. Existing
trial preference baselines remain recorded separately.

This closed batch is synchronized in
[`442_interactions_20261002_05.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261002_05.tar.gz.dvc).

The cleanup receipt `ui04/archive_cleanup.json` records targeted eviction of 21
client442 archives after matching their DVC hashes and verifying the remote. The
cache is shared at the main worktree's `.dvc/cache`; only the exact objects for these
archives were removed. Other raid cache objects, active Wine/CASC overlays, game data,
models and useful incremental build caches are preserved. Measured free disk space
increased from about 41 GiB to 55 GiB. One abandoned temporary checkpoint directory
was removed after identifying it as a copy of an already closed, uploaded batch.

For future closed checkpoints, use the reusable eviction command after checkpointing:

```bash
pixi run python -m tools.client_compatibility.evict_checkpoints \
  442_interactions_20261002_05.tar.gz \
  --receipt ~/.local/share/trinity-client442-lab/evidence/<closed-batch>/checkpoint_eviction.json
```

The command verifies the remote before deleting an archive or its exact shared-cache
object and checks references across worktrees. It runs `dvc status` and `dvc push`
afterward. Local absence is expected after eviction; it is not a missing remote copy.
Raw screenshots are removed only after matching a verified checkpoint manifest:

```bash
pixi run python -m tools.client_compatibility.prune_checkpoint_frames \
  --directory ~/.local/share/trinity-client442-lab/evidence/<closed-batch>
```

Run frame pruning before archive eviction. It rechecks the archive hash and DVC
remote, verifies every frame against the checkpoint manifest, and records removals.


## Guild ranks, lobby stability and retained data

`ui05/guild_commands_01` selects the bare-name promotion slash command but submits
no rank request. The visible Classic member button in `guild_commands_02` does
submit `CMSG_GUILD_PROMOTE_MEMBER`: the backend changes rank 4 to 3, while the
initiating client's roster stays at 4. Its legacy name-only promotion event has
no translation. The bridge now resolves the event's two public character identities
and its guild rank, then emits `SMSG_GUILD_SEND_RANK_CHANGE`. Removal events retain
both the removed member and removing officer. The full regression passes 358 tests;
19 selected guild tests pass under ASan/UBSan. Live qualification follows deployment.

`ui05/guild_commands_03` and `_04` verify promotion on both clients but fail the
next demotion attempt behind an addon-blocked popup. The flushed client taint log
attributes the failure to the compatibility addon's named bank tabs: stock
`GuildControlPopupFrame_Initialize` reads those globals and blocks
`GuildControlSetRank`. Version 2 removes widget creation and observes the mismatch
without modifying stock globals. The read-only UI observer now retains
`ADDON_ACTION_BLOCKED` and `ADDON_ACTION_FORBIDDEN` events.

`guild_commands_05` then passes promotion, demotion and peer guild chat, but the
runner expects the wrong removal confirmation caption. Its captured dialog says
"Yes". The corrected `guild_commands_06` passes promotion and demotion with native
ranks, the initiating roster and the peer's own rank; guild chat reaches both
clients; confirmed removal removes native membership and both client rosters.
Cleanup restores the unguilded scout and both UI preferences. No addon action is
blocked. `ui_clean=false` remains explicit: the stock missing-bank-tab Lua error
still occurs. Guild rank/bank controls are open requirements, and the earlier
control-window visibility pass does not qualify their protected actions.

The built-in Communities path was also checked with `useClassicGuildUI 0`; it
opens no panel while this lab's Battle.net club services are disabled. It does not
replace the local Classic guild window. No protected-action check was bypassed.

`ui05/guild_disband_01` passes the ordinary `/gdisband` confirmation with Laya,
native guild absence and the leader's visible unguilded state. The disposable
guild is removed, restoring its original pre-experiment absence. The nearby-player
fixture uses temporary private `game_tele` rows and console reloads, records both
owned accounts and positions, and restores the primary before removing those
exact rows. It does not rebuild or restart the native worldserver.

`ui05/guild_information_empty_01` repeats the empty-information save with a 150 ms
mouse press. The dialog closes without an information update packet, the native
text remains unchanged, and the fixture is restored. Empty information remains
unqualified. Reproduce it with `interaction_guild_notes --empty-information`; the
normal note/information trial continues to use a reversible nonempty baseline.

The first event-adapter reconnect attempts expire at character selection before
entering world. Modern pings were answered locally while the native socket waited
120 seconds for traffic. Realm pings now reach the native session; instance pings
are not duplicated onto that connection. Native pongs are consumed separately
from the modern latency acknowledgement. `interaction_lobby_idle` checks owned
character selection through a 165-second window and requires native pongs beyond
the original idle deadline. `lobby_idle_01` passes with five native ping/pong pairs
and an intact character-selection screen after the window. The latest full
regression still passes 358 tests; 25 selected guild/logout/login-barrier tests
pass under ASan/UBSan. Loading/timeout fixture failures remain in the batch.

The remote-verified UI04 archive and its exact shared-cache object are evicted. Its
373 raw PNG frames (767,831,220 bytes) are removed only after hash/manifest checks;
local receipt metadata occupies about 1.8 MiB. New trials keep one frame per identical
observed control page within each episode and retain the exact controls in receipts.
Every distinct page and the case before/after screenshots remain attributable.

## Nearby players, movement and follow

`ui06/nearby_players_01` receives native nonself player creations on both sessions,
but neither modern client can target its peer. The bridge discarded native kind-4
creations for other players. Public players now use Object, Unit and Player roots,
with visible gear and no private inventory, skills, currency, XP or owner-only stats.
Sparse equipment changes retain that public visibility, and removal revokes target
authority. `nearby_players_02` passes normal name targeting on both clients; retained
screenshots show the level-1 scout and the geared level-85 primary correctly.

Native `SMSG_MOVE_UPDATE` was also ignored, leaving peers at their original positions.
Its pinned native bit sequence now translates positions, orientation, timestamp,
pitch and fall data for currently visible players. It never updates the owner's
movement state. Public transport motion remains unqualified. The modern layout is
checked against TrinityCore revision `6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2`'s
[movement serializer](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/MovementPackets.cpp).

`ui06/public_follow_02` passes Laya's bounded strafe, follow and stop-follow choices.
The primary moves 8.4 yards, the scout observes the matching new target position,
and 11 native movement updates have 11 modern outgoing counterparts. Both original
positions and the temporary private teleport rows are restored. The earlier
`public_follow_01` passes those physical outcomes but its final check uses the wrong
outgoing journal direction; that failed receipt remains. Both clients stay on HDMI-1,
and the native worldserver PID/start identity is unchanged throughout the batch.

The accepted regression passes 372 tests, with 29 selected public-player, guild,
inventory and stat tests passing under ASan/UBSan. Earlier public-player test failures
remain in UI06: a fixture omitted required arrays, and the diagnostic codec lacked
the production selection adapter. Both were corrected before live deployment.
Two journal tests qualify lookup of the latest owned session across rotations and
an incomplete trailing record. Inspect, trade and broader movement cases remain open.

UI05 is checkpointed as `442_interactions_20261002_06.tar.gz.dvc`. Its 251 raw PNGs
(520,651,133 bytes) were verified and removed after remote synchronization; the
workspace archive and its exact shared-cache object were also evicted. The journal
cleanup checkpoints 75 immutable rotations, preserving 634,367,981 raw bytes remotely
before removing them locally. Active journals, recent rotations, current-batch
evidence, game data and useful build caches remain available. Session lookup now
starts with the newest rotation instead of decoding the whole historical journal.

## Inspect and trade

`ui07/peer_services_01` submits normal inspect and trade requests, but both are
unmapped. The bridge now translates visible-player inspection and native trade
requests, statuses and item offers. Inspection requires an outstanding request
for a currently visible player. Trade preserves the backend's ownership, range,
eligibility and money checks. Native and modern trade status values differ and
are mapped explicitly; nonzero socket enchants remain unsupported.

`peer_services_02` passes inspection on both clients: INSPECT_READY identifies
the requested peer, and displayed head/main-hand samples agree with native gear.
Trade opens correctly, but an invalid child frame handle interrupts the read-only
observer. Observer version 6 records and skips that child; it does not alter stock
widgets. `peer_services_03` then passes both inspection samples, trade visibility
on both clients, Laya's Cancel-button choice, and peer closure. The unidentified
child remains an observation limitation, not a qualified control.

`trade_roundtrip_02` passes eight bounded Laya choices: open, offer and both accept
buttons for an outbound and return trade. The existing five-item Draenei Tome
stack (entry 64394, native item GUID 30) changes owner from Harnessone to Harnesstwo
and back. Both clients display the offers and received stacks. The complete native
inventory and money snapshots, both saved positions, and temporary teleport rows
are restored. `trade_roundtrip_01` failed because its fixture expected the wrong
item name; it was cancelled before either acceptance and retained its baseline.
All failed protocol, observer and fixture receipts remain in the checkpoint.

The regression passes 402 tests. The selected peer/public-player/guild/inventory
and stat set passes 58 tests under ASan/UBSan, and the final 29 peer tests pass again
after the late-cancel guard. Only the compatibility bridge was rebuilt/restarted;
the native worldserver identity stayed unchanged. Inspect PvP, item level,
customizations and unsampled slots, socketed trade items, explicit gold changes,
offer editing and unaccept remain open. Automatic zero-gold and cleanup packets
do not qualify those interactions.

UI06 is checkpointed as `442_interactions_20261002_07.tar.gz.dvc`. Its 96 PNGs
(197,618,136 bytes) were verified against the remote checkpoint before removal.
Its local archive and exact cache object were also evicted. UI07 follows the same
checkpoint/prune/evict process as `442_interactions_20261002_08.tar.gz.dvc`.

## Bank services

The reversible banker fixture uses existing Olivia Burnside (entry 2455) and two
temporary private teleports. `ui08/bank_open_01` submits no NPC interaction packet:
the bank counter occludes the mouse hit. The revised staging is on the NPC's side
of the counter. `_02` opens gossip, but its fixture searches for the wrong caption.
`_03` selects the actual deposit-box option; the backend sends `SMSG_SHOW_BANK`,
which the bridge drops. These failed receipts are retained separately from the fix.

The bridge now emits `SMSG_NPC_INTERACTION_OPEN_RESULT` for a visible native banker,
translates character-bank auto deposit/withdraw requests, and consumes the modern
close notification. Bank moves require the native bank-open grant and retain the
backend's inventory/range checks. Account and guild banking are rejected by this
character-bank adapter. The serializer follows the pinned
[bank handler](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Handlers/BankHandler.cpp)
and [NPC packets](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/NPCPackets.cpp).

`bank_open_04` passes ordinary opening and closure, with 28 visible base slots.
`bank_roundtrip_01` passes five Laya choices, including depositing the existing
five-item Draenei Tome stack into base bank slot 1 and withdrawing it into its
original backpack slot 2. The independent native inventory oracle preserves item
GUID 4611686018427387934, entry 64394 and count 5; addon-visible contents agree.
The complete native inventory/money snapshot and saved position are restored, and
both temporary teleports are removed. Screenshots were visually checked. Observer
version 7 adds read-only base bank contents on both owned clients.

All 411 regression tests and 46 selected bank/peer/inventory ASan/UBSan tests pass;
the bridge was the only restarted service. Bank bag purchases, equipped bank bags,
split/merge variants, persistence and negative gameplay paths remain open. This
does not qualify the whole bank family. Reproduce the bounded round trip after
verifying the NPC's screen point for the current camera:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_bank --roundtrip --point 639 176 --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/bank_roundtrip_01
```

The runner preserves restore teleports if inventory cleanup fails. Its fallback
withdrawal is a separately attributed code-controlled ordinary-input episode.
UI07's remote-verified archive/cache copies (336,643,587 bytes each) and 156 raw
PNG frames (341,920,281 bytes) were removed locally; about 1.3 MiB of metadata
remains. UI08 uses checkpoint `442_interactions_20261002_09.tar.gz.dvc`.

## Merchant services

UI09 stages existing Thurman Mullby (entry 1285). The initial facing offset put the
camera behind a wall. The revised non-bank fixture approaches the NPC from its
facing direction. A restoration attempt also exposed SQL FLOAT text rounding;
temporary rows now retain canonical stored values and all rows are checked before
any deletion. Failed staging and blocked attempts remain in the evidence.

`merchant_open_02` selects the visible goods option, but the bridge drops the
native `SMSG_VENDOR_INVENTORY`. The new serializer preserves native catalog IDs,
prices, quantities and extended-cost/condition fields in the modern item-instance
layout. Six packet tests, all 417 regression tests and 52 selected sanitizer tests
pass. `merchant_open_03` passes three Laya choices for interaction, gossip and
closure. Its nine displayed item IDs exactly match the native vendor fixture.
Catalog screenshots were visually checked on HDMI-1. Commerce variants remain
separate acceptance cases.

`merchant_sale_01` selects the correct backpack right-click. The bridge logs an
unmapped `CMSG_SELL_ITEM`; native money and item ownership remain unchanged. The
complete native inventory/money baseline and original position are restored.
Sell and buyback requests now preserve native vendor/item identity and translate
the twelve buyback slots. The adapter also translates sell errors and carries
private money, buyback-price and timestamp changes. Both pinned cores use the same
login-relative timestamp units, as shown in the pinned
[buyback implementation](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Entities/Player/Player.cpp#L11256).
Observer version 9 reads only the selected merchant tab, keeping its pixel payload
bounded. It does not mutate stock widgets or submit gameplay APIs.

Nine new transaction tests pass. The first compile caught an integer deduction
mismatch, corrected with an explicit 64-bit type. The first sanitizer invocation
named a nonexistent test file and ran no tests; the corrected selection passes 61.
The full suite initially reported 425 passes and one failure because its independent
create-field oracle lacked the new buyback arrays. After updating that oracle, all
426 tests pass. These earlier failures are retained, and the native worldserver has
not been rebuilt or restarted.

`merchant_sale_02` completes seven Laya choices. It sells existing Recruit's Pants
(entry 39, count 1, native GUID 4611686018427387908) for one copper, displays the
item and price in Buyback, buys it back into automatically chosen backpack slot 3,
then drags it back to original slot 8 and closes the merchant. Native and visible
money agree at 99,977,309 after sale and 99,977,308 after buyback. The complete
native inventory/money snapshot and original position are restored, both temporary
teleports are removed, and screenshots were visually checked on HDMI-1.
Packet receipts include modern/native sell and buyback request pairs.
Purchase, repair, partial-stack, stock, discount and negative variants remain open.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_npc --service merchant --point 639 100 --sell-buyback --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/merchant_sale_01
```

The screen point must be checked for the current camera. Failed cleanup preserves
the NPC restore rows and open merchant. Any fallback buyback or slot restoration
has its own code-controlled receipt and is excluded from model qualification.
UI08's 109 raw PNG frames (166,380,164 bytes) and verified archive/cache copies
(166,247,857 bytes each) have been removed locally. UI09 is closed as checkpoint
`442_interactions_20261002_10.tar.gz.dvc` before its raw frames are pruned.

UI09's remote-verified archive is 274,426,128 bytes, SHA-256
`da618f4eb7a1f10d7e50638d8bbde25fc72ac750a03be5627b4d1cb4dd11fb00`.
Its 176 raw PNG frames (276,316,910 bytes) and local archive/cache copies were
removed after verification; 1.5 MiB of receipts remain. Six older immutable journal
rotations (50,332,328 bytes) were separately checkpointed, verified and removed.
Their 5,559,199-byte archive/cache copies were also evicted. Active journals, the
two newest rotations per journal and useful build caches were preserved.

### Purchase trials

UI10 (`client_interactions_20261003_ui10`) uses the same native process and separate
databases. `merchant_purchase_01` selects the correct water bundle right-click,
but the bridge drops `CMSG_BUY_ITEM`; inventory/money and position are restored.
The initial adapter passes seven purchase tests, 433 regression tests and 68
selected sanitizer tests. Its first bag fixture used the wrong object-kind byte
offset; that fixture failure is retained and corrected.

`merchant_purchase_02` exposes a gap in those generated tests: the destination slot
was serialized as a byte, while the pinned `BuyItem` header and captured 60895
request use `uint32`. The adapter closes the test connection on trailing bytes
before sending a native purchase. Native inventory/money remain exactly at the
baseline. The original position and held NPC teleports are restored through a
separate native-console cleanup, including offline position restoration. The
parser now matches the 32-bit slot and signed quantity and has a regression using
the actual closed request. The generic NPC cleanup restores verified positions
even if UI observation disconnects. These failures remain separate from later
gameplay qualification.

The captured-layout correction passes 434 regression tests and 69 selected
ASan/UBSan tests. `merchant_purchase_03` completes four Laya choices and acquires
five Refreshing Spring Water (159) for exactly 23 copper. Native and visible money
agree at 99,977,285. Its packet trace exposes a separate missing receipt: the
bridge drops the native 45-byte `SMSG_ITEM_PUSH_RESULT`. The inventory and money
pass therefore does not qualify acquisition notifications.

The notification adapter preserves the native recipient, quantity, inventory
total, storage position, stacking sentinel, creation and chat visibility flags.
The native packet has no item GUID and may precede the item's creation update;
the adapter explicitly leaves that modern field empty. Item identity-dependent
toasts and quest notification variants remain unqualified. The pinned modern
[ItemPushResult writer](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/ItemPackets.cpp)
and native `Player::SendNewItem` define the two layouts. Four notification tests
include the actual vendor packet; all 438 regression tests and 73 selected
ASan/UBSan tests pass.

`merchant_purchase_04` completes the same four choices with native/client item and
money agreement plus a fresh `CHAT_MSG_LOOT` observation for item 159, count 5.
The screenshot visibly shows the normal received-item chat message. Packet
receipts include the 42-to-30-byte purchase request, 20-to-22-byte success reply
and 45-to-56-byte item notification. Both purchase runs restore the complete
inventory/money snapshot, original position and temporary teleports. Narrow,
temporary item/money fixture permissions are separately attributed and revoked;
fixture cleanup is excluded from Laya qualification. Only the bridge restarted.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_npc --service merchant --point 639 100 --purchase --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/merchant_purchase_01
```

Repair and trainer probes now use existing Heinrich Stone, Wu Shen and Lilyssia
Nightbreeze fixtures. Their windows, mutations and negative paths are pending.

UI10 is closed as `442_interactions_20261003_11.tar.gz.dvc`: 229,199,169 bytes,
SHA-256 `b3dbf33e4d8358d8d846260523cfad841e4e7050d23467d8179b76c8612470fa`.
After remote verification, 147 raw PNG frames (230,319,590 bytes) and the local
archive/cache copies (229,199,169 bytes each) are removed; 1.4 MiB of receipts
remain. Post-experiment `dvc status` reports the deliberately absent local output,
and `dvc push` confirms that the remote is up to date. UI11 is the new active batch.

### Repair and trainer trials

UI11 uses the unchanged isolated native worldserver. `repair_open_01` opens and
closes Heinrich Stone's merchant with three Laya choices. Its repair quote is
163,335 copper for ten pre-existing worn items. `repair_all_01` selects the right
button, but the bridge drops `CMSG_REPAIR_ITEM`; no native mutation occurs.
The repair adapter preserves visible NPC and owned item identity and the guild
bank choice. Its three tests cover repair-all, an individual item and ownership
rejection. Guild repair rights and individual repair remain live qualifications.

`repair_all_02` repairs all ten items and clears the visible quote, but charges
163,332 copper. This run remains failed because the charge differs from the quote.
Inventory, money, position and temporary permissions are restored; the repaired
gear is deliberately retained. Selected native item and durability table records
reproduce 163,332 with the existing round-then-truncate formula and 163,335 with
rounding after the discount. The pricing change has not yet been live-qualified.

`trainer_open_01` submits correct inputs but its native catalog is unmapped.
`trainer_open_02` exposes a second layout problem: the running backend emits
34-byte spell rows while the initial parser assumed 38-byte rows. The initial
38-byte parser rejects the captured 1,524-byte response and closes the connection.
Native-console cleanup restores the original position and deletes both temporary
teleports. The parser now validates both complete framed layouts and accepts
exactly one. The 38-byte legacy profession flags are validated and omitted from
modern rows; the captured 34-byte tail is preserved. Seven trainer tests include
the actual 43-row response. A prefix test initially rejected a byte sequence that
is independently valid as an alternate 34-byte row and empty greeting; the
corrected regression explicitly covers that valid packet. Both test receipts remain.

`trainer_open_03` completes three Laya choices. The stock warrior trainer displays
available Parry and Plate Specialization, and closes normally. The service
screenshot is visually checked on HDMI-1. Learning and incremental learned-spell
notifications remain separate pending cases. All 448 regression tests and 83
selected ASan/UBSan tests pass. Only the bridge has restarted during UI11.

UI11 is closed as `442_interactions_20261003_12.tar.gz.dvc`: 229,758,220 bytes,
SHA-256 `9a75a27d7866dcd9f7088e627482be9e903ba891a0eb3d74ce9f313d5b192f72`.
Remote verification precedes removal of 230,936,255 bytes of raw frames and both
local 229,758,220-byte archive/cache copies. Small receipts remain. `dvc status`
reports the deliberately evicted output, and `dvc push` confirms remote completion.

### Repair pricing and trainer learning

UI12 starts after the one required private native worldserver rebuild. The main
raid worldserver and databases remain untouched. `Client442.RepairCostRounding = 1`
enables a single rounding after discount and rate in the lab; the distributed
config defaults to zero and preserves legacy arithmetic. A compiled native pure
calculation test covers the ten captured items, both totals, rate multiplication,
unworn items and artifact minimum pricing. `Item.cpp` is split into 718-line item
storage, 834-line item mechanics and a 66-line durability unit to satisfy the
source-size guard. The incremental worldserver target builds successfully.

The native-console/SQL fixture restores exactly the ten earlier observed wear
values while the private server is stopped, after verifying owned full-durability
items. `repair_all_03` completes four Laya choices. Native and visible money agree
on a 163,335-copper charge, all ten items become fully repaired, and the client
quote clears. Inventory, experiment money, position and temporary permissions
are restored; repaired gear is retained. The obsolete 67,411,216-byte rollback
binary is removed after the successful deployment trial. Useful build caches remain.

`trainer_learn_01` selects the normal Train button for available Parry. The bridge
drops the actual 17-byte purchase request; no money or spell mutation occurs,
and the complete fixture is restored. The new adapter preserves native trainer,
trainer ID and spell ID, translates money/unavailable errors, and maps the native
skill rejection to the modern unavailable reason. The modern protocol has no
trainer success opcode; its legacy acknowledgement is validated and consumed.
The actual 8-byte native learned-spell message becomes the pinned 14-byte modern
`LearnedSpells` form with normal messaging.

A subsequent source audit corrects the UI11 layout interpretation: both the native
header and writer use **two** prerequisite spells followed by profession dialog
and button flags, totaling 34 bytes. The initial 38-byte assumption and temporary
three-prerequisite/tail interpretation were wrong. Class catalog rows had zero
profession flags, so the earlier warrior window passed. The corrected parser
validates the two flags, preserves two prerequisites, and adds zero for the modern
third prerequisite and `Unk440`. Profession flags are no longer misread as a
prerequisite spell. The earlier 453-test/87-sanitizer run is retained; after the
semantic correction and actual request regression, all 454 tests and 88 selected
ASan/UBSan tests pass.

`trainer_learn_02` completes four Laya choices. Parry (3127) becomes active and
undisabled in native state and known in the client. Both charge exactly 646 copper,
and the screenshot shows the normal learned-ability chat message. Packet receipts
pair the 17-to-16-byte purchase and 8-to-14-byte learned-spell notification; the
12-byte legacy acknowledgement is consumed. Inventory, experiment money and
original position are restored, both temporary teleports are removed, and the
learned passive skill is retained. Both clients have clean read-only observer
version 12 and verified HDMI-1 windows. Only the bridge restarts for this training fix.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_npc --service trainer --point 644 214 --learn --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/trainer_learn_01
```

Learning requires an existing unlearned affordable Parry fixture; it does not
silently unlearn an already qualified skill to create artificial repetition.
Profession training, incremental unlearn/supersession and trainer failure UI
remain separate acceptance cases. Quest, mail and auction work remains open.

UI12 is closed as `442_interactions_20261003_13.tar.gz.dvc`: 128,261,820 bytes,
SHA-256 `98608515b1652b56bc9b0a0a327f752653b82fdb6201663b33d128d84fb0e890`.
Its raw frames and local archive/cache copies are removed only after remote
verification. `dvc status` records the intended local eviction and `dvc push`
confirms synchronization. UI13 starts the questgiver probes.
