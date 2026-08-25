# Magmaw Drudge source-union escape-path handoff

The exact `b673f5f565052fbc5afd4a46fc8677cc1236fe34` Canary27 failed closed under the completion watchdog after 276.620 seconds. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and stopped on `death_loop_watchdog` with five deaths and five of ten bots alive. It did not reach or kill Magmaw. Identity, provisioning, telemetry demultiplexing, cleanup, and forbidden-assistance gates passed. This is failed diagnostic evidence, not a clear.

The live-plus-native-home source union added by `b673f5f565` worked as an endpoint invariant. The first newly proven failure is its path admission rule. Member 30006's declared point `(-295, -75)` was correctly rejected because source 0 was too close. A dynamic point `(-293.524, -76.8593, 213.472)` was selected, submitted, and reached. For members 30003 and 30004, grounded exterior candidates were found, but `SourceUnionPathSafe` rejected them as `drudge_anchor_source_union_path_unsafe` because it required every path point after the origin to already be outside the full 15-yard radius. Both members began about 7.13 yards from a live Drudge. Any real exit from that state necessarily contains early path points inside 15 yards, so the rule made safe escape impossible.

The bounded repair is to preserve the strict live-plus-home union at the endpoint while admitting a deterministic outward escape. For each live or home source anchor, a member that starts outside the exclusion radius must remain outside it. A member that starts inside may traverse outward only if no admitted path point moves materially closer than its starting distance and the endpoint is outside the exclusion radius. The existing specialized minimum-distance escape uses this same monotonic floor rule. Do not remove native-home checks, reduce the configured 15-yard radius, change healing priorities or encounter damage, force movement or threat, teleport, revive bots, mutate Drudge AI, or manufacture an encounter result.

Some rejected fan candidates reported floor values near `-140`. These points were off the upper platform and were correctly rejected by the native floor-height delta check. They are useful diagnostics but are not the first broken edge.

The next work unit is one small route-owned implementation with focused pure replay coverage for safe-origin, unsafe-origin outward, unsafe-origin inward, endpoint, and live-plus-home union cases. After root review and a queued exact build, provision a fresh exact ten-player roster and run one completion-watchdog canary. There is no fixed raid success timer.

Failed Canary27 evidence:

- Report: `/tmp/trinity-magmaw-b673f5f565.JosIu5/canary27-run/capture/report.json`
- Canonical report SHA-256: `f5a0dba90695b708364a6707ae4e0d28275fd1cc0eb40808750311000a673b8a`
- Report file SHA-256: `3b183e92eb78d1a9e553231992ada8d933af0f15a063de57e8284c2c1bd5f707`
- Raw trace SHA-256: `606ad841e725d07a9ed189e02e7b226e0dabae6297ace0bc33be81d6160e35dc`
- Server log SHA-256: `989f7f5aacf0dc11bb92baa5a47d20950044ea9b2ce627ccc8810e9eeb584d01`
- Exact build receipt: `/tmp/trinity-magmaw-b673f5f565.JosIu5/worldserver-build-receipt.json`
- Build receipt SHA-256: `9695e676da2fcb93e8b762bf6879e33695c49789c0747c7fddf6d3d1325e796e`
- Build receipt file SHA-256: `059d0500430988ff0f3dde9001ae90eab73774073bdfd0b8610c537412817d97`
- Exact binary SHA-256: `ae7a15109cb4d353dab8283a4d26c7b2c4c0e923d91e4e1ea23bb6284e87eb64`
- Run identity: server epoch 6158413697777649, attempt 2, route generation 3

Do not promote Canary27 to DVC acceptance data.
