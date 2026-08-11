# Magmaw — Phase 0 research contract (Cataclysm Classic 4.4.2)

This is a sourced planning dossier for Blackwing Descent's Magmaw encounter in 10-player normal/heroic and 25-player normal/heroic. It is not live-validation evidence. Values called “guide-reported” are observations from the current 4.4.2-labelled guides; values called “repository baseline” describe this checkout's C++ implementation and must not be silently promoted to Classic retail truth.

## Bot-safe encounter contract

- Magmaw is immobile and is fought from melee range. Keep the tank at the boss and keep the rest of the raid out of the pillar marker; a tank out of melee causes the repository AI to cast Molten Tantrum instead of Magma Spit.
- Pillar of Flame selects a non-vehicle target and prefers a target more than 15 yards from Magmaw when one exists. Move out of the impact area and control the Lava Parasites; do not infer an exact parasite count from this repository.
- Mangle is a tank event in the current implementation and in both current strategy guides. During the Mangle/Crash sequence, stop normal damage, avoid Massive Crash, put one player on each available pincer, and apply both hooks to the same target. The two-hook condition is repository-confirmed; exact retail interaction tolerance is guide-reported and unresolved below.
- A successful impale exposes the head for a 30-second, +100% damage window in both current guides. Retarget the exposed head, then expect the ordinary phase to resume. The code also applies Sweltering Armor to the Mangle passenger and removes it when that passenger leaves; duration is a spell-data question, not established by the script.
- Heroic only: Nefarian is summoned at engage, casts Blazing Inferno/construct events, and starts Shadow Breath when Magmaw is damaged below 30%. Normal modes have no Nefarian add in the repository.

## Difficulty matrix

The health figures below are reported by the current Wowhead Cata guide and are not present as verified 4.4.2 data in this checkout. The Magma Spit counts are repository-confirmed and agree with the size-based reading in the current Icy Veins guide; Wowhead's paragraph uses ambiguous “in heroic difficulty” wording and is recorded as a conflict in the ledger.

| Mode | Guide-reported health | Repository/strategy target rule | Mode-specific phase delta |
|---|---:|---|---|
| 10N | 33.5M | Magma Spit selects 3; no heroic Nefarian | Normal Mangle → Crash → hooks/head loop |
| 10H | 39.2M | Magma Spit selects 3; heroic Nefarian | Blazing Inferno, Bone Constructs, Shadow Breath below 30% |
| 25N | 101.4M | Magma Spit selects 8; no heroic Nefarian | Normal Mangle → Crash → hooks/head loop |
| 25H | 120M | Magma Spit selects 8; heroic Nefarian | Blazing Inferno, Bone Constructs, Shadow Breath below 30% |

No source audited here supplies a reliable, complete 10N/10H/25N/25H table for every damage, health, spawn, or timer value. Do not interpolate 10-to-25 or normal-to-heroic scaling.

## Mechanic evidence

The current Wowhead and Icy Veins Cataclysm Classic guides independently report the core sequence: approximately 5-second Magma Spit, approximately 20-second Lava Spew over 6 seconds, approximately 30-second Pillar, approximately 90-second Mangle, Crash, two hook users, a 30-second exposed-head vulnerability window, and heroic Nefarian. Warcraft Tavern independently reports the same qualitative sequence, but conflicts on hook-user count and armor duration. Repository confirmation is cited for target filtering, hooks, phase transitions, reset cleanup, and difficulty gating.

Guide-reported values requiring caution:

- Wowhead reports Magma Spit at roughly 30k normal/45k heroic per hit, Lava Spew at roughly 16k normal/27k heroic every 2 seconds for 6 seconds, Pillar at roughly 75k normal/120k heroic within 5 yards, Infection at 25k every 2 seconds for 10 seconds, Vomit at 20k normal/45k heroic within 8 yards, Mangle at roughly 165k every 2 seconds for 30 seconds, and Crash at roughly 100k normal/170k heroic plus a 3-second stun.
- Wowhead also reports Molten Tantrum as +100% damage every 1.5 seconds, stacking 10 times (up to +1000%). Its heroic Inferno report gives a 4-second meteor delay, roughly 75k within 4 yards, and fire trails lasting 50 seconds at roughly 55k per hit. These are guide values, not mode-complete tuning.
- The same Wowhead page's ability table instead lists ranges of 39,375–50,625 (Spit), 14,800–17,200 (Spew), 29,250–30,750 (Pillar), 154,649–179,728 (Mangle), and 157,250–182,750 (Crash), without a dependable mode mapping. The Crash narrative/table conflict is unresolved; neither range is a bot contract.
- Current Wowhead/Icy report up to two players mounting and both hooks being required; old Icy material and the Warcraft Tavern strategy text mention three melee players. The repository has exactly two pincer body parts and requires both hook auras, so “two” is the implementation contract while retail player-count/tolerance remains unresolved.
- Current Wowhead/Icy report Sweltering Armor for 1 minute; Warcraft Tavern says 2 minutes. Repository confirms application/removal but not duration. Treat duration as unresolved.

