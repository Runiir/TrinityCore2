# Magmaw healer and transient-warning replay

The exact-build canary at source `202994c78eac89f2653e132b3fb37527f74719d1`
cleared the Chainwielder and both Drudges, then wiped on Magmaw. The completion
watchdog closed at 743 seconds with `semantic_progress_plateau_watchdog`.

Bound evidence:

- report: `4f04acad08988554d3889bfba5bacb3e2489fc2200fa65386b4a8721966737cc`
- combat log: `05ecb406b4eeda97eac4df1bb8bd652a2e1f5392f8e375a1bdaae475da6e5170`
- combat analysis: `1a708447c5091602a54253ae93ea3fcbcbfeb5a7cc648cc215fcb010411ecc0c`
- heartbeat stream: `8949ca316545cd0e6a348d8e43c125f51c97b0c295b2a7fd40e436969b1232b7`

During 97 active Magmaw seconds the raid produced 104,293 DPS and 11,961 HPS.
The restoration druid produced 8,402 HPS, but the holy paladin produced 1,886
and the discipline priest 385. A merely proposed hazard forced the latter two
specs into instant-only healing even when no movement path won arbitration.
Commit `a5126f82fabb33e40b04da817dae557acfb57f89` now requires an admitted active
native path before hard-cast heals are suppressed.

The live snapshot also emitted pull-time `pincer_preposition` for GUIDs 30006
and 30007 roughly one minute before Mangle. Persistent Crash dummy entry 47330
had been conflated with the transient warning. Commit
`62f6d27f91bb4f231b6b3e996c94ca1df8560d0a` removes dormant 47330 from the
adaptive observation and requires the lit Room Stalker 47196 with aura 87949,
or a real player Mangle aura. The same lit telegraph remains the local
Massive-Crash survival source.

Commit `4df5fef310c2352466bb38a5b25a08ca16fa1e56` retains at most 64 compact
movement-intent receipts across heartbeats so the next terminal report keeps
actor, route, gate/result, first/last timestamp, and count without raw snapshot
retention.

The next run is one freshly provisioned completion-watchdog canary from exact
source `4df5fef310c2352466bb38a5b25a08ca16fa1e56`. It must show no pull-time
pincer or dormant-dummy evasion, materially active Holy and Discipline healing
during Lava Spew, exactly two assigned DPS only after Mangle or the lit-stalker
warning, and continued progress into approach, mount, and hook. A clear is
required before the first of two consecutive acceptance clears can be counted.
