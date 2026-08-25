# Magmaw Canary28 displaced-origin recovery handoff

Canary28 ran the exact clean source commit `81ded72166532342311a9f4650d0dbed860fa7c5` and failed closed after 470.343 seconds. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and stopped on `death_loop_watchdog` with three healer deaths and seven of ten bots alive. It did not reach or kill Magmaw. Provisioning, exact build identity, telemetry demultiplexing, cleanup, and forbidden-assistance gates passed. This is failed diagnostic evidence, not a clear.

The `81ded72166` unsafe-origin path repair was useful. Canary27 completed no post-Rush reseparation. Canary28 closed observations 1 through 4 with all ten roster GUIDs recorded, proving that a member can now leave an unsafe live-source radius through a monotonic outward path. Observation 5 landed at `1787693320046` and never closed. Observations 5 through 20 have `reseparation_recorded=false`.

The first newly proven edge is the origin used to build non-tank recovery candidates. `AnchorCandidatesFor` always builds its deterministic fan from the member's declared formation anchor. A landed Rush can displace the member far beyond that point. Affliction warlock 30008 ended at `(-341.301, -79.0869)` while its declared slot-8 anchor remained `(-311.5, -78.0)`. At the final observation, the live sources were `(-328.567, -74.655)` and `(-297.355, -80.0307)`. The warlock was only 13.48 yards from source 0 and repeatedly returned `drudge_native_charge_lane_reseparate` with `no_candidate_committed`; its repeat count exceeded 1,300.

Replaying `BuildCandidatesForSources` with those exact points shows the mismatch. The declared-origin fan has only one endpoint that passes the source union and lane predicates, around `(-312.560, -80.356)`. A path from the displaced member to that point crosses toward source 0 and correctly fails the monotonic source-distance rule. Building the same fan from the member's current position immediately yields same-lane, source-union-safe outward exits, including approximately `(-343.366, -79.214)`. This preserves the existing 15-yard endpoint invariant and avoids crossing a live or home source radius.

The bounded repair is to generate non-tank landed-Rush escape candidates from the member's current position when that member is not source-union safe. Keep the declared anchor as the stable destination for ordinary staging and already-safe recovery. Preserve deterministic ordering, strict native path and floor checks, live-plus-home endpoint safety, monotonic path safety, lane membership, peer spacing, native movement submission, and the existing tank recovery behavior. Do not change the configured distance, healing, damage, threat, Drudge AI, encounter state, or watchdog.

Focused coverage must reproduce the exact displaced slot-8 counterexample and prove:

- the declared-origin fan has no admissible monotonic path from the displaced position;
- the current-origin fan has at least one deterministic outward candidate that is source-union safe and remains on the member's lane;
- safe members still use stable declared-anchor behavior;
- tanks keep their existing recovery-anchor path;
- source/home, spacing, floor, and native-path rejections remain fail closed.

Failed Canary28 evidence:

- Report: `/tmp/trinity-magmaw-81ded72166.gvvS4a/canary28-run/capture/report.json`
- Canonical report SHA-256: `69d6e1ee5111ad7cd1a9286fb898a5c34625eb0aa8724557cf45978c3fa5e563`
- Report file SHA-256: `d7ca54610d8587593e5b9ce4720fde3534514337acf23a390ddad1c493abfe0d`
- Raw trace SHA-256: `08c6094e3a5d2f4c20b603fb473001ed7ada31fcaad8d2819b98158967287393`
- Server log SHA-256: `dddb5c5bf43cfb0b55ddb74aa91d73b187419825abe798b6ada352ec5de57673`
- Exact build receipt: `/tmp/trinity-magmaw-81ded72166.gvvS4a/worldserver-build-receipt-verified.json`
- Build receipt canonical SHA-256: `086c845d0056841e6ab7656fd589e5b3ee8615e46118452e2b79bee38b817ca5`
- Build receipt file SHA-256: `a8f8b367e5c1b94001b63b733c2f7a6b5b5976c5fe6be5f6d44348499ce6404b`
- Exact binary SHA-256: `c520ebd8f937e7f58c47c8f152b125c579faf2cc7c614814fe4a9b762b39ebb6`
- Run identity: server epoch 5145751843064976, attempt 2, route generation 3

Do not promote Canary28 to DVC acceptance data.
