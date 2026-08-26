# Magmaw Canary35 Drudge combat-envelope handoff

Canary35 ran the exact clean source commit `988d5e8fdd044402d2e5c85766a9c0576e8177e8` with the queued coordinator build. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and failed closed on the death-loop watchdog after 511.479 seconds. Five deaths were eventually observed, seven members remained alive at the controller's terminal snapshot, Magmaw was not reached, and no forbidden assistance occurred. The worldserver exited normally and cleanup proved zero bots and leases.

## What the prior repair proved

The scoped movement reference-floor handoff worked. Deduplicated Canary35 trace contains zero `route_destination_path_floor_gap` decisions. Native point movement was active and the matching-path executor preserved it between decision ticks. Do not reopen generic floor validation, exact endpoint ordering, movement lease expiry, or set-and-forget point execution.

Canary35 also executed 56 guarded `drudge_lane_single_target_action` decisions, so the earlier safe-member offense repair is active. The new failure is downstream of those repairs.

## First actionable runtime edge

`drudge_dynamic_group_safety_has_no_maximum_combat_envelope_and_accepts_rush_displaced_members_outside_line_of_sight_and_effective_range`

`GroupPositionSafe` requires minimum distance from both live and home source positions, the correct lane side, and same-lane peer spacing. During dynamic landed-Rush recovery it then accepts that geometry without requiring the member to remain within useful range of its assigned live Drudge or its declared lane anchor.

Affliction warlock `30008` proves the missing upper bound. At native observation 5 it was at `(-343.177, -126.937)`, 58.29 yards from its declared slot-8 anchor and 66.58 yards from its assigned live Drudge. It stayed between 49.12 and 58.29 yards from the declared anchor and between 58.66 and 68.54 yards from the assigned Drudge through observation 18. These observations were nevertheless recorded as lane-safe, spacing-safe, and exact-roster reseparated. Its combat attempt remained `native_no_line_of_sight`.

The resulting trace repeatedly entered `drudge_native_charge_lane_reseparate`. The final pre-death cycle ran from sequence 1475 through 1516, followed by the death at sequence 1518. The movement snapshot showed a native point path with progress, so the decision label is not proof of path restart. The missing safety predicate lets a remote destination or remote live position close recovery while the bot cannot contribute damage or receive reliable support.

The Drudge contract already requires `split_seed_max_range_yards = 35.0`. That value is the existing bounded useful-combat range for this node and should be reused. Do not introduce a second unpinned distance.

## Bounded repair contract

- Add a typed Drudge seed combat-envelope predicate: a living configured seed-roster recovery member and any selected recovery candidate for that member must be no farther than `ValidationRouteSplitSeedMaxRangeYards` from its assigned live lane source. Non-seed members retain their current class/role range behavior.
- Apply the predicate to `GroupPositionSafe`, including the dynamic landed-Rush early-acceptance branch.
- Apply the same predicate before native path search and candidate caching so the brain never selects or reuses a destination that cannot satisfy the completion predicate.
- A remote member must remain unsafe and receive a path toward a deterministic declared/fan candidate inside the envelope. A member already inside the envelope retains the existing set-and-forget movement and safe-member offense behavior.
- Emit one distinct trace rejection such as `drudge_anchor_combat_range_unsafe` for an otherwise valid candidate outside the envelope. Preserve existing source-union, lane, spacing, exact endpoint, floor, tank-separation, and path checks.
- Keep this concern separate from `native_full_wipe_only`. Do not resurrect partial deaths or weaken native wipe fidelity to hide the pre-death positioning defect.
- Add deterministic replay/static coverage for the observed 66.58-yard failure, the exact 35-yard boundary, a normal declared slot-8 point inside the envelope, cache reuse, candidate rejection before path search, and ordinary in-range safe-member offense.
- Keep every C and C++ source and header below 1,000 lines. `BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp` is 990 lines, `LaneSelection.cpp` is 994, and `Actions.cpp` is 998, so extract the combat-envelope concern rather than growing those files past the limit.

Do not widen maximum spell ranges, teleport, force movement, alter Drudge AI or damage, grant line of sight, change healer throughput, force resurrection, manufacture a clear, or globally constrain unrelated movement.

## Deterministic acceptance

1. The observed member point 66.58 yards from its assigned live Drudge is not group-safe even when minimum source distance, lane side, and peer spacing pass.
2. A configured seed-member recovery candidate beyond 35.0 yards is rejected as `drudge_anchor_combat_range_unsafe` before native path search and cannot enter the anchor cache; non-seed members are unaffected.
3. A candidate at or inside 35.0 yards retains the existing source-union, lane, spacing, floor, endpoint, and native-path checks.
4. The declared slot-8 anchor remains admissible under the recorded source geometry when all existing predicates pass.
5. Matching active point movement remains set-and-forget, and safe in-range members still reach the guarded single-target action path.
6. Focused Drudge and movement tests pass, `git diff --check` passes, and all touched C/C++ files remain below 1,000 lines.

## Immutable Canary35 evidence

- Source commit: `988d5e8fdd044402d2e5c85766a9c0576e8177e8`
- Source tree: `47a5a048ecdbc5c3a907a79939479510a694c73a`
- Binary SHA-256: `fb68ad45faca7dc06e83b15e47db931b963ab3f9681e0c321ffc61c5bb1b3d9f`
- Build receipt: `/tmp/trinity-magmaw-988d5e8fdd-build.33mVAV/worldserver-build-receipt-valid.json`
- Build receipt file SHA-256: `738f808c4bf0430eab5544db4678bc9c42f089a9166b4bd83635759e8026937b`
- Build receipt canonical SHA-256: `ab25ed600da8d3fc20254d510293267b378ef1384b784b9bbdcf4771d03543a2`
- Report: `/tmp/trinity-magmaw-988d5e8fdd-canary35.Df22QX/canary35-run/capture/report.json`
- Report canonical SHA-256: `2c719713a9983deee859c19c860c3c969a3e37d531afd22eee52020c3dfee1c0`
- Report file SHA-256: `96a33235669d52fd8a5a520b4b26740c6e14359bd32ccc998534bfe81dc10dae`
- Raw trace SHA-256: `e3674b5c14dc78299bb8bb0b64364c2ee47a26c52625c0b465cdcc72958a8eec`
- Server log SHA-256: `0351c86edf4983eb40b88a6386d77ee12a116ace88855fef9cef25d3a4f5aecb`
- Route scope: generation `3`, node `bwd.magmaw.drudges`, manifest index `2/4`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, entrance and Chainwielder clear, Drudges incomplete, Magmaw not reached
- Deduplicated trace: 1,108 ordinary lane-reseparate decisions, 269 lane-violation reseparate decisions, 56 guarded single-target actions, 20 source-union path rejections, 19 strict tank-recovery path rejections, zero generic destination floor-gap rejections
- Evidence demultiplexing: 180/180 retained rows bound, zero rejected or unchecked
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`

The next owner is `raid-bot-runtime-implementation`. It may implement this one trace-backed combat-envelope repair and run focused tests only. A separate coordinator must review and commit it, obtain a new exact queued build receipt, provision a fresh ten-player roster, and run Canary36 under the completion watchdog.