## Timer ledger (not live-validated)

| Event | Current strategy reports | Repository baseline | Status |
|---|---|---|---|
| Magma Spit | roughly every 5 seconds | first at 6s; repeats every 6s for four projectiles | mixed; live Classic timing unresolved |
| Lava Spew | roughly every 20 seconds, 6-second channel | first at 19s; repeats every 24s; reschedules projectile in 6s | mixed; live Classic timing unresolved |
| Pillar | roughly every 30 seconds; Wowhead says 4-second impact | emitted after the fourth projectile; pillar despawns in 7s; exact live cadence unresolved | repository-only cadence |
| Mangle | roughly every 90 seconds; 30-second damage window | first at 90s, repeats every 95s; Mangle target event, Crash preparation +3.5s and Crash +5s | mixed; live Classic timing unresolved |
| Head | vulnerability roughly 30 seconds | impale self +1s; head shown +5s; finish event +3s after cover action | mixed; live window source-only |
| Heroic Blazing Inferno | roughly every 35 seconds | first at 27s, repeats every 36s | mixed; live Classic timing unresolved |
| Heroic Shadow Breath | at 30%, approximately every 1 second | below 30% trigger schedules first after 9s, then repeats every 1.2s | mixed; target/cadence unresolved |

These implementation intervals are useful for diagnosing this checkout, not proof of a 4.4.2 retail timer. The repository's event loop also cancels Spit/Spew during Mangle and immediately schedules Lava Spew after mounting ends.

## Reset, completion, and credit behavior

- On evade, the script marks Magmaw `FAIL`, ejects the boss and both pincers, removes Parasite Infection/Vomit from players, despawns the head/summons/Nefarian, and the instance removes Crash dummies and room stalkers. The original Cataclysm hotfix says Lava Parasites should not reset the encounter when they evade; the repository does not implement a parasite-driven reset.
- On death, the script removes parasite auras, disengages the encounter frame, tells heroic Nefarian to finish/despawn, and calls `BossAI::_JustDied()`. The instance's `DONE` transition despawns Crash/room-stalker helpers and notifies generic Nefarius for progression credit. This is repository behavior, not a retail loot/achievement assertion.
- The loader declares and invokes `AddSC_boss_magmaw`; the instance maps creature 41570 to `DATA_MAGMAW`, maps heroic Nefarian 49427 to `DATA_NEFARIAN_MAGMAW`, and ties the inner-chamber door to the Magmaw state. Historical 4.3.4 SQL supplies template/difficulty rows, but no current 4.4.2 SQL snapshot was found.

## Strong sources and unresolved blockers

- Wowhead, “Magmaw Strategy Guide — Blackwing Descent Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: https://www.wowhead.com/cata/guide/raids/blackwing-descent/magmaw-strategy
- Icy Veins, “Magmaw Encounter Guide: Strategy, Abilities, Loot,” Abide, updated 2024-07-29: https://www.icy-veins.com/cataclysm-classic/magmaw-encounter-guide-strategy-abilities-loot
- Warcraft Tavern, “Magmaw Raid Guide,” lettara, publication date not exposed by the fetched page/search result (retrieved 2026-08-11): https://www.warcrafttavern.com/cataclysm/guides/magmaw-raid-guide/
- Blizzard, “Cataclysm Hotfixes — Updated Jan. 26” (original Cataclysm hotfix context; Classic carryover not independently proven): https://worldofwarcraft.blizzard.com/en-us/news/1232869
- Blizzard, “Patch 4.0.6 Hotfixes and 4.0.6a Changes — Last update: March 29” (historical hotfix context): https://worldofwarcraft.blizzard.com/en-gb/news/9981073/patch-406-hotfixes-and-406a-changes-last-update-march-29
- Blizzard forum, Kaivax, “World of Warcraft: Cataclysm Classic—Patch 4.4.2 Notes,” 2025-02-18: https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030

Material blockers: exact 4.4.2 client/build and BWD hotfix cutoff; live timer confirmation in every mode; exact Crash/Pillar/Spit/Spew mode scaling; parasite spawn count; mount count and hook timing tolerance; Sweltering Armor duration; and Shadow Breath splash/cadence. These remain `unresolved`/`fidelity_blocked` in the machine-readable files.
