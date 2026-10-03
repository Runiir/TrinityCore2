# Earned quest rewards and stock glyph filters

The isolated lab now completes quest 52 through ordinary melee and collects its
reward through the stock client window. Learned, unlearned, Prime, Major and Minor
glyph filters also pass their catalog and restoration checks. These are code
controlled compatibility trials; concurrent Laya input isolation is documented in
[the two-client report](isolated_clients_20261003.md).

## Reward request repair

UI28 `quest_reward_04` earned all five bear and eight wolf credits. Selecting the
first reward succeeded, but completing the quest disconnected the client. The
captured `CMSG_QUEST_GIVER_CHOOSE_REWARD` selected item 57523 with quantity zero.
The bridge had required a matching nonzero quantity and rejected the request
before forwarding it to native. The failed episode and packet remain unchanged.

`quest_turnin.cpp` now permits zero quantity for a unique offered plain item ID.
A supplied positive quantity must still match. Unknown items, ambiguous zero
quantity choices, unsupported item metadata, inactive quests and unseen givers
remain rejected. Native receives its offer index and awards its own quantity.
Regression checks include the exact captured request, duplicate identities,
unknown IDs and invalid quantities.

The completed quest was preserved through reentry. The separate
`quest_reward_04_cleanup_01` verifies quest history, inventory, money, restored
pose and deletion of temporary teleport rows. `quest_reward_05` stopped before
interaction because its inventory oracle compared Python tuples with JSON lists;
the retry normalizes that representation without discarding any field.

`quest_reward_06` resumes the attributable completion and passes the ordinary
turn-in. It selects the first of three choices, receives one item 57523 and two
potions 858, and gains exactly 640 copper. Native and modern completion packets
both report quest 52, zero XP and 640 copper. The level-85 character cannot gain
XP, so this does not qualify XP gain or leveling. The normal backpack observation
agrees with both new native item rows. Earned history, items and money are retained;
fixture pose is restored. Teleport staging does not qualify navigation.

## Glyph filters

`glyph_filters_02` exercises the stock dropdown's **Already Known** and
**Unavailable** checkboxes. Known-only displays Battle; unknown-only displays the
other 33 glyphs. Restoring both filters returns the complete 34-glyph catalog plus
three headers. Exact identities, names, types, learned flags and filter state are
compared, while rebuilt row indexes are allowed to change during filtering.

The first filter trial passed known-only but its next menu lookup used the wrong
caption, **Used**. Its cleanup failed for the same reason. The separate
`glyph_filters_cleanup_01` restores the original catalog and verifies native
inventory, money, spells, talents and glyphs before the fresh full trial.

`glyph_type_filters_01` collapses Prime, Major and Minor in that order, then
expands them in reverse order. The observed glyph counts are 25, 8, 0, 8, 25 and
34. Ordinary header clicks bring each next header into view. All five filter
flags and the exact original catalog are restored. Both successful filter suites
preserve native inventory, money, learned spells, talents and applied glyphs.
Replacement, other glyph applications, tooltips and glyph effects remain open.

## Low-level quest tracking

`quest_tracking_01` opens the stock minimap menu and toggles **Low Level Quests**
on and off. Each public tracking catalog differs only at that setting; the
original catalog, quest history, inventory, money and pose are restored. The
tracking controls pass, but the overhead marker remains unqualified: reviewed
screenshots show no marker both before and after enabling the setting.

The visible Guard Thomas GUID matches the status packet. Native status 4 maps
to modern 64, the trivial category. Each toggle also sends an actual two-GUID
`CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY`; both are logged as unmapped. This is a
separate missing request adapter. The pinned modern
[handler](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Handlers/QuestHandler.cpp#L627)
responds through the multiple-status path for requested questgivers. Implementing
that adapter and retrying the visible marker is the next repair; the current
control pass does not establish its rendering behavior.

## Runtime and checks

The optimized full regression passes **722** checks. The focused reward suite
passes **9** checks under ASan/UBSan. Only the standalone C++ bridge was rebuilt
and restarted. Both clients reconnected with observer v37 and passed their public
resource, equipment, group and profile baselines on their private displays and
HDMI-1. An earlier deployment precheck found the scout at character selection;
it stopped before restarting the bridge and is retained alongside successful
scout reentry and deployment.

The native worldserver remains PID 3428101, start ticks 15075252, with binary
SHA-256 `2882faddd8df9214e634643e821b35c56d464f0470b0fdaaeed1b5b7d3a2ab5a`.
The bridge source digest is
`7dea2c273a3d72a95de8d7adc8d99d854a2833c7d85d94e8970be700084f2949`,
and optimized binary SHA-256 is
`41c4683597473e80d619935a927850d1acb4233ce06abf008277718311e53ab2`.

New filter trials can run after the registered warrior has learned Battle and
all filters are enabled:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_glyph_filters --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/glyph_filters_01
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_glyph_type_filters --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/glyph_type_filters_01
```

Quest 52 is now rewarded on this character. Do not remove earned history to rerun
it. A reward resume requires a closed thirteen-kill completion, verified cleanup,
unchanged quest/inventory baseline and a fresh screenshot review of the giver.
The remaining interaction families and protocol/content variants still require
their own evidence.
