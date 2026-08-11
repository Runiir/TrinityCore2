# Chimaeron — Phase 0 research contract (Cataclysm Classic 4.4.2)

This is a sourced planning dossier for Blackwing Descent's Chimaeron encounter in 10-player normal/heroic and 25-player normal/heroic. It is not live-validation evidence. “Guide-reported” values come from current Cataclysm Classic strategy pages; “repository baseline” describes this checkout's C++ and historical SQL and must not be silently promoted to Classic retail truth.

## Bot-safe encounter contract

- Activate Bile-O-Tron through Pip/Finkle before the pull. While its mixture is active, heal every player above 10,000 HP; the aura absorbs lethal damage down to 1 HP only when the target is above that threshold.
- During the ordinary phase, keep raid members at least 6 yards apart for Caustic Slime's hit-reduction debuff. Assign a tank/taunt exchange for Break and Double Attack; the Double Attack soaker must be healed to full, while the Break tank generally only needs the 10,000 floor while the mixture is active.
- Massacre is a 1,000,000-damage raid hit. Restore the entire raid above 10,000 before it lands. When Systems Failure takes the Bile-O-Tron offline, collapse within 6 yards to split Slime, rotate raid cooldowns, and continue healing through the offline window; spread again after the next Massacre and reapplication of the mixture.
- At 20%, stop treating the fight as a healing-floor phase: Mortality reduces healing received by 99%, increases Chimaeron's damage taken by 10%, and makes him immune to taunt. Preserve defensive cooldowns, kite/rotate threat as needed, and burn.
- Heroic only: Nefarius casts Shadow Whip when Systems Failure starts, interrupting the Feud behavior so Chimaeron resumes melee during the offline window, and applies Mocking Shadows in phase two. Exact retail spell timing is not asserted without live validation.

## Difficulty matrix

Wowhead reports the following boss health. The current repository chooses Slime targets by raid size (2 for 10-player, 4 for 25-player), while current Wowhead/Icy prose describes 2 normal targets and 4 heroic targets. That normal/heroic-versus-size conflict is explicit below and remains unresolved for Classic 4.4.2.

| Mode | Guide-reported health | Repository target rule | Mode-specific delta |
|---|---:|---|---|
| 10N | 25.9M | 2 random targets; current victim removed | Bile-O-Tron remains through normal Feud; no Nefarius add |
| 10H | 36.2M | 2 random targets; current victim removed | Shadow Whip ends/interrupts Feud behavior; Mocking Shadows in phase two |
| 25N | 90.6M | 4 random targets; current victim removed | Bile-O-Tron remains through normal Feud; no Nefarius add |
| 25H | 126.8M | 4 random targets; current victim removed | Shadow Whip ends/interrupts Feud behavior; Mocking Shadows in phase two |

The guide target rule is reported as “2 normal/4 heroic”; repository evidence is “2 10-player/4 25-player.” Do not interpolate an authoritative Classic mode table until this is validated.

## Mechanic evidence

The current Wowhead and Icy Veins Cataclysm Classic guides independently report the core sequence: Bile-O-Tron mixture and a 10,000 HP floor, Break and Double Attack tank handling, approximately 5/10/15/20/30-second events, 6-yard Slime spacing/stacking, Systems Failure/Feud, a 20% Mortality burn, and heroic Nefarius actions. Warcraft Tavern independently confirms the qualitative encounter but omits a heroic-specific Shadow Whip description in the fetched result. Repository confirmation exists for the exact target filter, event scheduling, random Bile-O-Tron knockout chance, phase transition, hotfix attack reset, heroic actions, reset cleanup, and completion credit.

Guide-reported values requiring caution:

- Wowhead reports boss health 25.9M (10N), 36.2M (10H), 90.6M (25N), and 126.8M (25H); these are not verified against a current 4.4.2 SQL/DBC snapshot here.
- Wowhead reports Caustic Slime every 5 seconds, 270k Nature damage split within 6 yards, two random targets and four on heroic, with a -75% hit chance effect for 2 seconds. Icy Veins reports 270,000 and the same target/timer wording; its ability table gives 270,480. The repository uses raid-size selection and removes only the boss's current victim, so the retail target exclusion remains unresolved.
- Break is reported as +25% physical damage taken and -15% healing done per stack for 1 minute, up to four stacks/+100% physical damage. Current Wowhead says roughly 15–20 seconds; Icy says 20 seconds; the repository starts at 5 seconds and repeats at 15 seconds, then reschedules to 11 seconds after Massacre.
- Double Attack is reported roughly every 10 seconds; Icy's current strategy says every 10 seconds, while the repository starts at 5 seconds, repeats at 15 seconds, and reschedules to 11 seconds after Massacre. The repository also removes the Double Attack aura and resets the melee cycle after every successful Massacre, matching an official historical hotfix comment.
- Massacre is reported approximately every 30 seconds and 1,000,000 physical damage to the raid; the repository first schedules it at 26 seconds and repeats at 30 seconds. It is only scheduled in phase one.
- Systems Failure is reported approximately every minute, with the Bile-O-Tron offline for 26 seconds (Warcraft Tavern says 30 seconds). The repository's Massacre knockout chance begins at 40%, rises by 20 percentage points after each miss, and resets to 40% after a knockout; Reroute Power's exact spell duration is in un-audited spell data.
- Normal Feud is reported as roughly 30 seconds without melee attacks while Slime continues. Heroic Shadow Whip interrupts the Feud behavior, but the exact time from knockout to whip and whether the aura is removed by spell interrupt are unresolved without spell data/live evidence.
- At 20%, current guides report no Caustic Slime, Break, or Massacre; Double Attack continues. Mortality makes healing ineffective (99% reduction), makes Chimaeron immune to taunt, and increases damage taken by 10%. The repository transitions below 20%, applies two Mortality spells, and schedules an immediate Double Attack in phase two.
- Heroic Mocking Shadows is reported at 2,000 Shadow damage per second to all players. Repository Nefarius schedules it immediately when Chimaeron enters phase two; its aura duration is not in the audited C++.

