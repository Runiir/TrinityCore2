# Quest credit, rewards and talent learning follow-up

The isolated native worldserver remains PID 3428101, start ticks 15075252.
The main raid-bot worktree and databases are unchanged. New trials use ordinary
keyboard/mouse inputs with the code controller. The later user-requested desktop
isolation check explicitly uses Laya for a bounded two-client UI probe; it does
not change the controller attribution of the quest or talent trials.
Temporary console teleports place the actor beside existing creatures and NPCs.
They do not qualify navigation, quest completion or combat.

## Native quest credit

`native_bridge/quest_progress.cpp` translates native quest kill credit into the
60895 packed victim GUID, quest/object IDs, 16-bit counts and objective type.
The native active quest remains authoritative. Full-reader, identity, ownership
and count checks reject malformed credit. The completion notification preserves
the native quest ID.

UI25 `quest_complete_05` accepted Protect the Frontier through the stock quest
window and earned all eight wolf credits through ordinary melee attacks. Each
credit agrees in native quest state, the public client objective counter and the
translated credit packet. The first bear could not be selected by the exact-name
command, although native create packets show an alive bear nearby. The run failed
and restored the original quest, inventory, money and pose. It does not qualify
full quest completion.

Retained failures include moving-target out-of-range engagement, a staging
radius that rejected the third wolf, combat cleanup checked before departure,
a fresh point review that expired, and the bear targeting failure. The staging
radius and combat cleanup were repaired; earlier partial kills are not combined
into a completion claim. `quest_reward_01` earned three bear credits, then an
uphill offset placed the actor below the client floor and produced a -561-yard
player Z. Its 3D distance guard stopped the run and cleanup restored the full
quest/inventory/money/pose baseline. Initial combat staging now starts eight yards
above spawn Z, and target staging three yards above observed creature Z, so
normal client gravity can settle before the ground approach.

UI25 `quest_reward_03` earned all five bear and eight wolf credits in one run.
Native quest 52 was complete with counters 8/5, and both public objectives were
finished. The fresh giver frame showed the yellow turn-in question mark above
Guard Thomas. Reward collection stopped before the choice because the diagnostic
incorrectly required the capped character's public zero XP to equal the raw offer
XP of 65. Cleanup restored the disposable quest; no reward was claimed. The
runner now expects zero awarded XP at level 85, matching native SendQuestReward.

`observation/spline_pose.py` estimates current ground movement from ordinary
native spline packets. It uses path distance and recorded duration. Curved
uncompressed paths remain a polyline estimate, not an exact private server pose.
The ordinary melee approach is bounded and records every physical key input.

## Ordinary reward adapter

`native_bridge/quest_turnin.cpp` translates NPC completion, reward requests,
reward offers, plain item choice and final completion. A modern chosen item and
quantity map to an index in the last authoritative native offer. The bridge
requires an owned active quest and a visible native NPC questgiver. Currency,
modified item choices, item/game-object givers and unsupported progress dialogs
still require separate implementations and live tests.

`interaction_quest_reward.py` completes both kill objectives before opening the
stock reward panel, comparing its choices, fixed items, money and XP with the
native offer, and clicking the normal reward controls. It checks reward history,
item quantities, money and native/modern completion agreement. This runner is
implemented; live reward qualification remains pending.

Legitimate rewards are retained. They are recorded separately from reversible
fixture setup. If the native server awards the quest before a later observation
fails, cleanup preserves the earned history and items instead of removing them.
The failed diagnostic remains failed.

The same offer exposed a backend bug in Quest::BuildQuestRewards: its fixed-item
count used GetReqItemsCount instead of GetRewItemsCount. Quest 52 serialized two
healing potions (item 858), but advertised zero fixed rewards. The source is
corrected. The bridge also derives the count from contiguous authoritative reward
arrays, supporting the still-running old native binary without a worldserver
restart. Sparse or incomplete rows are rejected. The native source correction
will enter the next required native build; it is not deployed in this batch.

Future failed reward checks preserve an attributable completed quest when all
thirteen ordinary kills, native counters and unchanged inventory agree. Use
`interaction_quest_reward --completed-episode <closed episode.json>` with a fresh
reward point file to retry only turn-in. The source receipt digest and current
native quest/inventory baseline are verified; no command generates quest credit.

