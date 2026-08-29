# Magmaw Canary117 parasite recurrence handoff

## Identity and terminal result

- Source commit: `1dcdd3a1add2deb268667a2765672068059a91ce`
- Run: `trinity-magmaw-1dcdd3a1ad-canary117.QXkp5t`
- Classification: `gameplay_failure`
- Terminal gate: `death_loop_watchdog` after 503.495 seconds
- Report SHA-256: `df71760eefdbcf6229bdcdab4489828af8bf217696dd378cb8edc8f2d01e88e5`
- Raw JSONL SHA-256: `5d63a2245ed51115a3d2206836f4c303db5e56fd96f5c82f642812fb7a446101`
- Worldserver log SHA-256: `f375fd1b3e2f858601adfce9e994d2bc8025d37a272c5ef261e10e130fa0cf67`
- Terminal diagnosis and combat-log transport were complete. The final forced
  trace was incomplete because the response reported a delta gap, so it cannot
  certify acceptance.

## What remained stable

The entrance, Chainwielder, and both Drudges cleared with zero deaths. Magmaw
formation, pre-pull consumable staging, and pull completed. The run did not
reproduce current-route authority, future-pack contamination, route-Z
normalization, same-floor path proof, or prep-pot formation blockers.

Chainwielder produced 81,568.421 party DPS and 4,945.316 HPS over 57 active
combat seconds. Drudges produced 105,668.182 DPS and 44,388.015 HPS over 66
active combat seconds.

## Recurrence verdict

The revision-2 parasite repair is provisional and failed its first live
canary. Five players took direct Parasitic Infection (`78941`): Fire Mage
30006, Elemental Shaman 30010, Restoration Druid 30003, Holy Paladin 30004,
and Discipline Priest 30005. The infected druid then dealt Infectious Vomit
(`78937`) to Fire Mage 30007 and healers 30004 and 30005. Counting only the
vomit aggregate would incorrectly report one infected actor; damage-taken
attribution proves the wider containment failure.

This is occurrence 13 of parent signature
`magmaw_parasite_containment_failure`, and the first post-review occurrence
after the architecture review acknowledged the first 12. The retained
`magmaw_parasite_lane_paths_v1` revision-2 fixture is therefore incomplete and
invalidated by this run. No successor build or live canary is admitted until a
revision-3 replay materially extends the live policy-to-native-outcome boundary.

The route-level destination field remained stable, but the native movement
request did not. The first mage hazard intent appeared at
`1787988207018`; direct infection followed at `1787988222602`. Later retained
diagnoses for the same mage show local radial requests changing through
`(-345.794,-25.942)`, `(-349.374,-22.8815)`,
`(-330.476,-39.0387)`, `(-312.401,-68.8224)`, and
`(-340.855,-30.1652)`. Across the run the trace contained 77 parasite-evade
events across seven bots, with as many as 36 unique planner requests for one
bot. Revision 2 retained one contact escape, but temporary clearance retired
it and the next contact generated another arbitrary radial escape. It did not
preserve fixed left-right lane semantics across the complete parasite wave.

## Throughput and downstream symptoms

Magmaw produced 75,979.481 active party DPS and 14,086.778 active party HPS
over 216 active combat seconds. Affliction contributed 28,646.301 DPS with
1,405,929 pet damage, or 22.72 percent of its damage. Hunter and Elemental
throughput collapsed to 4,724.556 and 2,321.968 DPS. These values are useful
diagnostics, but they cannot qualify class throughput because parasite
containment and survival failed first.

The terminal route-recovery `route_destination_unreachable` decisions and
third death-loop transition are downstream symptoms unless a separate replay
proves an independent recovery failure. Do not route them ahead of the live
parasite containment recurrence.

## Required next boundary

Do not rerun revision 2 or launch Canary118. Reconstruct the earliest direct
infection as one multi-tick replay from role ownership and target selection,
through fixed left-right lane intent, repeated parasite contacts, native path
submission and progress, to infection-free safe arrival. The replay must
reject arbitrary radial destinations after temporary clearance and must not
mistake a stable route-level destination field for a stable native request.
Preserve all revision-1 and revision-2 expectations. Revision 3 must add the
missing live transition and must fail before its runtime repair. After the
full immutable bank passes at the exact source identity, one fresh
completion-watchdog canary may be admitted. Two consecutive complete route
clears with every known signature explicitly absent remain required for
closure.
