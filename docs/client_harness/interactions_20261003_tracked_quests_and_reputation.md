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
explicitly before reopening; fresh watch/header trials need their own closure.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_reputation --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/reputation_read_01
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_reputation --controls --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/reputation_controls_01
```

Only the standalone bridge and read-only observer change. Native worldserver
PID 3428101, start ticks 15075252 and binary SHA-256
`2882faddd8df9214e634643e821b35c56d464f0470b0fdaaeed1b5b7d3a2ab5a`
remain unchanged. Other reputation mutations, persistence and remaining player
interaction families still need their own evidence.
