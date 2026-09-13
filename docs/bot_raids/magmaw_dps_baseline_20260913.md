# Magmaw DPS comparison references

Reviewed through the connected WCL browser on 2026-09-13. These are measured
reference observations, not a controlled expected-DPS floor. Native comparison
is closed source `ee0504cc0c`, epoch11003006216685852, attempt1, instance2;
132.205 seconds, 213,253.077 originated hostile DPS, one Blood tank, three
healers and six DPS. Its published all-bot review and timeline remain the
native evidence authority.

## Selected closer class reference

[Dragon Soul, report Y8ajQ7dbmKMG1RZy, fight22](https://classic.warcraftlogs.com/reports/Y8ajQ7dbmKMG1RZy?fight=22&type=summary),
created by chani666 on May15,2025, is Magmaw Normal10. WCL displays111.3 seconds,
246,232.7 raid DPS, average item level395.33, no deaths, and **nine participants**:
two tanks, two healers and five DPS. Its roster includes all four of our caster
DPS specs and Blood DK. It has no Hunter, so it cannot establish MM parity.

| Spec / WCL actor | WCL ilvl | WCL DPS | Latest bot DPS |
| --- | ---: | ---: | ---: |
| Balance / Inkar | 401 | 41,029.1 | 30,422.6 |
| Fire / Sethra | 395 | 40,189.9 | 27,935.8 / 30,140.1 |
| Elemental / Roostertours | 399 | 41,866.0 | 35,775.8 |
| Affliction / Næñï | 394 | 40,281.0 | 33,775.4 |
| Blood / Nexry | 393 | 26,152.0 | 16,132.9 |

These columns are unadjusted observations. Do not label their difference a
coefficient error, account for it by an item-level ratio, or impose it as a
passing threshold. Composition, duration, cooldown coverage and tank pressure
differ. Native bots have head exposure; this WCL target table lists Magmaw and
parasites only. That table is not an exact head-targetability observation.

The [target table](https://classic.warcraftlogs.com/reports/Y8ajQ7dbmKMG1RZy?fight=22&type=damage-done&by=target)
shows body26.02m/233,704.2DPS and parasites1.39m/12,528.5DPS. These are rounded
WCL display amounts; they have not been reconstructed with our native damage
accounting rules. The header duration is not an exact millisecond denominator.

Næñï's summary equipment links expose gems and permanent enchant IDs, including
weapon78418/enchant4097; there is no71086 in the displayed equipment list.
The summary reports one combat potion. This permits an actual gear comparison,
not an assumption based on average ilvl. Full aura/cooldown/event normalization
and native effective-stat parity remain outstanding.

## Complementary references

[Sehr erfolgreich, xAhkN2y9YP3KRmnJ fight10](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=10&type=summary),
Amaraaa, June11,2025:70.9 seconds,378,849DPS, average401.40; one Blood tank,
one Restoration Shaman, eight DPS, no deaths. Fire400 does58,173.4;
Affliction403 does49,435.6; Elemental406 does41,299.2; Blood407 does28,446.3.
Both Hunters are **Survival**, not Marksmanship. No Balance is present.
The target table displays only body26.17m/369,013.6DPS and parasites697.4k/
9,835.4DPS. Retain this as a short-fight throughput/action reference. Its raid
DPS is not our composition's required minimum.

[10er WT feat. Wongel, MxFq7TRbvnjGY1hJ fight22](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22&type=damage-done),
Amaraaa, October28,2024:131.1 seconds,205,908DPS, gear357–365 in the displayed
player table. Useful for the longer mechanic cycle, unsuitable as the gear-tier
throughput target. Detailed older mechanic observations remain in
[magmaw_longer_wcl_20260912.md](magmaw_longer_wcl_20260912.md).

## Reproduce selection without broad browsing

Open the retained xAhk report, Compare, select Schlabunsen under similar parses.
Set duration tolerance90s, raid-size difference0, item-level tolerance10 and
lookback1000 days. The search on2026-09-13 returned Næñï at1:51/394ilvl/40,281DPS.
Opening that result produced the comparison against Y8aj report fight22.
Verify the actual roster in Summary: the search's raid-size setting did not
prove ten participants. Read the spec names, potion counts and actual item links.
Use the exact report URL above on future reviews; do not repeat this search
merely to recover known evidence. Search results and availability may change.

## Other losses and next review

Affliction's latest33,775.4DPS is14.11% below nativeff226's39,323.1 at nearly
matched duration/phase lengths. Versus ff, boss damage falls791,230 while add
damage rises33,296. Direct, periodic and pet damage all fall. Drain Soul and
Haunt cadence, execute coverage and pet outcomes are priority comparisons;
the current aggregate does not prove which code caused the loss.

Balance's latest30,422.6 is its best of these native runs, but retained masks
suppress Starfall48505 and Force33831 through
`declarative_area_damage_semantics_forbidden`. The policy gate is observed;
its safe-use contract needs review before changing it. Elemental is within0.56%
of2af and Blood is aboveff/26; neither has a newly proven class defect.

Build a per-spec comparison across this roster before accepting optimization:
gear/native effective stats, phase-specific cast cadence and damage per event,
owner/pet output, DoT coverage, cooldown/potion use, movement and required duties.
Keep the promoted exact WoWSims requests as the class-mechanics reference.
Do not use generic validation-profile `enchanted` flags as the selected raid
loadout authority; inspect the frozen scenario and actual admission inventory.
The new WCL reference improves diagnosis but does not complete controlled parity
or establish an exact maximum-DPS target for every bot.

## Native setup check

`report.json` at `accepted_raid_runtime.admission_receipt.members[*].gear_manifest`
is the equipment authority, with current/admission identity matching for all ten.
Blood and all three healers have zero nonzero permanent `enchant_id` values;
Balance/Fire/Affliction/Elemental have nine each and Hunter ten. Missing item
enchants do not independently prove that a separate temporary/runeforge aura
was absent. This setup difference must be resolved or explicitly retained in
the comparison before claiming an optimized roster.

Reject the generic base-profile inference that Affliction/Elemental were
unenchanted: native head enchant4207 and weapon4097 disprove it. The frozen
all-spec target's `provisioning_bot.profession_equipment` supersedes that base.
Their actual equipped16-item means are407.94/408.31, not the intermediate
profile's409.56/409.24. Blood's mean is407.44. Counting the two-handed weapon
twice gives17-slot means407.29/407.65/407.94 respectively; retain the convention
rather than silently equating these with WCL's displayed average.


## Bounded class findings before the Survival canary

Retained native source ee0504cc0c and the selected WCL actors support these
separate findings. Full compact reviews are included with the next experiment
publication; none changes the immutable ee0504 report.

- Affliction submitted18 long single-target DoTs/Haunt to short-lived parasites
  for only19,553 landed damage from those spells. The first Bane of Doom starts
  at+34.016s. This waste also occurs onff226 and does not establish the cause
  of the14.11% local decline. The Affliction profile also lacks Summon Doomguard;
  WCL source9's guardian contributes416.2k displayed damage. Neither finding
  justifies changing native coefficients.
- Fire30006/30007 submit0/1 Combustions and2/5 instant Pyroblasts; WCL source4
  records2 and12 respectively. Existing aura/proc gates require investigation.
  Mage30006's19.138s fresh-direct-effect gap contains successful Living Bomb
  casts and mandatory movement. A shorter+95.233..100.547s interval retains
  backoff and maximum-range rejection after movement path rejection; native
  body distance47.2094yd is observed. It is not19seconds of complete idleness.
- Blood and all three healers have permanent enchant_id=0 in every admitted
  equipment slot, with current/admitted hashes matching. Their source rows omit
  profession-equipment overrides; the generic profiles are explicitly
  unenchanted. Exact replacement enchant/profession authority must be completed
  before provisioning a correction. This does not prove absent DK runeforge
  aura. All DPS actors have permanent enchants in actual admission.
- Affliction's latest andff226 gear hashes, Haunt/Drain submission counts and
  execute start times closely match. Drain Soul tick amounts, Dragonwrath and
  pet outcomes differ. Retained landed events lack crit flags, cast-instance
  correlation and complete aura-state joins; ff226 also lacks the newer stat
  snapshots. The decline remains unattributed, not a proven priority regression.

WCL action counts above come from the linked report's exact actors and differ
from native landed-event counts. Roster, equipment, phase coverage and proc
opportunities remain comparison limits. Switching30009 to Survival tests the
requested spec/setup and preserved duties; it cannot prove the other losses fixed.

Balance review narrows the area-policy lead: Force of Nature33831 is a
non-damaging guardian summon, but the shared predicate treats its destination
area as hostile multi-target damage. All28 retained masks reject it and no
native summon occurs. Resolver and executor duplicate that predicate. A repair
must distinguish summon geometry from damage and validate native Treant targets;
it does not justify enabling genuine Starfall, Chain Lightning or Fire AoE for
all actors. Those spells currently conflict with the route's exact-target focus
contract. Elemental's lower Earth Shock count is plausibly downstream of absent
Chain Lightning charge generation; no independent Elemental gate or coefficient
defect is proven. Its Fire Elemental, Spiritwalker's Grace and head Bloodlust
are present.


## Survival native validation and newly localized caster losses

Source8146 replaced MM with the exact promoted Survival setup but exposed a
35yd profile cap and core-single-target enemy-count ceiling. Survival did only
14,603.545DPS and stopped offense during the head window. Source699 repairs
those gates within native40/45yd shot limits: Survival reaches37,019.760DPS,
lands Cobra and core shots on head, and has no former head range/count rejection.
These are native end-to-end outcomes, not a WoWSims-equivalent DPS score.

Raid DPS nevertheless falls205,544.666→191,627.988 and six Infection damage
hits land on three actors. The Fire losses concentrate on head:30006 landed
Fireballs15→5 and30007 thirteen→eight. Contact-evasion movement is recorded
through that damage window. Affliction's head escape moves it13.27→58.71yd
away; movement gates become range gates after stopping, with no owner damage
cast after+115.310 until the head closes. Offensive stats/procs are present.
This establishes casting-opportunity loss before any coefficient diagnosis.
It does not establish that the Hunter SQL caused all new contact or movement.

The next bounded correction is the unsupported enemy-target AoE ExplosiveTrap
row. Its native spell is self-placed/range0. At+50.483 its failure requests an
inward combat-range path; later Hunter contact and Infection are recorded.
Disabling that invalid action preserves MultiShot and the accepted shot gates.
The following run must measure actual movement, Infection and all-bot output;
removing the row alone is not a claim of overall safety or performance recovery.
