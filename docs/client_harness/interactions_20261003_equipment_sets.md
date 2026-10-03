# Stock equipment sets

UI36 keeps one shared native worldserver running. The separate C++ bridge gains
equipment-set request/reply translation. Both clients retain private input
displays and HDMI-1 windows. New runs use ordinary code-controlled inputs.

The first manager inspection stops at the collapsed character layout. A second
inspection expands the panel and opens New Set, then exposes a harness error:
the focused name field consumes Return, so a diagnostic chat command creates a
client-only set named `/tcui equipment`. The command is removed from this dialog
flow. `equipment_sets_create_01` also creates only a client entry: its ordinary
226-byte `CMSG_SAVE_EQUIPMENT_SET` reaches the bridge as an unmapped packet.
Native set rows remain empty and all native resources stay unchanged. Every
failed episode remains in the evidence.

The bridge translates save/delete/use requests, the native list, assigned set
identity and use result. Set identities come from the owned native list or a
causally matched native save acknowledgement. Item GUIDs must belong to the
owned inventory. Source positions use the existing inventory mapping. Ignored
slots retain their native raw-GUID-one semantics. Outstanding save/use requests
are bounded. The native server keeps authority over item validation and swaps.

The modern contract is pinned to the
[WPP equipment parser](https://github.com/TrinityCore/WowPacketParser/blob/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2/WowPacketParserModule.V4_4_0_54481/Parsers/EquipmentSetHandler.cs),
including the 4.4.1-and-later acknowledgement/result order. Stock Cata character
and paper-doll sources come from the installed build 60895 CASC. Observer v46
reads public equipment-set data; v47 identifies the stock row's edit/delete
buttons without changing them.

Four positive wire regressions fail against the old bridge. The first test
invocation uses the default pixi environment without Crypto and fails during
collection; no test executes. The corrected auth-manifest invocation retains the
four failures. The patched optimized bridge passes all 796 protocol tests, and
13 equipment/inventory tests pass ASan/UBSan. Both test receipts remain alongside
the pre-fix failures. C++ changes are confined to the independent bridge target.
The worldserver binary and process lifetime remain unchanged.

After reconnecting both owned clients, the native empty catalog is translated
to an empty modern catalog on each. `equipment_sets_create_02` creates the stock
HarnessUI36 set normally. All 19 native slots match the existing inventory, and
the stock manager shows the one equipped set. The complete request, native save,
native acknowledgement and modern acknowledgement form a captured packet chain.
All native resources stay unchanged.

The full-session trial uses normal menu logout and a separately reviewed
character-selection frame before Enter. Its first reentry preserves both native
and public state, including the set, but the packet observer was primed after
login and discarded the captured login events. That harness failure is retained;
the observer is corrected to prime before input and a fresh whole trial is run.
`equipment_set_reenter_02` passes every public/native baseline, ordinary login,
native list and translated modern list check. Its reviewed stock manager shows
the preserved set after the complete logout and reentry.

The shipped edit button opens a context menu before the name/icon dialog. Its
builder calls the absent `GetNumSpecializations` API and passes the edit button
where the popup expects its owning set row. A read-only probe finds no legacy
count/info API before or after ordinary talent-window loading. Observer v48
records those capabilities; v49 records the compatibility menu's status.
`Client442Compatibility/EquipmentMenu.lua` repairs the basic name/icon entry for
this exact client build and API absence. It keeps the stock dialog and gameplay
API. Specialization assignment stays unavailable and unqualified.

`equipment_set_roundtrip_02` saves the normal edited name HarnessSaved, preserves
set identity and every slot, survives interface reload, then equips the saved set
to restore a normally unequipped helmet. The delete click does not open its
confirmation in the first observation, so the episode remains failed. Recovery
attempts also retain early panel-check failures and one diagnostic command whose
missing leading slash sent `tcui equipment` as ordinary chat. They do not qualify
new operations. The corrected runner waits for requested panels without replaying
inputs, settles the hover-only buttons, matches diagnostic chat to the normal
background transport timing, and explicitly verifies the original sidebar layout.
The later recovery proves one Character click appears after three pending
snapshots without another click; this does not classify every earlier miss.

Two additional optimized equipment guards and the same two ASan/UBSan guards
pass for multi-record catalog bit boundaries and bounded FIFO use attribution.
Eight existing input/cleanup guards pass. These are protocol and harness checks;
they do not replace the remaining live set deletion and complete roundtrip.

The source-bound deletion recovery later confirms and deletes the native set,
and both catalogs remain empty after reload. Its final sidebar observation fails,
so that whole episode stays failed. A separate display recovery verifies the
original collapsed layout and unchanged native resources. A fresh creation trial
then creates HarnessUI36 normally and restores the sidebar. Its reviewed stock
manager shows the native set equipped. The next roundtrip reaches the name/icon
dialog, but physical editing leaves its original name unchanged. The original
cause remains unproven; cleanup restores the layout and native resources.
Observer v52 records visible edit-field text and keyboard focus. The runner now
waits for the selected field to have focus before sending text, then waits for the
requested value without repeating the input. All 13 selected input, cleanup and
control-catalog guards pass. A fresh complete roundtrip remains required.

A reviewed expanded stats panel also shows a nonnumeric melee DPS value. The
public damage percentage is zero while the native school modifier is nonzero.
Two positive wire regressions fail against the retained running bridge. The next
bridge build translates all seven native school damage modifiers in both full
creation and sparse updates. All 824 protocol/authentication tests and 23 focused
ASan/UBSan tests pass. This build is not yet deployed or live-qualified; the
equipment trial continues on its retained earlier bridge. Item-level display
remains a separate open check. Neither build changes the native worldserver.

Reproduction uses new owned output directories:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_equipment_sets --phase create --output <new-create-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_equipment_set_session logout --source <successful-create-episode.json> --output <new-logout-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_equipment_set_session reenter --reviewed-character-selection --source <successful-logout-episode.json> --output <new-reentry-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_equipment_set_roundtrip --source <successful-create-episode.json> --output <new-roundtrip-directory>
```

Creation requires the primary actor's empty native equipment-set catalog. The
later phases bind the exact successful source, actor, client/server lifetimes and
complete native state. The review flag records an inspection already completed.
Save/use/delete and their restoration are separate checks from creation.

Current scope is one warrior's ordinary equipment set and ASCII names. Native
slots support indices 0 through 9. Larger catalogs, specialization assignment,
appearance sets, cosmetic fields and full-inventory swap failures remain open.
The bridge rejects unsupported types and fields rather than saving false native
state. These limits remain in the checklist's qualification records.
