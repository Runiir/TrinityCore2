# Quest credit, rewards and talent learning follow-up

The isolated native worldserver remains PID 3428101, start ticks 15075252.
The main raid-bot worktree and databases are unchanged. New trials use ordinary
keyboard/mouse inputs with the code controller; no new Laya or Jev calls occur.
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
into a completion claim.

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
an ordinary addon reload. Learned state is retained. The trial is implemented;
live specialization and point-spending qualification remain pending.

The talent observer records the stock preview preference, primary and preview
specializations, first-tier and allocated ranks, and confirmation dialogs.
Preview rank is the eighth GetTalentInfo result, as used by the pinned stock
TalentFrameBase source. Login persistence and other talent/glyph operations remain
open.

## Validation and deployment

The quest-credit candidate passed 14 selected packet tests and 14 sanitizer tests,
then 675 world regression tests. Moving spline observation passed 12 selected
checks. The reward/talent candidate passed 13 selected packet tests and 13
sanitizer tests, then 685 world regression tests. These are protocol tests, not
live reward or talent qualification.

The first deployment precheck found the scout at character selection and stopped
before changing the bridge. Ordinary Enter World input recovered the scout.
`quest_reward_deployment_02` then restarted only the independent C++ bridge and
installed observer v34. The native worldserver identity was verified unchanged.
Both client reconnects are checked against their recorded resources, equipment,
group and raid-profile state and against the second physical monitor.
