# Longer Magmaw WCL references

Retrieved September 12, 2026. These are historical observations from before the pinned 4.4.2 client era. They supply coverage missing from the 70-second kill, but do not establish unchanged behavior across patches.

| Report | Mode | Displayed kill | Date | Coverage inspected |
| --- | --- | --- | --- | --- |
| [FhcbnAmN9v7kr1VP, fight 3](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3) | 25H | 4:38 | 2024-11-03 | Two Mangles, two Massive Crashes, nine Spew tick sequences, seven construct Ignitions, one full Armor lifetime |
| [MxFq7TRbvnjGY1hJ, fight 22](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22) | 10N | 2:11 | 2024-10-28 | One Mangle and subsequent Armor application |

Both reports were uploaded by Amaraaa. The displayed durations are rounded WCL headers, not exact DPS denominators. The 25H summary shows 2 tanks, 5 healers, 18 DPS and average item level 368. It is not a matched performance baseline for our 10N roster.

## Direct observations

The [25H Mangle table](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=auras&spells=debuffs&view=events&ability=89773) shows:

- Catamara: applied 90.522s, removed 118.048s.
- Gillhart: applied 186.080s, removed 215.201s.

The application interval is 95.558s. The held durations are 27.526s and 29.121s. These support a roughly 95-second repeat prediction for this report, without proving an exact deadline or player-independent release duration.

The [25H Armor table](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=auras&spells=debuffs&view=events&ability=78199) shows Catamara gaining Armor at 118.049s and losing it at 208.041s, a measured 89.992s lifetime. Gillhart gains it at 215.202s. Each application follows Mangle removal by 1ms.

The [10N Mangle table](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22&type=auras&spells=debuffs&view=events&ability=89773) shows Wongelrainer gaining Mangle at 90.597s and losing it at 114.896s. The [Armor table](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22&type=auras&spells=debuffs&view=events&ability=78199) shows Armor applied at the same displayed 114.896s. The fight ends before its expiry.

In the [25H cast events](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=casts&view=events&hostility=1), Massive Crash 88253 occurs at 99.595s and 195.151s. Spew 77690 appears in nine groups of three casts approximately 2s apart. The first triggers occur at 21.666, 49.181, 79.920, 110.715, 152.826, 183.587, 207.881, 249.887 and 274.171s. Grouping these as periodic sequences is a cadence inference; the table does not expose parent-wrapper starts. Construct Ignition 92118 occurs at 30.650s, then about every 35.5s across seven construct instances. Ignition is not the summon event itself.

## A focused native discrepancy

At source `4b0895871a`, `boss_magmaw.cpp:PassengerBoarded` applies Sweltering Armor in the boarding branch alongside Mangle. Both inspected WCL reports instead place Armor application at Mangle removal. The previous research established the 90s duration but missed this application anchor.

This is an evidence-backed repair candidate, not a measured cause of the current DPS loss. Confirm target-era compatibility, then hand encounter implementation this bounded change: apply Armor on the externally supported gameplay release paths, with explicit handling for successful hooks, timeout, wipe/reset/death and unrelated passenger removal. The follow-up below shows why successful hooks alone cannot be assumed. Do not move it blindly into every ejection callback. A production-path fixture must distinguish boarding, successful release and cleanup, followed by an attributable live application/removal trace. No combat code was changed in this research pass.

## Coverage limits

The [enemy buff table](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=auras&view=events&hostility=1&ability=79011) has a Point of Vulnerability application at 90.558s, near Mangle application. That is not a measured head-targetability window. The corresponding enemy debuff view and the selected 77907 impale debuff view had no rows. Those empty views do not prove missing mechanics. Exact head appearance/return still needs attack/replay evidence; do not label the gap resolved because the kill is longer.

No new damage distribution, same-era tuning baseline or native first-Spew explanation is claimed. The selected 47 event records and derived intervals are retained through `artifacts/cata_raid_program/magmaw_longer_wcl_20260912.tar.gz.dvc`. The original canary archive remains unchanged.

## Follow-up: completion inventory and stronger references

The ledger now has a `research_completion` inventory with 15 mechanic/lifecycle questions. It separates pinned client values, observed historical combat and verified native behavior. Full fidelity remains blocked. Resume with:

```bash
pixi run python -m tools.raid_program.encounter_research_view experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_ledger_v1.json
```

Add `--key shadow_breath` (or another emitted key) to inspect one claim and its sources. This projects the existing ledger, without another status database.

### Client values by mode

