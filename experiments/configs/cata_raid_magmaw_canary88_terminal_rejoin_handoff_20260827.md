# Magmaw Canary88 trash-terminal and cohort-rejoin handoff

Canary88 used the clean exact build at commit `47e8a48e6dd42557d6937d7abb95d2fac1f1fe3a`. The current-standard 10N roster cleared the entrance regroup, killed the Chainwielder, and killed both Drudges. One Affliction Warlock was already dead and performing native corpse runback, so the route remained at `bwd.magmaw.drudges`. The surviving bots repeated `validation_route_regroup / hold_anchor_no_focus` until the completion watchdog stopped the run. Magmaw was not pulled. Cleanup passed with the worldserver absent and zero bots and leases.

## First broken edge

The Drudge pack was terminal, but `RunTargetEngagement` used one full-roster-at-endpoint predicate for two different decisions:

1. whether the dead trash pack can emit `trash_cluster_cleared`; and
2. whether the route manifest may advance to Magmaw.

That made one valid native recovery episode suppress the pack terminal event. With no living trash focus, survivors remained in regroup and produced the repeated no-focus fingerprint. Pack death and cohort rejoin are separate state transitions.

## Bounded repair

Commit `62ae6550f8d84afb3f61b1e302f49e00c36e3c03` adds a pure cohort-readiness classifier. A dead roster member counts toward trash-terminal accounting only when its native recovery episode exactly matches the current attempt, route generation, wipe generation, and death ordinal and is not terminal. Pack terminal can then be emitted while the manifest still waits fail-closed for the full living roster at the endpoint. Commits `bea928d382127692fa32e67bf5743692637f91e96` and `8fea9a8083cbe6756bd6ec2725e70acdd07c0942` repair build-visible diagnostics defects exposed by the exact native build.

The repair preserves the candidate-priority execution path. Strategy and validation code propose typed actions; the arbiter still owns ranking, resource claims, and native submission. The helper extraction does not claim to remove total decision complexity: `RunTargetEngagement` remains a separate high-CCN refactor target after this live edge is verified.

## Canary89 acceptance

- both Drudge deaths emit `trash_cluster_cleared` even when one member is in a valid exact native recovery episode;
- survivors leave the no-focus terminal loop;
- the manifest stays at generation 3 until all ten members are alive, rejoined, and at the endpoint;
- after full rejoin, the route advances to `bwd.magmaw.encounter` and exercises the queued Magmaw movement candidate;
- no teleport, forced resurrection, threat injection, forced target, health/damage tuning, or watchdog suppression is observed;
- the completion watchdog, not a fixed success timer, owns termination and server cleanup.

## Immutable evidence

- Canary88 capture report: `/tmp/trinity-magmaw-47e8a48e6d-canary88.6ZGin1/canary88-report.json`
- Capture report canonical SHA-256 recorded at capture: `0251246f27d6632a6382e77ab90c71aa3d70009d22992a4f623931feb3ce3f42`
- Compact post-eviction report file SHA-256: `3832300ada2fe3e913888aa7bed84b8eb33d15dba20c2fe3a340a8f9a889542d`
- Canary88 binary SHA-256: `13f4b07a66597896e688c8a32ef5c14ea0b0a9c316a969d40e3c4c70292c07e2`
- Current repair build receipt: `/tmp/trinity-magmaw-8fea-build.6pszNI/worldserver-build-receipt-v2.json`
- Current repair build receipt file SHA-256: `8260abb3183d247362f0988bc30ca751ae58ef98fc57079297b1fabbdceec723`
- Current repair binary SHA-256: `08df0fa478a49ec31ac29e65ad9287158da8df102402be1ab866fa1c27007048`
- Focused tests: 170 cohort/readiness and autonomy tests, 14 arbitration/movement/layout tests, 6 movement trace tests, and 2 terminal JSON tests passed
- Forbidden assistance observed: false
- Fixed success timer: none; completion-watchdog policy only

This handoff authorizes one fresh exact-build Canary89. It is not a clear and must not be promoted as acceptance evidence.
