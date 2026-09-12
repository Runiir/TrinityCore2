# Magmaw timing and damage check, 2026-09-12

Scope: Magmaw only. The checked live comparison is 10N. Heroic and 25-player fidelity are not established by a 10N report. The target remains client 4.4.2.59185 enUS with the existing February 20, 2025 hotfix cutoff.

## Queue repair

Native `UpdateAI` checked casting once, then drained every due event. With Spew and Mangle both overdue, Spew could start its two-second cast, Mangle would be rejected by `UnitAI::DoCast` as spell-in-progress, and the AI would still cancel offense and advance the Crash sequence. This is a deterministic queue defect, not a proven cause of the historical DPS decline.

Commit `a4b9ab9bd7` rechecks casting after each dispatched event. Later events stay queued until the cast ends. The existing impaled-phase exception remains because head exposure must progress during impale. Instant spells receive no invented global spacing. Missiles and periodic damage can overlap; the observed report has Magma Spit landing during Lava Spew ticks.

The regression compiles the production UpdateAI body and native EventMap implementation. It stubs actors and cast submission, including the native cast-in-progress rejection. It fails before the patch and passes after it. It also exercises the next update after cast completion, impaled head exposure, and instant-cast dispatch. Independent Sol review approved the native call path and preserved lifecycle. This fixture does not establish actual terrain, spell metadata or boss completion.

## Timer references

The local DBM r254 Magmaw module declares interface 40402 and revision 20241115112135. Its logic matches [pinned upstream DBM](https://raw.githubusercontent.com/DeadlyBossMods/DBM-Cataclysm/4b02efec4552aef3df43c75fb19c6d8c7fdb3e6e/DBM-Raids-Cata/BlackwingDescent/Magmaw.lua), after packaging revision, whitespace and line-ending normalization.

| Mechanic | Prediction and anchor | Interpretation |
| --- | --- | --- |
| Mangle | First 90s; 95s after aura 89773 application | Expected cooldown; 30s target timer |
| Exposed head | 30s after head-exposed emote | Expected window, not aura database duration |
| Pillar | First 30s; 32.5s after aura 78006 | Author gives 30–40s variation |
| Lava Spew | 22s after triggered cast 77690 | First accepted tick, not wrapper cast 77839 |
| Heroic Inferno | First 30s; 35s after summon 92154 | Cancelled by phase-two yell |
| Berserk | 600s from engage | Addon prediction |

DBM's 15s Pillar reset after slump is explicitly a theory. Existing native intervals remain compatibility values where external observations are incomplete. Cast-state leeway is implemented by the existing event queue. No extra random timer range or universal delay was invented.

The [WCL report](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=10&type=casts&view=events&hostility=1) shows Spew triggered casts at 23.036/25.030/27.034 and 50.574/52.627/54.574 seconds. These are two periodic sequences, not six independent wrapper casts. Native first scheduling at 19s plus a 2s wrapper cast and a 2s tick accounts for a first hit near 23s. The observed 27.528s first-hit interval is one interval; it does not establish the server cooldown distribution.

## Damage comparison

The [WCL incoming events](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=10&type=damage-taken&by=ability&options=4098&view=events) retain damage, absorbs and WCL unmitigated estimates separately. The selected 30 rows include every ordinary Spit hit and all Spew hits on the two actors whose displayed damage equals U without displayed mitigation.

| Spell | 4.4.2 client roll | Selected WCL U range | Samples outside range |
| --- | ---: | ---: | ---: |
| Ordinary Magma Spit 78359 | 30,625–39,375 | 30,834–39,329 | 0 of 18 |
| Lava Spew damage 77690 | 14,800–17,200 | 15,084–17,087 | 0 of 12 |

The runtime DBC has matching base/dice rows. Database readback found no `spell_dbc` or `spelleffect_dbc` overrides for these spells. The source scan found no direct numeric corrections for these IDs. No damage adjustment is justified by this comparison. Ordinary Spit 78359 must not be confused with Tantrum Spit 78068, whose base roll differs.

WCL U is an estimate. Sample extrema are not exact distribution endpoints. Gear alone cannot recover temporary defensive effects, resistance or absorbs. Do not tune boss damage to a tank's health loss or treat absent mitigation fields as independently observed zero mitigation. The comparator reports sample compatibility only and requires an explicit effect/difficulty row.

Client data resolves Sweltering Armor 78199 to -50% armor and a 90s duration. Its effective encounter lifetime still depends on native removal. Point of Vulnerability 79010 transfers damage; 79011 contains the +100% modifier. Its indefinite database duration does not contradict a lifecycle-controlled 30s head window.

## Evidence and remaining coverage

Generated inputs, selected WCL rows, exact client table hashes, native DBC/readback, pre/post fixture results, review and validation outputs are published under `artifacts/cata_raid_program/magmaw_fidelity_20260912.tar.gz.dvc`.

This short WCL kill does not cover Mangle, hooks, head return, heroic adds, or heroic/25-player damage. It is also later than the pinned hotfix cutoff. Those gaps remain explicit in the Magmaw ledger. No all-mode or full-raid qualification is claimed.