The read-only observer v34 has a dedicated quest reward page and records stock
minimap tracking state. The page never invokes quest actions or changes frames.
The reward controls follow the pinned [stock quest UI source](https://github.com/Gethe/wow-ui-source/blob/a1ca983a43a7aa73b5764d3245925ba40869fce3/Interface/AddOns/Blizzard_UIPanels_Game/TBC/QuestInfo.lua).

## Talent learning

The modern talent preview request reverses the native count/tree header. The
bridge now reorders it while preserving 32-bit preview ranks and validating
counts, tree indexes and unique talent IDs. Single-talent learning still widens
its modern 16-bit rank to the native 32-bit rank.

`interaction_talent_learn.py` selects Arms and spends one first-tier point through
the stock UI. It verifies the requested talent against the native Talent.dbc,
checks the learned spell and one-point charge, and checks the public rank after
an ordinary addon reload. Learned state is retained. UI25 `talent_learn_01` passed. The stock UI selected Arms, previewed one point
in Blitz, opened the normal Learn confirmation and learned native talent 9664,
rank zero, corresponding to spell 80976. Native talent tree 746 and the public
Blitz rank one agree; unspent points changed from 41 to 40. The learned state
persisted in native storage and after an ordinary addon reload. Inventory and
money were unchanged. The screenshot shows the correct Arms total of one.
Logout/login persistence and other talents remain open.

The talent observer records the stock preview preference, primary and preview
specializations, first-tier and allocated ranks, and confirmation dialogs.
Preview rank is the eighth GetTalentInfo result, as used by the pinned stock
TalentFrameBase source. Observer v34 omitted the explicit talent-group argument when reading per-tree
totals, although the stock frame correctly displayed one point. The pending v35
observer passes the active group used by the stock UI and adds bounded read-only
glyph catalog pages. `fixed_reward_deployment_01` deployed v35 on both clients.
`talent_glyph_catalog_02` passed with Arms/Fury/Protection totals 1/0/0,
40 unspent points, all nine typed sockets and the complete 37-row catalog. Search
for Battle showed the one matching glyph and clearing restored the original
catalog. The first catalog trial falsely rejected the stock SEARCH placeholder
after focus loss; its failed receipt and restored native baseline are retained.
Login persistence and glyph learning/application/removal remain open.

The pinned native GlyphSlot.dbc and installed 60895 GlyphSlot.db2 rows have
identical IDs, numeric types and tiers. UI26 `glyph_slot_positions_10` initially
passed an incorrect catalog-derived type oracle. UI27 `glyph_apply_01` exposed
that error: pending Battle matched socket type 2, while socket 2 had type 3 and
its stock tooltip called it Prime. GetGlyphInfo uses Prime=1/Major=2/Minor=3;
GetGlyphSocketInfo uses Major=1/Minor=2/Prime=3. Those API enums cannot be reused.
The erroneous rotation is removed; create and sparse updates preserve the
pinned slot IDs. The corrected ordered socket types are
`1,2,2,1,2,1,3,3,3`. The earlier type-position qualification is superseded and
requires a fresh live check; historical receipts remain unchanged.

`glyph_learn_01` right-clicked one staged Glyph of Battle book. The client opened
its glyph placement UI. No item-use request was retained in that packet capture,
and no spell was learned. Item-use packets were not included in the capture
whitelist at the time, so that receipt cannot establish whether one was sent.
Escape then sent a valid local cancellation for spell 483, which had no native
cast. The bridge incorrectly closed the connection. Cleanup could not finish
while disconnected. The primary client reconnected through ordinary private-display
input, and the exact unused book was removed. The first cleanup checked persisted
inventory before a native save and reported a stale DB row; a read-only saved-state
verification then passed the full original inventory/money/spell/talent baseline.
Neither failed receipt is counted as glyph learning. Local cursor cancellations
now produce no native packet when there is no owned cast; malformed requests are
still rejected. Observer v36 adds read-only pending-glyph/socket-match diagnostics
for the next ordinary placement trace.

## Desktop isolation

Both actors already run in separate Gamescope X displays, Wine prefixes and
client directories. The old input adapter activated their host windows and shared
one global input lock. Input now verifies HDMI-1 placement without moving the
window, focuses only the owned nested game window, and uses one lock per actor.
The Wine window is bound to its Gamescope supervisor by process ancestry. Reused
client PIDs and actor switches invalidate an existing adapter.

`isolated_laya_ui_01` passed three ordinary panel operations on both clients,
using the explicitly requested local Laya model and its pinned revision. The two
worker lifetimes overlap. Across 593 read-only desktop samples, host focus and
pointer stayed unchanged and both game windows remained in the background.
Resources, equipment and groups were unchanged, and panels were closed afterward.
This proves the bounded two-client input case; long-running roaming remains open.
The subsequent [C++ sender trial](isolated_clients_20261003.md) passes the same
six actions with 2,158 unchanged desktop samples and per-actor libei devices.

## Validation and deployment

The quest-credit candidate passed 14 selected packet tests and 14 sanitizer tests,
then 675 world regression tests. Moving spline observation passed 12 selected
checks. The reward/talent candidate passed 13 selected packet tests and 13
sanitizer tests, then 685 world regression tests. These are protocol tests, not
live reward or talent qualification.

The fixed-reward count candidate initially passed 685 tests and failed one old
quest-details assertion that expected the erroneous zero count. Its captured
packet already contains item 57255 quantity one. The assertion now requires one
fixed reward and still verifies the exact item. The sanitizer selection initially
failed the same assertion (8 passed); its corrected rerun passed all 9 checks.

The first deployment precheck found the scout at character selection and stopped
before changing the bridge. Ordinary Enter World input recovered the scout.
`quest_reward_deployment_02` then restarted only the independent C++ bridge and
installed observer v34. The native worldserver identity was verified unchanged.
Both client reconnects are checked against their recorded resources, equipment,
group and raid-profile state and against the second physical monitor.
