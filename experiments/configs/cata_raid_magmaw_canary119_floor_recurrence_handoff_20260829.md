# Magmaw Canary119 same-level floor recurrence

Canary119 was the first Magmaw run admitted through the commit-bound
recurrence gate. It used source commit
`173e21af8f3d86a872559f2fb226ae1f6a9e545f`, binary SHA-256
`ac2afc585cf6c9ddc0a46777180d868269a6da865e2f4fb9d64650eaccd3dcce`,
and an independently verified 16-fixture regression receipt. The exact
admission receipt SHA-256 was
`ad7f416d4b45ac23cd7b95d8efc205ef5e3666b2b887e184be5ced3267b25797`.

## Outcome

- The Chainwielder and both Drudge packs cleared with zero deaths.
- All ten members consumed their native flask, food, and pre-pot from their
  bags. A second combat potion remained reserved.
- Magmaw was engaged for 270.168 seconds.
- The encounter produced 92,781.395 party DPS and 13,423.509 party HPS.
- Two members died; eight remained alive and Magmaw remained in combat when
  the repeated-decision watchdog ended the attempt at 506.618 seconds.
- The route did not complete and the run is a gameplay failure.

## First reusable causal edge

The first rejected mechanic move was Affliction sequence 3376 at
`1787994880682`, approximately 87 seconds after Magmaw combat began. A
`parasite_contact_evade` request for `(-308.477, -32.2655, 211.581)` produced a
complete native path, but the normalized endpoint was
`(-309.333, -33.6001, 210.339)`. Its floor proof was valid and its vertical
normalization was within tolerance, but its 1.586-yard horizontal difference
exceeded the generic 0.5-yard endpoint identity tolerance. The planner rejected
the usable bounded escape as `route_destination_endpoint_mismatch` instead of
accepting its native endpoint as local mechanic progress.

That first false negative was followed by short, same-room mechanic
destinations whose declared Z was approximately 210--212 while the static
height query selected an unrelated lower floor between approximately -90 and
-112. Examples include:

- `parasite_contact_evade`: request `(-296.185, -27.0863, 210.948)`, sampled
  floor `-105.840`, Z delta `316.788`, then
  `route_destination_partial_path`;
- `massive_crash_evade`: request `(-287.675, -29.781, 211.813)`, sampled floor
  `-111.843`, Z delta `323.656`, then
  `route_destination_unreachable`;
- another parasite escape request at `(-304.820, -11.3816, 211.116)` sampled
  floor `-90.1575` and repeatedly failed admission.

Affliction later fell or became stranded at Z `160.893` while formation
restoration requested the room floor near Z `211.815`, then died. This is a
recurrence of `same_level_encounter_hazard_path_rejection`,
`same_level_movement_path_floor_false_negative`, and their shared native-path
proof parent. The revision-1 regression fixtures passed at admission but did
not reproduce the live endpoint-normalization plus unrelated-lower-floor
sequence. Those fixtures are therefore inadequate and must be revised before
another canary is admitted.

## Downstream gameplay evidence

Fourteen direct Parasitic Infection events reached five players. The assigned
fire mage was again contacted at 0.2 yards, and infected players propagated
Infectious Vomit. Revision 4 reduced the earlier Canary118 contact count but did
not close containment because valid escape movement still failed native path
admission. Affliction dealt 19,099.638 DPS with 30.682% pet damage; its lower
throughput is downstream of the failed encounter movement and is not the next
work unit.

## Required closure

The next fixture must replay both observed forms: a complete same-level native
path whose usable endpoint is normalized 1.586 yards horizontally, and a
same-level hazard request with an unrelated lower `GetHeight` result plus an
incomplete path. It must prove a bounded, same-floor, native-path-backed
progress segment is selected while genuine cross-floor, missing-MMAP,
shortcut, far-from-poly, and non-progress paths stay rejected. No further live
canary is allowed until the revised fixture and the entire recurrence bank pass
at one clean source identity.

## Evidence identity

- Canonical report SHA-256: `ef5c69ea881680b06d6a9366f0771bcd681c5b8389e285ef4420e6d794882f85`
- Raw JSONL SHA-256: `f766c6593c86be21c4e8cc2b777b1a4c14ae0df9d304ca0c2c62fcac313ae323`
- Worldserver log SHA-256: `6e5948bb7e725e2d532ed6a56f4152d3c2ef0d99163326c1fe9f6bca2f462059`
- DVC pointer:
  `artifacts/cata_raid_program/phase1_foundation_173e21af8f_magmaw_canary119_20260829.dvc`
