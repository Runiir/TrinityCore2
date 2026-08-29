# Magmaw Canary109 recurrence-stop handoff

## Identity and terminal result

- Run: `trinity-magmaw-d111136523-canary109.5GqLp7`
- Source commit: `d1111365238abc4fd3ccf8cd51fc58c0cdce1c95`
- Worldserver SHA256: `5e51c6c0586e93e18997d46979a9ffcfdb1c149cf4fc8a8bd6585dde2aecac70`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Completion: `semantic_progress_plateau_watchdog` after 758 seconds
- Route evidence: Chainwielder and both Drudges cleared without deaths or
  future-pack contamination; Magmaw was pulled but not killed
- Totals: 3 trash kills, 9 deaths, 1 survivor, 0 raid-boss kills

The Canary108 prepull repair passed its live boundary. Every admitted member
used one ordinary flask, food, and pre-pot from inventory. All ten pre-pot
receipts have one submission, one successful use, and an observed aura,
including the fixed max-range fire mage (`30006`) and hunter (`30009`). The
prepull receipt remained `ready=true`, `failed=false`, with a second potion
reserved. This makes
`magmaw_prepot_geometry_conflicts_with_bait_formation` absent in this run; it
does not close the signature because the full route did not clear twice.

## Tenth parasite-control occurrence

The retained combat events directly record Parasitic Infection on five
players:

| GUID | Player | Infection hits | Infection damage |
| ---: | --- | ---: | ---: |
| 30003 | Restoration druid | 2 | 14,705 |
| 30005 | Discipline priest | 6 | 28,201 |
| 30006 | fixed bait fire mage | 8 | 49,938 |
| 30008 | Affliction warlock | 1 | 7,182 |
| 30009 | fixed bait hunter | 10 | 42,347 |

The first Pillar hit the hunter at `1787965280768`. Both fixed baiters were
infected about six seconds later while moving through the declared lateral
lane. Later parasites reached three non-bait players. The run therefore adds
the tenth unique occurrence of
`magmaw_parasite_control_allows_player_infection`; intervening runs where the
boss was not reached do not reset that history.

The current geometry is also an architecture warning. The two bait endpoints
are 30 yards behind the boss and 24 yards laterally, while the support stack is
22 yards behind the boss. Although each endpoint is at least 20 yards from the
support stack, the straight segment between the endpoints passes only 8 yards
from it. Current deterministic tests validate endpoint clearance, not the
clearance of the traversed corridor or a full Pillar-to-parasite trajectory.
That relationship is an inference from current code and trace coordinates;
the infection events above are direct evidence.

No Canary110 is admitted until the ten-run architecture review identifies one
shared invariant, retains a deterministic counterexample, and records which
historical fixes failed to preserve it.

## Post-wipe liveness edge

After the native encounter reset, nine dead members repeatedly returned
`native_full_wipe_wait_partial_death`. The only survivor, fire mage `30007`,
was out of combat and resumed prepull staging. No hostile remained engaged,
but dead members could not begin ordinary release/corpse-run recovery because
the route declared `native_full_wipe_only`. Recovery telemetry accumulated
46,998 events before the semantic-progress watchdog closed the run. This is a
separate shared-runtime signature from the mechanic that caused the wipe.

## Combat signal

| Segment | Active DPS | Elapsed DPS | Active HPS | Elapsed HPS |
| --- | ---: | ---: | ---: | ---: |
| Chainwielder | 98,923.404 | 78,187.169 | 5,993.362 | 4,737.039 |
| Drudges | 110,700.000 | 92,885.207 | 35,035.079 | 29,396.934 |
| Magmaw | 78,720.470 | 70,759.825 | 13,553.377 | 12,182.785 |

Magmaw received 16,924,901 party damage over 215 active combat seconds.
Affliction produced 24,915.363 active DPS and 1,145,843 pet damage (21.39% of
its total). This encounter segment is diagnostic and does not replace the
exact 300-second isolated self-provided-buff calibration.

## Artifact hashes

- `report.json`: `2e8a4ebe414199426b179100fdbb1dbb8989b750e7b5ba46da0a64d657cfdf02`
- `combat_analysis.json`: `a0a7b9710ade2f8b2976db8006ba91820fcc97749d26573ba3b801b26f975142`
- `combat_log.json`: `2f0afccbde815c6feaebed5cd878de4a902b65bac657bb584c8def42284e10b3`
- `heartbeat_events.jsonl`: `a19633a37aded0ace30092fdaa56108974b1f07cda85a4dbbac41ce9badebde3`
- `worldserver_output.log`: `d802f75fa48ed51a798ef82640ddc0a8db9cdf04c851e2727e0f732273227884`
- `validation_route_manifest.json`: `f549cbb99bb1767f00c8a1697d249d2f4bec52b8df3b411b25adad94d94fc8f8`

This failed run is retained only until this compact handoff and its recurrence
decision are committed. It is not promotion evidence and must not be
published as a pass.
