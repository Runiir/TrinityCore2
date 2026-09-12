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

This is an evidence-backed repair candidate, not a measured cause of the current DPS loss. Confirm target-era compatibility, then hand encounter implementation this bounded change: apply Armor on the intended successful Mangle release path, with explicit handling for wipe/reset/death and unrelated passenger removal. Do not move it blindly into every ejection callback. A production-path fixture must distinguish boarding, successful release and cleanup, followed by an attributable live application/removal trace. No combat code was changed in this research pass.

## Coverage limits

The [enemy buff table](https://classic.warcraftlogs.com/reports/FhcbnAmN9v7kr1VP?fight=3&type=auras&view=events&hostility=1&ability=79011) has a Point of Vulnerability application at 90.558s, near Mangle application. That is not a measured head-targetability window. The corresponding enemy debuff view and the selected 77907 impale debuff view had no rows. Those empty views do not prove missing mechanics. Exact head appearance/return still needs attack/replay evidence; do not label the gap resolved because the kill is longer.

No new damage distribution, same-era tuning baseline or native first-Spew explanation is claimed. The selected 47 event records and derived intervals are retained through `artifacts/cata_raid_program/magmaw_longer_wcl_20260912.tar.gz.dvc`. The original canary archive remains unchanged.
