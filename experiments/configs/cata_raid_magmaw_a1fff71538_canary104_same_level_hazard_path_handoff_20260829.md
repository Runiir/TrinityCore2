# Magmaw same-level hazard path admission handoff

## Identity

- Source commit: `a1fff71538f463a3aa393da2507670a6279eff70`.
- Worldserver SHA-256: `5c458aaaf91132d0031bd2ae1334a88a998a0ddb9cfda64c282416115f90ff8f`.
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`.
- Closed autonomous canary: `/tmp/trinity-magmaw-a1fff71538-canary104.G772RN/run`.
- Report SHA-256: `36ddd947f603c8623cad0bc51b9d2201ee4d310d8185cc51b033d902bf4d478d`.
- Combat-analysis SHA-256: `c6067ab9a47d2ac1ebeb184cc8b433e7ba6686b5d432f051d05db619fceae432`.
- Combat-log SHA-256: `7361701e58e83dc77afaea8b0887f5ccd7b0c4cf03baa2e149951c315bdbd9fd`.
- Worldserver-log SHA-256: `6b102567c53e690889de76390d8beab98f4a4b0071c261e929f55331c2dc02ff`.

## Proven route result

Canary104 cleared the Chainwielder and both Drudges with three kills, zero
trash deaths, and zero future-pack contamination. It reached route generation
4 and fought Magmaw. This verifies the prior central future-pack movement guard
for the observed run and keeps this work unit out of trash routing.

The Magmaw attempt dealt `26,155,575` party damage at `92,750.266` active DPS
and `78,213.392` elapsed DPS. It produced `3,037,154` healing at `10,770.050`
active HPS and `9,082.045` elapsed HPS. Nine bots died. The controller stopped
on `validation_route_stuck_loop` after the last live healer exhausted recovery
candidates. The stuck loop is a terminal symptom, not the repair target.

## Trace-backed shared-runtime edge

The final planner observations contain several local encounter movement
requests whose declared destination Z is on the same room floor as the bot,
while `Map::GetHeight` resolves an unrelated lower collision/terrain floor.
The planner then rejects native movement that is required to survive a lethal
mechanic:

- Tank 30001, `parasite_contact_evade`: current Z `210.948`, requested Z
  `210.948`, sampled floor Z `-102.075`, rejected
  `route_destination_partial_path`.
- Tank 30002, `parasite_contact_evade`: current/requested Z `210.948`, sampled
  floor Z `-104.459`, rejected `route_destination_partial_path`.
- Healer 30003, `parasite_contact_evade`: current/requested Z about `210.995`,
  sampled floor Z `-100.791`, rejected `route_destination_partial_path`.
- Healer 30004, `pillar_evade`: current/requested Z `212.129`, sampled floor Z
  `-66.148`, rejected `route_destination_unreachable`.
- Mage 30007, `pincer_preposition`: current/requested Z `207.718`, sampled
  floor Z `-106.229`, rejected `route_destination_path_floor_gap`.

The existing planner recognizes a `sameLevelDeclaredFloorFallback`, but these
same-level hazard/mechanic requests can still fail later at native path
admission. One terminal healer position was below the room at Z `73.613`, and
the combat log ended with self-damage from `Magma`. Do not infer a single
killing spell from this receipt; repair the directly observed admission edge.

The encounter aggregate independently shows the mechanics that needed those
movements: Pillar of Flame hit the hunter for `137,512`; Massive Crash hit
several ranged actors; Parasites infected or meleed multiple actors; tanks took
Mangle; and all actors accumulated Lava Spew. Affliction produced `25,297.904`
active DPS and `7,134,009` damage, including `1,859,265` pet damage (`26.062%`).

## Bounded repair contract

Repair one shared movement-planner edge: admit a short, local, same-level
hazard or encounter-mechanic move when the actor Z and declared destination Z
agree but map height sampling resolves a clearly unrelated lower floor. Keep
the existing shared movement executor, priority ownership, and trace identity.

The repair must remain fail-closed for genuine vertical transitions, long
routes, recovery/runback, missing-map destinations, future-pack destinations,
and paths whose native endpoint is not locally consistent with the declared
same-level floor. Do not bypass the central future-pack guard. Prefer one small
predicate or path-admission rule over encounter-specific branches.

Add focused counterexamples for the recorded Magmaw room inputs and for a real
floor transition that must remain rejected. Do not change class rotations,
healing policy, encounter coordinates, boss mechanics, route coordinates,
creature aggro, acceptance thresholds, or watchdog policy. Do not build, run a
shard, modify databases, publish evidence, or commit inside the specialist work
unit. Keep every C/C++ source and header below 1,000 physical lines.

## Matched verification

Root reviews and commits the bounded implementation, builds its exact commit,
and runs a fresh autonomous completion-watchdog canary. It must again clear all
three trash mobs without contamination. At Magmaw, planner receipts for local
same-level `parasite_contact_evade`, `pillar_evade`, `massive_crash_evade`, and
pincer movement must no longer reject solely because of the unrelated lower
floor sample. The run must preserve genuine vertical-transition rejection and
must produce DPS/HPS evidence. Success still requires a Magmaw kill; one clean
movement receipt is only intermediate verification.
