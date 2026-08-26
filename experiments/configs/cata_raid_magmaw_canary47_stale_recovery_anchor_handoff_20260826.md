# Magmaw Canary47 stale recovery-anchor handoff

Canary47 used the clean exact build at commit `08460bacf76fb3ca01fe6ef5f5b71702fd450cb4`. The current-standard 10N roster cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges` at route generation 3, established native ownership of both Drudges, and delivered two native Rushes. It did not target or pull Magmaw. The completion watchdog stopped the run after four roster deaths and a death-loop count of three. Cleanup passed with the worldserver absent and zero bots and leases.

## First broken edge

At recovery tick `1787755249681`, both tank recovery paths and tank arrival anchors were proven. Non-tank slots 3, 4, 7, 9, and 10 selected their frozen recovery anchors and reported safe recovery placement. Slots 5, 6, and 8 instead retained dynamic pre-pull candidate anchors:

- slot 5, GUID 30005: candidate 3 at `(-320.534, -63.5843, 212.702)` instead of recovery anchor `(-311.5, -116.3, 214.033)`
- slot 6, GUID 30006: candidate 1 at `(-293.17, -65.6471, 213.604)` instead of recovery anchor `(-295, -120, 215.947)`
- slot 8, GUID 30008: candidate 1 at `(-349.596, -69.2127, 214.071)` instead of recovery anchor `(-311.5, -123, 214.034)`

Those three cached anchors had `group_position_safe=false` and `exact_roster_member_reseparated=false`. The exact roster never completed recovery, normal offense stayed blocked, and GUIDs 30001, 30008, 30006, and 30005 died at timestamps `1787755250733`, `1787755252819`, `1787755253120`, and `1787755253821`.

The source boundary is in `SelectPathableDrudgeAnchor`. For non-tanks, `activeDynamicRecovery` remains true after the sealed recovery formation activates when the cached candidate index is greater than zero. That skips the candidate-coordinate match against `AnchorCandidatesFor`, even though candidate zero has changed to the declared frozen recovery member anchor. Dynamic fallback candidates remain valid before the recovery formation is sealed; their cache must not survive the transition into sealed recovery.

## Bounded repair

Implement one trace-backed runtime repair: when `IsRecoveryFormationActive()` becomes true, invalidate a non-tank cached dynamic candidate that does not match the declared recovery candidate and select the ordinary native-path-proven recovery anchor. Preserve dynamic candidate fallback before sealed recovery, both tank paths, native taunts and Rushes, movement-before-support ordering, source-union safety, spacing, combat envelopes, and all existing no-cheat constraints.

Do not change encounter aggro, damage, health, threat, victims, spell ranges, line of sight, pathfinding admission, Magmaw state, resurrection, or teleport behavior. Do not suppress watchdog or contamination detection.

## Immutable evidence

- Capture report: `/tmp/trinity-magmaw-08460bacf7-canary47.5Vl87x/canary47-run/capture/report.json`
- Capture report canonical SHA-256: `7bf3fd4956d84e9ef1551c2fd2e80c461d9e2096d686d9d6255eb51a011a77c1`
- Capture report file SHA-256: `29b6322c6cc0e81752562954daf471e2829cc03b8948f5a26460ea9c69fa73d8`
- Normalized raw trace: `/tmp/trinity-magmaw-08460bacf7-canary47.5Vl87x/canary47-run/capture/raw-output.txt`
- Normalized raw trace SHA-256: `395461a4acc07642ed91e072977d0c2f75bbcb685e0b0214c9cab3810ef26fc8`
- Worldserver log SHA-256: `dd069de1b1c28dfa7f06c660dec6c12b864207fb4eabb43c1a1db170b4db0bae`
- Build receipt: `/tmp/trinity-magmaw-08460bacf7-canary47-build.gdDjnl/worldserver-build-receipt-v2.json`
- Build receipt canonical SHA-256: `3ef3ecb02f664a7ff422782e4cf12ede55814c1aa6d48a9209f9ba67c8044618`
- Binary SHA-256: `4c7cda8d8d666853e8762a5ee1394a94c125c0282d7ec609d4c9359b851ca4ad`
- Forbidden assistance observed: false
- Fixed success timer: none; completion-watchdog policy only

This is a failed-run diagnostic receipt. It is not a clear and must not be promoted to DVC acceptance evidence.