## Timer and random ledger (not live-validated)

| Event | Current strategy reports | Repository baseline | Status |
|---|---|---|---|
| Caustic Slime | every 5s | first at 5s; repeats 5s; rescheduled +19s after Massacre | target/scaling conflict; cadence mixed |
| Break | roughly 15–20s (Wowhead), 20s (Icy) | first 5s; repeats 15s; rescheduled +11s after Massacre | mixed; live timing unresolved |
| Double Attack | roughly 10s | first 5s; repeats 15s; rescheduled +11s after Massacre; phase-two event +1ms | mixed; live timing unresolved |
| Massacre | roughly 30s | first 26s; repeats 30s | mixed; live timing unresolved |
| Bile-O-Tron outage | every minute; offline 26s (guides) | knockout only on successful Massacre roll; `Reroute Power` spell duration not in C++ | random/timing unresolved |
| Feud | 30s normal; begins after knockout | aura starts Feud; heroic asks Nefarius to cast Shadow Whip | aura/heroic timing unresolved |
| Finkle wake sequence | boss wakes shortly after activation | Snort +6s, Grunt +6s, Wake +11s (approximately 23s after the action) | repository baseline |
| Heroic Mocking Shadows | at 20%, 2,000 Shadow per second | Nefarius schedules cast +1ms after phase-two action | aura duration/live cadence unresolved |

## Reset, completion, and credit behavior

- `Reset()` calls BossAI reset and returns the event map to the asleep phase. The method does not explicitly reinitialize the helper chance/player-death/Feud fields, so a post-evade field reset is a repository fidelity question. On evade, the script disengages the encounter, removes Chimaeron auras, despawns Bile-O-Tron and Finkle with a 30-second delay, despawns heroic Nefarius, and despawns the boss at evade. Retail lockout/reset semantics are not asserted.
- On death, the script calls `BossAI::_JustDied()`, disengages the frame, removes boss auras, schedules Bile-O-Tron shutdown after 6 seconds, asks Finkle to speak after 6 seconds, and on heroic tells Nefarius to remove auras/talk/teleport. The instance sends generic Nefarius the `DATA_BOSS_DEFEATED` notification on `DONE`; this is repository progression behavior, not a retail loot assertion.
- The loader declares/invokes `AddSC_boss_chimaeron`. The instance maps boss 43296 to `DATA_CHIMAERON`, Bile-O-Tron 44418 and Finkle 44202 to encounter data, and historical SQL maps difficulty entries 47774–47776 to Chimaeron. The TDB snapshot is 4.3.4-era and is not proof of current 4.4.2 tuning.

## Strong sources and unresolved blockers

- Wowhead, “Chimaeron Strategy Guide — Blackwing Descent Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: https://www.wowhead.com/cata/guide/raids/blackwing-descent/chimaeron-strategy
- Icy Veins, “Chimaeron Encounter Guide: Strategy, Abilities, Loot,” Abide, updated 2024-07-29: https://www.icy-veins.com/cataclysm-classic/chimaeron-encounter-guide-strategy-abilities-loot
- Warcraft Tavern, “Chimaeron Raid Guide,” Passion, publication date not exposed by the fetched page/search result (retrieved 2026-08-11): https://www.warcrafttavern.com/cataclysm/guides/chimaeron-raid-guide/
- Blizzard, “Cataclysm Hotfixes — Updated Jan. 26” (historical source: attack-cycle reset and Double Attack removal after Massacre; Classic carryover not independently proven): https://worldofwarcraft.blizzard.com/en-us/news/1232869
- Blizzard, “Patch 4.0.6 Hotfixes and 4.0.6a Changes — Last update: March 29” (historical source: Caustic Slime target exclusion/related Chimaeron fixes): https://worldofwarcraft.blizzard.com/en-gb/news/9981073/patch-406-hotfixes-and-406a-changes-last-update-march-29
- Blizzard forum, Kaivax, “World of Warcraft: Cataclysm Classic—Patch 4.4.2 Notes,” 2025-02-18: https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030

Material blockers: exact 4.4.2 build and Chimaeron hotfix cutoff; whether target count is difficulty- or raid-size-based in Classic; Break-target exclusion for Slime; Bile-O-Tron knockout probability and Reroute duration; heroic Feud/Shadow Whip timing; spell-data durations for mixture, Feud, Reroute, Mortality, and Mocking Shadows; exact mode damage/scaling; helper-field reset after evade; and retail reset/loot/achievement behavior. These remain `unresolved`/`fidelity_blocked` in the machine-readable files.
