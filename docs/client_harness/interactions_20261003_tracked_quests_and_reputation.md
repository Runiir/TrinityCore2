# Tracked quest markers and reputation state

The UI29 tracked-status repair makes the eligible low-level questgiver marker
appear when the stock **Low Level Quests** setting is enabled and disappear when
it is disabled. This follows the failed visual check in
[the UI28 reward and filter report](interactions_20261003_quest_claim_and_filters.md).
Both clients retain their private input displays and verified HDMI-1 host windows.

## Tracked-status request

The actual two-GUID `CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY` was previously unmapped.
The adapter now validates a bounded list of canonical creature/game-object
identities on the owned realm and map. Empty lists receive an empty multiple
reply. Duplicate and cached identities are harmless reads; none grants visibility
or hello/accept/reward access. Truncated, trailing, foreign and oversized requests
are rejected.

Native 4.3.4 has no subset request. Nonempty tracked reads therefore request a
fresh native all-visible status list, retaining authoritative eligibility and
the existing visible-giver response guard. Extra visible status rows are permitted.
The adapter does not associate a queued subset with the next response: native
also sends unsolicited multiple updates after quest-state changes. The pinned
modern [tracked handler](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Handlers/QuestHandler.cpp#L627)
uses the multiple-status response path.

UI29 `quest_tracking_02` records both actual toggle requests, both forwarded
native refreshes and both modern replies. Guard Thomas's exact visible GUID has
native status 4 and modern status 64 in both replies. Reviewed enabled screenshots
show the overhead exclamation mark; the disabled screenshot shows none. Quest
history, inventory, money, tracking and staged pose are restored. This qualifies
one eligible trivial creature, not other eligibility categories, game-object
markers, minimap pins or navigation.

The adapter passes eight focused ASan/UBSan checks. The first full suite had
724 passes and one stale checklist assertion expecting now-qualified reward
items to remain pending; its unchanged JUnit receipt is retained. Updating that
coverage guard yields 725 passes. An initial C++ helper used `Value` instead of
`Array` for GUID indexing and was corrected before deployment.

The first deployment precheck found the scout at character selection and stopped
before restarting the bridge. Reviewed private-channel reentry restored its
saved public baseline; the second deployment reconnected both clients with
observer v37 and their original resources, gear, groups and profiles. The deployed
tracked bridge is retained with SHA-256
`a2209756710419b1824a5503fdce8b5683973e8ca8a14792d567a32d1118fac4`.

## Reputation reads and watched-field repair

Observer v38 adds an eight-row public faction page and stock checkbox/watch-bar
reads. The installed Classic and Cata reputation Lua/XML files and Cata TOC are
pinned from strictly local build-60895 CASC reads, with paths and SHA-256 records.
Reference files retain their full hierarchy so similarly named Classic/Cata
sources cannot overwrite each other.

`reputation_read_01` stopped at an oracle assumption that every faction DBC row
must be saved. Native `ReputationMgr` replaces repeated reputation-list indexes
in ascending faction ID order, leaving two superseded placeholder IDs without
saved state. The corrected reader follows those effective indexes. The failed
trial and exact native restoration are retained.

`reputation_read_02` verifies all ten displayed faction standings and native
at-war/inactive flags. It combines the native racial/class base with saved
standing offsets rather than treating an offset as the public total. Ordinary
Stormwind selection shows 4165 and a visible detail panel; native reputation,
inventory and money are unchanged.

That read also exposes an independent defect: native watched index `0xffffffff`
means none, while the client reported Bloodsail Buccaneers, index zero. The bridge
had omitted `ActivePlayerData.WatchedFactionIndex` from creation and owner updates.
`reputation_fields.cpp` now preserves the signed `-1` sentinel and bounded native
indexes, including explicit zero. Sparse owner deltas use pinned group 70 and
scalar 97; visible peers never receive the owner's field.

The initial watched-field candidate passed 731 full regression checks and 19
focused checks under ASan/UBSan. Those assertions mirrored an incorrect gate:
bit 96 is `LastWeekRank`, while scalar 97 is nested under gate 70. The live
`reputation_controls_01` trial exposed this: native watch became Stormwind index
19 while the public watch/bar remained absent. Its cleanup failed as well.
The first regression runs also retained one failed dispatch regression
whose test setup omitted the required empty game-object list (730/1 full and
18/1 focused); the complete test setup passed. That initial bridge SHA-256 is
`31903115e0cd13cce0c6eaa3fc0578bd17fba61b9ff51a755b450259cddc6322`,
source digest
`2da576cade666a0ff30d0d0e149c7f1a1983ce076ce20e1afa551a470a01cff3`.

The corrected watched delta emits both gate 70 and scalar 97. A source audit
also repairs glyph-enable scalar 127 under gate 102, including that group's
unconditional absent `PetStable` presence bit. Glyph-slot arrays retain their
separate gate 1410; a live glyph-enable delta remains unqualified.

The correction passes 731 full regression checks and 22 focused ASan/UBSan
checks. One sanitizer invocation named a nonexistent test file and ran no tests;
that JUnit result is retained alongside the successful corrected invocation.
The optimized bridge SHA-256 is
`3c48929324ceab8696f8597153fd808cb9c1b275ed7d3fa999e7a8bfbcb6d3e3`,
source digest
`5238de8ccb39e8f6677855fa4a932a48b8dde5ae8388a086df773e38d7c65a82`.
Both observer-v38 clients reconnect with original resources, equipment, groups
and profiles and the same native worldserver lifetime.

`reputation_watch_recovery_01` binds the closed failed trial by SHA-256, actor
and native/client lifetime. It verifies the only native mutation is watch index
19, then uses the stock checkbox to restore the source sentinel and public bar.
All faction rows, inventory and money are restored. `reputation_controls_02`
then stops at the stock detail toggle: clicking the already-selected faction
hides its detail. No native state changes. The runner now tests that close
explicitly before reopening in the next trial.

`reputation_controls_03` closes successfully. Stock watch show/hide preserves
the exact native Stormwind index 19 and total 4165. The public bar shows
1165/6000, with reviewed screenshots showing green progress when watched and
an empty bar after hiding it. Alliance collapse/expand hides/restores the exact
child identities. All faction rows, inventory, money and public catalog are
restored. `reputation_watch_visual_review.json` binds the reviewed source
screenshots and action-bar crops by digest.

The initial inactive trial changes only Stormwind's native inactive flag but
stops because the collapsed destination clears selection and hides detail.
`reputation_inactive_recovery_01` binds that failed source, folds Alliance,
expands Inactive, reselects Stormwind and unchecks the stock control. Native
reputation, public catalog, inventory and money are restored exactly.
The next trial's already-expanded destination instead retains selection at its
new index; its too-strict selection oracle fails, while ordinary cleanup restores
every baseline. The runner now validates either the correct updated selection
or a cleared/hidden detail, then independently reselects and verifies the inactive
faction. `reputation_inactive_03` closes successfully: ordinary move, destination
navigation, reselected checked detail and restore pass, with the complete native
reputation, public catalog, inventory and money baseline restored.

No eligible displayed non-header faction currently permits an at-war toggle.
The next ordinary-combat trial uses an existing Bloodsail Raider and its native
positive Booty Bay/negative Bloodsail reward definition, without a reputation
grant or kill command. It stages only pose and retains earned standings.
Watched-faction reload and earned standing trials have separate runners and
remain unqualified until their live evidence closes.

The closed UI29 batch is synchronized through
[`442_interactions_20261003_30.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc),
archive SHA-256
`5c050a68a2afd179879f74e697054d76adce27c6a77563bb67d425ec19f7f16e`.
Five archived receipt/review digests and 83 distinct action-frame digests are
verified before adding six qualified operations. The checklist now has 220
qualified fixture variants among 916 operation contracts; eight regeneration
guards pass. Other variants and whole-game coverage remain open.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_reputation --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/reputation_read_01
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_reputation --controls --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/reputation_controls_01
```

Only the standalone bridge and read-only observer change. Native worldserver
PID 3428101, start ticks 15075252 and binary SHA-256
`2882faddd8df9214e634643e821b35c56d464f0470b0fdaaeed1b5b7d3a2ab5a`
remain unchanged. Other reputation mutations, persistence and remaining player
interaction families still need their own evidence.

## UI30 persistence, earned standings and At War

`reputation_persist_01` passes watched Stormwind across an ordinary `/reload`,
then restores the original no-watch sentinel. Native/public total 4165 and
bar progress 1165/6000 agree. Full session persistence remains a separate scope.

`reputation_combat_01` earns +5 Booty Bay, -22 Bloodsail and +2 for each other
goblin faction through ordinary melee on an existing Bloodsail Raider. Its
initial death oracle fails because the stock client deselects the dead victim;
native exact-victim health zero and death/deselection packets are retained in
`reputation_combat_oracle_review.json`. The corrected runner follows that exact
victim after deselection. The failed receipt remains failed. Its next retry
stalls on a zone-loading screen before sending target or attack inputs; native
pose and all starting resources are restored. Earned standings are retained.

A primary-only restart then stalls before sending player login. Process
diagnostics include a waiting VKD3D graphics queue; the DirectX 11 retry enters
successfully. `d3d11_recovery_review.json` verifies D3D11 loaded, D3D12 absent,
the complete native baseline preserved and unchanged bridge/worldserver
lifetimes. This supports the recorded recovery, without establishing that all
loading stalls share that cause.

`earned_reputation_read_01` verifies all public/native standings, including
Booty Bay 505 and Bloodsail -6522, but fails inspecting Stormwind because the
newly visible factions push it below the viewport. The harness now identifies
the ordered visible catalog slice, uses normal scrollbar buttons to reveal
the selected row, and restores its original viewport. The failure is retained.

`reputation_atwar_01` finds eligible Booty Bay, but its ordinary At War click
disconnects with bridge error `truncated value`. Native flags remain 65.
`reputation_atwar_recovery_01` restores its source public catalog through the
stock Alliance header and verifies exact native reputation and inventory/money.
The pinned [CharacterPackets.h](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/CharacterPackets.h#L703)
declares uint16 At War indexes, while inactive and watch requests use uint32.
The bridge now widens those two-byte indexes to native uint32 and retains their
bounded public request traces. Watch and inactive formats remain separate.
The test formerly constructed the same incorrect four-byte input; its corrected
source-bound case rejects truncation, extra bytes and out-of-range indexes.

The corrected optimized and sanitizer builds share source digest
`2ebb4ac72d18bc0ba5defe5218d1d9bbf6f0c349c6081bb0b39083c3dd97beec`.
Optimized binary SHA-256 is
`043b0f3dcec4a3d55e91c3f1d945a605a86675dd57b5c6c159429b1a26718b62`.
The full suite passes 731 checks and 19 focused ASan/UBSan checks pass. The
first commands failed collection (112/2 import errors) because direct `pytest`
omitted the repository import path; both failed XML results are retained.
The corrected commands use `python -m pytest` and run the same requested suites.
Live corrected At War, earned-kill qualification and UI30 checkpointing remain
open until their own receipts and archived frame reviews pass.
