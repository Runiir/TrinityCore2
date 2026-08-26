# Magmaw Canary41 entrance-pull handoff

Canary40 proved that the current-standard 10N roster can clear the entrance and Chainwielder and reduce both Drudges below 23% with all ten bots alive. It failed because the old post-Rush tank return moved the fight toward Magmaw and contaminated the next encounter.

## Bounded repair

Commit `c2393bfd57b80a4e5ecd00cc37b78ec3c807b892` keeps the initial native two-tank taunt geometry unchanged. After both assigned tanks receive source-scoped native taunt confirmations, the exact roster switches once to the already frozen-navmesh-proven entrance-side recovery formation. Tanks, healers, DPS, pets, threat, and native Rush behavior remain ordinary runtime behavior. The active selector no longer offers the boss-side combat or navigation anchors after this latch, including after a Rush observation closes.

The repair does not change creature aggro, health, damage, spell ranges, threat, victims, line of sight, or pathing. It does not teleport, resurrect, suppress Magmaw, force a target, or manufacture a clear.

## Source and build evidence

- Focused Drudge/no-cheat tests: `82 passed`
- Wider runtime/workloop source checks before metadata refresh: `355 passed`; two stale active-work-unit assertions were then replaced by this handoff and descriptor
- Luna max read-only review: pass after verifying exact arrival and source-scoped native-taunt invariants
- Largest touched C++ file: `965` lines
- Configure receipt: `/tmp/trinity-magmaw-c2393bfd57-canary41-build.VaMPD5/configure-receipt-v2.json`
- Configure receipt canonical SHA-256: `386642f33d2e7caebbf4bd7245af3a589a0bd1baa4b50fce53d05f85d85065ed`
- Worldserver build receipt: `/tmp/trinity-magmaw-c2393bfd57-canary41-build.VaMPD5/worldserver-build-receipt.json`
- Worldserver build receipt canonical SHA-256: `6d00a392d29292b172a44813ddb21df929520729bd446d69da9893c82f26865f`
- Worldserver binary SHA-256: `c59546e36953c476a8e557e5a52ab808bb40130c397d0d4d078b8e8da23e00fa`
- Build receipt verification: valid, gate-bearing, non-test, source identity stable

## Live gate

Fresh-provision the frozen `blackwing_descent_10n_magmaw_diagnostic` roster and verify readback before starting the exact binary. Run under the completion watchdog, not a fixed timer. Success requires entrance, Chainwielder, Drudges, and Magmaw to clear normally with no contamination, semantic stall, repeated-decision loop, excessive deaths, infrastructure loss, or forbidden assistance. If Canary41 clears, repeat from fresh state as Canary42 before promotion. Publish and remotely verify accepted evidence through DVC, then evict local raw data.

This checkpoint is implementation and build evidence. It is not a live-clear claim.
