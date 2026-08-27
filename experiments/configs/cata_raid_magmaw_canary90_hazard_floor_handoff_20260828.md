# Magmaw Canary90 hazard-floor handoff

Canary90 used the unchanged exact gameplay binary from commit
`7c13a3f89352c53b740820a1fe988a2796b2dc0c` and the combat diagnostic from
commit `944b10579ec7bc5eea0840c7b15f297bc7cfea6d`. Fresh provisioning and DB
readback passed. The roster reached the Chainwielder and made native combat
progress. The completion watchdog stopped the run after Affliction Warlock
`Mgwdpsc` repeated `validation_route_mechanic / hazard_exit_failed` 20 times.
Cleanup, evidence demultiplexing, bounded combat-log reconstruction, and
forbidden-assistance gates passed.

## First broken edge

The hazard controller requested an ordinary outward exit for bot GUID `30008`
from the Chainwielder's Overhead Smash marker:

- hazard source entry: `42690`
- detection and damage spell: `79580`
- native radius: `20` yards
- requested endpoint: `(-370.107, -82.6631, 213.665)` on map `669`

The shared movement planner sampled target floor Z `-91.5379` for that XY while
the requested/current encounter floor was near Z `213.665`. It rejected the
move as `route_destination_invalid_z_transition` with absolute delta `305.203`
against the `4` yard threshold. The same invalid lower-floor sample was retried
until the repeated-decision watchdog fired. This is a trace-proven shared
movement/floor-selection edge, not a class rotation or enemy-tuning issue.

## Combat diagnostic result

The combat-log export passed with all `29/29` chunks and `355574` decoded bytes.
For the 62-second Chainwielder combat window:

- party damage: `2171704`; party DPS: `35027.484`
- party healing: `252597`; party HPS: `4074.145`
- `Mgwdpsc`: `5581.000` DPS, `27.4%` damage uptime, zero pet damage
- healer HPS: restoration druid `1855.323`, holy paladin `2209.097`,
  discipline priest `0.000`

Incoming damage to `Mgwdpsc` was `50175` Constricting Chains and `31700`
Overhead Smash. These figures are encounter diagnostics, not isolated 300-second
spec calibration values.

## Bounded repair contract

Repair one shared movement-planner floor-selection edge so a same-level hazard
exit on multi-level geometry does not select an unrelated lower floor. Preserve
native pathfinding, collision, arrival checks, movement ownership, and hazard
priority. An invalid or genuinely cross-floor destination must still fail
closed. Do not special-case Affliction, Chainwielder GUIDs, or the recorded XY;
do not teleport, force movement, disable the watchdog, shrink the native hazard
radius, or tune enemy damage/health.

Add focused deterministic coverage for:

1. the recorded same-level request with a bogus far-below height sample;
2. a genuine cross-floor destination that remains rejected;
3. a normal valid floor that remains accepted;
4. bounded retry/backoff or alternate-exit behavior so one invalid sample cannot
   flood the decision trace every tick.

## Immutable evidence

- report: `/tmp/trinity-magmaw-7c13a3f893-canary90.zkpUEi/canary90-report.json`
- report canonical SHA-256:
  `b5c669b7b14d2c46c79b0e6202691a8e58d7998f171165e5a2aea3aa09fcd89b`
- report file SHA-256:
  `d39d486eee21d8f918338d690c5fec86f87417fd0dbe4fcfc5e9ced9febcaea5`
- raw JSONL SHA-256:
  `56ab0e1d680bbb548a5fa70b007680dbdc4b639e13cd6ae59380c253a30c986c`
- worldserver log SHA-256:
  `cd58e959d8f5e226b29719acac64b2e0eb169affd3b756babd8a5b120439dc53`
- gameplay binary SHA-256:
  `c02a71618b616f6699b1504c66dc0d26fcd8efa14f33938afdaaf57da706cfba`
- worldserver exit code: `0`
- forbidden assistance observed: false
- fixed raid success timer: none

This handoff authorizes one bounded shared-runtime repair. It does not authorize
a class-policy change or claim that Chainwielder, Drudges, or Magmaw cleared.
