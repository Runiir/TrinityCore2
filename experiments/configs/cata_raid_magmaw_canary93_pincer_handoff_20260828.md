# Canary93 Magmaw pincer movement handoff

## Scope

- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Route node: `bwd.magmaw.encounter`, generation 4
- Runtime commit: `4c061723ec2d88ca56dfcc250eaab5fde1bcb1d2`
- Binary SHA-256: `8ebb02b4f782aaf16f5ebe1a900925fdcfefe346528c10f457db4770a4b8adee`
- Gate-bearing build receipt semantic SHA-256: `8def4c714b965d37d81c7ec80f93efe2df7984f8895730b4d879130cbc478c9e`

## Accepted observations

Canary93 cleared the entrance regroup, Chainwielder, and Drudge nodes with all
10 bots alive, then engaged Magmaw. It stopped fail-closed on the death-loop
watchdog after the Blood Death Knight, Protection Paladin, and Restoration
Druid died. Cleanup, identity, forced terminal evidence, and all 307 combat-log
chunks passed. No forbidden assistance was observed.

The Magmaw segment lasted 226 combat seconds and recorded 60,204,690 party
damage, 266,392.434 party DPS, 4,985,452 party healing, and 22,059.522 party
HPS. The Affliction actor recorded 9,419,209 damage, 41,677.916 DPS, 82,665
healing, 365.774 HPS, and 2,625,009 pet damage for a 27.8687 percent pet share.
These are encounter values, not the 300-second training-dummy reference.

The Magma Spit repair is behaviorally accepted for progression. The retained
late events contain six volleys with at most three unique victims and no
duplicate victim in a volley, instead of Canary92's 24-hit first volley. The
current outcome-only telemetry cannot prove the exact 95280 cast count or every
older volley because 7,578 recent-ring events were dropped. Cast-level or
compact per-volley telemetry remains a separate evidence-tooling gap.

## First broken edge

The first death was the Blood Death Knight. Its last native damage was eight
ticks of Mangle 89773 after Massive Crash. The second death was the Protection
Paladin, also after eight Mangle ticks. No `mount_free_pincer` or
`launch_native_hook` action completed before either death.

During the first pincer window, assigned hook DPS 30006 and 30007 repeatedly
submitted parasite or other hazard movement. DPS 30007 briefly received a
mechanic-owned approach destination, then the next decision replaced it with a
higher-priority hazard destination. DPS 30006 remained hazard-owned. This is a
movement-ownership conflict: the native pincer approach cannot remain active
long enough to reach, mount, and launch both hooks. Healing the indefinite
Mangle channel is not the encounter solution.

The later Restoration Druid death was three Pillar of Flame 77971 hits within
one second. Canary93 therefore also rejects the current multi-Pillar avoidance
behavior, but that is a later edge. The pincer window is repaired and replayed
first.

## Bounded repair contract

Owner skill: `raid-bot-runtime-implementation` using the encounter-owned
adaptive Magmaw movement policy.

When Magmaw is natively spell-clickable, the two deterministic hook assignees
must retain the pincer approach and interaction path until they mount and
launch their native hooks. Already-landed Massive Crash markers, ordinary
parasite avoidance, and ranged formation restoration must not make that path
oscillate. Preserve an immediate local Pillar escape when a hook assignee is
actually inside the active Pillar hazard. Preserve native interaction flags,
vehicle seats, hook spells, damage, timing, and normal target selection.

Add a focused deterministic regression with simultaneous pincer availability
and competing hazard observations. It must prove stable approach ownership and
the existing native mount and launch actions without encoding captured GUIDs
or coordinates.

Forbidden shortcuts include removing Mangle, reducing encounter damage,
extending the pincer window, teleporting players, forcing vehicle occupancy,
forcing boss state, suppressing the watchdog, or special-casing captured GUIDs
and coordinates.

## Evidence locations

- Report: `/tmp/trinity-magmaw-4c061-canary93.XJ0eTV/canary93-report.json`
  (`f2340b48e46b84acc07b46440c5d734f84687349037fa444db2ec43dccd7de44`)
- Normalized telemetry: `/tmp/trinity-magmaw-4c061-canary93.XJ0eTV/canary93-raw.jsonl`
  (`378fd3d45b16127d12f3e5bc080cfa3cc85df724501b4431031067e05522654b`)
- Worldserver log: `/tmp/trinity-magmaw-4c061-canary93.XJ0eTV/canary93-worldserver.log`
  (`bb6b435d59a68ae3c1d9bde8224cad1d1cc6999385ad8bbdb78a339319d20fc0`)

The next live check must use a fresh provisioned state and the completion
watchdog. It must show both assigned users reaching the native pincer flow and
prevent the first Mangle death before any later Pillar failure is classified.
