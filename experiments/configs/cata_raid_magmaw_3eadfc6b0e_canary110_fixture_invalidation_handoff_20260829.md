# Magmaw Canary110 retained-fixture invalidation

## Identity and verdict

- Run: `trinity-magmaw-3eadfc6b0e-canary110.hz84YE`
- Source: `3eadfc6b0e280993cb079ea4c542db8729fc26dd`
- Binary SHA-256: `b4b14cdded53a6b077740b156dd7953d4b5aa107ba0ffd411fc837589e9a439f`
- Verdict: `gameplay_failure / death_loop_watchdog` after 565.009 seconds
- Cleanup passed with zero bots, zero leases, and no worldserver process.
- No cheat, forced wipe, teleport, boss-state mutation, or synthetic encounter command was used.

The run cleared Chainwielder and both Drudges, recovered the Affliction
Warlock after a native Drudge reset, engaged Magmaw, and then wiped. It is not
acceptance evidence and was not published to DVC.

## First recurring causal edge

The retained lane-transition fixture passed before this run, but the live
`magmaw_parasite_control_allows_player_infection` signature recurred. The
fixture is therefore incomplete and invalid for promotion.

The first Parasitic Infection hit Protection Paladin `30001` at
`1787971013851`. Non-bait Fire Mage `30007` was infected at
`1787971028677`, then spread Infectious Vomit through the support group. Fixed
bait Fire Mage `30006` was infected only later at `1787971092181`; fixed bait
Hunter `30009` was never infected.

The complete combat-log transport shows that non-bait players damaged the
parasite pack before and during the first infection:

| Actor | Parasite damage | Decisive parasite-reaching actions |
| --- | ---: | --- |
| Protection Paladin `30001` | 119,381 | Avenger's Shield, Consecration, Hammer of the Righteous, Holy Wrath |
| Blood DK `30002` | 7,876 | Death and Decay, Blood Boil |
| non-bait Fire Mage `30007` | 369,990 | Living Bomb, Shadowbolt Volley, Flame Orb |
| Affliction Warlock `30008` | 11,883 | Shadowbolt Volley |
| Elemental Shaman `30010` | 113,263 | Chain Lightning, Shadowbolt Volley, Fire Shield, Fire Nova |
| fixed bait Fire Mage `30006` | 1,298,817 | assigned parasite damage |
| fixed bait Hunter `30009` | 168,130 | assigned parasite and pet damage |

The earliest architecture failure is not merely a lane endpoint reversal.
The strategy selected the two intended baiters, but the independently executed
class-action path still admitted parasite-reaching area and chained damage for
non-baiters. Tank area threat then brought parasites into the boss/support
stack. Reactive local evasion occurred only after containment had already
failed.

## Preserved working edges

- Party DPS/HPS: Chainwielder `91.2k / 3.55k`; Drudges `102.6k / 38.2k`;
  Magmaw attributable `72.5k / 11.6k`.
- Drudge partial death recovery restored `30008` without restarting the shard
  or mutating the surviving roster.
- The same-level native path repairs did not recur.
- The typed lane-transition implementation remains retained; it is insufficient
  alone and must not be removed while adding combat containment.

## Mandatory next gate

Do not patch another isolated helper and do not launch Canary111. Expand the
same compiled counterexample through the complete sequence:

1. observe a Pillar and the resulting parasite generation;
2. assign exactly `30006` and `30009` as bait/kill owners;
3. carry that assignment into immutable combat constraints;
4. execute class-action resolution for all ten roster members;
5. prove non-baiters cannot submit area, chained, multidot, pet, or persistent
   area effects that can touch parasites;
6. prove the baiters target and damage the live parasite generation while
   moving along the retained lane;
7. execute arbitration and native movement across multiple ticks, including
   GUID churn, lease expiry, preemption/resume, and arrival;
8. observe parasite threat/victim ownership, player distance, parasite death,
   and absence of spells `78941` and `78097` on every player;
9. preserve exposed-head priority and reset exact encounter state afterward.

Only after that compiled replay passes may the recurrence ledger admit one
matched capture-only canary.