The new extraction follows 51 requested spell IDs to 65 referenced IDs, retaining 145 effect rows. Nine requested/referenced IDs lack names/effects in the pinned build; legacy variant IDs must not be silently substituted for Classic difficulty rows. The pinned [Difficulty table](https://wago.tools/db2/Difficulty/csv?build=4.4.2.59185) identifies 3/4/5/6 as 10N/25N/10H/25H, with explicit fallback links. Each derived value retains the actual effect row and fallback path.

These are inclusive client base rolls before defenses, encounter modifiers or server hotfixes. They are not accepted native tuning values.

| Damage event | 10N | 25N | 10H | 25H |
| --- | ---: | ---: | ---: | ---: |
| Spit 78359 | 30,625–39,375 | 30,625–39,375 | 35,000–45,000 | 39,375–50,625 |
| Spew 77690 | 14,800–17,200 | 14,800–17,200 | 20,812–24,187 | 24,050–27,950 |
| Pillar 77971 | 69,375–80,625 | 69,375–80,625 | 115,625–134,375 | 115,625–134,375 |
| Mangle periodic 89773 | 110,464–128,377 | 132,557–154,052 | 132,557–154,052 | 154,649–179,728 |
| Crash damage 88287 | 81,400–94,600 | 81,400–94,600 | 157,250–182,750 | 157,250–182,750 |
| Shadow Breath 92173 | Inapplicable | Inapplicable | 20,812–24,187 | 24,975–29,025 |
| Inferno damage 92154 | Inapplicable | Inapplicable | 50,875–59,125 | 69,375–80,625 |

Infection and Vomit rows are also retained in `client_mode_rolls.json`. Mangle's initial weapon-percent hit is separate from its periodic damage. Armageddon's damage child has a nonzero coefficient, so it was excluded from simple base-roll comparison rather than treated as a flat amount.

Both hook auras, 77917 and 77941, reference a 3,000ms duration. The native script requires both auras on the same target. Wowhead's advice to coordinate within one second is stricter than the client expiry, not an established one-second server cutoff. The exact arrival/expiry boundary still needs verification.

The parasite chain is now explicit: 77973 has a 2,500ms duration and references 77969 every 300ms; 77969 summons NPC 41806. Vomit references 78936, which summons NPC 42321. This identifies the two parasite types. Tick arithmetic alone does not establish the observed spawn count.

### What the longer log actually establishes

[Shadow Breath incoming events](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=damage-taken&ability=92173&view=events&options=4098) contain 47 player rows. The first eight explicit U estimates range from 25,159 to 28,463; all fit the 25H client range. These are WCL unmitigated estimates, not logged base rolls. The enemy cast view for the same spell is empty despite landed damage. First damage is at 259.487s. This does not establish cast cadence or distinguish primary targets from splash recipients.

The two heads share a name but have different identities: report actor 61 is NPC 42347, while actor 72 is NPC 48270. After excluding mirrored spell 79010, [warrior Shîroh's attacks on actor 61](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=damage-taken&hostility=1&source=61&target=27&view=events) contain melee clusters at 120.340–143.925s and 217.957–240.156s. His first subsequent body swings are 165.357s and 256.025s. Rend still ticks on the head at 159.273s and 250.020s. These bound that player's activity; they do not measure exact targetability or reaction delay. Actor 72 instead receives the grabbed tank's attacks and pet cleave during Mangle.

At 215.088s, [Mangled Lifeless damages Gillhart](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=damage-taken&ability=78362&view=events&options=4098), 113ms before his Mangle removal. He is absent from the report's six listed player deaths. A timeout release is plausible, but not directly logged here. The earlier Armor handoff must therefore distinguish release causes, rather than describe both removals as successful hooks.

Native Nefarian keeps Inferno scheduled after the 30% action. DBM cancels its prediction at the phase yell. The current longer kill cannot settle that difference: its final construct Ignition is at 244.255s, and its first Breath damage occurs at 259.487s, too late to observe a full subsequent Inferno interval before death. The next useful heroic reference needs more than 36 seconds below 30%, with HP/phase and summon evidence.

### Version limits and the next work

[Blizzard's June 13, 2024 hotfix](https://news.blizzard.com/en-us/article/24066687/hotfixes-july-22-2024) corrected Magmaw falling backwards during Impale and preventing damage. Both longer logs postdate it. The [4.4.2 announcement](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030) and [February hotfix archive](https://news.blizzard.com/en-us/article/24148555/hotfixes-february-21-2025) contain no Magmaw entry. Those bounded checks do not prove complete carryover or exclude undocumented changes.

The next research targets are exact head transitions, actual summon counts, remaining heroic behavior/damage, mode-specific health, and reset/credit behavior. Native first-Spew loss still requires cast/absorb telemetry. No new combat patch or performance recovery is claimed.

New selected observations, extraction identities and comparisons are published separately through `artifacts/cata_raid_program/magmaw_research_closure_20260912.tar.gz.dvc`. The prior evidence archives remain immutable.
