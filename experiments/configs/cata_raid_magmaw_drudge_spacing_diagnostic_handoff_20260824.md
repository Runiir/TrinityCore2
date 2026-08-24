# Magmaw Drudge reseparation receipt handoff

The exact `49e8f8bff809e8d685653d127dcaed1d0bf2724e` canary `canary1r3` failed closed under the completion watchdog after 336.787 seconds. It cleared the entrance and Chainwielder, reached `bwd.magmaw.drudges`, and stopped on `death_loop_watchdog` with three deaths. It did not reach or kill Magmaw. Identity, telemetry demultiplexing, cleanup, and forbidden-assistance gates passed. This is failed diagnostic evidence, not a clear and not acceptance data.

The first bounded global spacing failure named member 30008, candidate 0 at `(-311.5, -78)`, with `source0_safe=false`, `source1_safe=true`, `lane_safe=true`, `same_lane_spacing_safe=true`, and `group_position_safe=false`. No peer caused that failure. The receipt was scoped to attempt 2, wipe generation 0, route generation 3, and accumulated 95 suppressed repeats.

That global receipt is not a lethal attribution. Member 30008 survived and later produced 487 `native_movement_submitted` outcomes. The retained trace did not bind any individual submission to its selected candidate, active native path, progress, arrival, or reseparation closure. The deaths of members 30003, 30006, and 30007 therefore do not justify a movement behavior patch from this run.

Commits `97718f44ed` and `72f8318c9c` add bounded diagnostic-only reseparation receipts. Each movement attempt receives a deterministic submission ID and retains exact attempt, wipe, route, map, instance, source, member, candidate, safety, arbitration, active-path, native-motion, progress, arrival, and closure fields. Repeated submissions against one selected anchor remain distinct. Commit `e600346648` widens `experiment_bot_events.context_json` to `MEDIUMTEXT` so the full receipt payload is stored without truncation. These changes do not alter candidate admission, movement arbitration, encounter state, damage, threat, healing, or death recovery.

The next run must build the exact clean commit `72f8318c9ce12f2470ef387761ccc98885f75aa2`, tree `1f80f706c748b21fd3fbd218f1fd213951f6ba34`, through the shared queued coordinator. Provision a fresh ten-player Magmaw diagnostic roster and run one completion-watchdog shard. There is no fixed raid success timer. Extract the first per-submission divergence between selection, arbitration, active path, progress, arrival, and closure, then route at most one trace-backed behavior repair. Do not teleport, force movement or threat, revive bots, mutate native encounter state, or manufacture an outcome.

Failed local evidence:

- Report: `/tmp/trinity-magmaw-49e8f8bff8/canary1r3/capture/report.json`
- Canonical report SHA-256: `05eeb9822472df389d91b9979e47ffdb71c6f404dc2426f1b7cab2a059661ba6`
- Report file SHA-256: `53b918d08ef17c638c8cffc22efff6756cca24f405f1e735105586e25fdbee6b`
- Normalized trace SHA-256: `6f67e860d2af275077c1d042ce4020ddb931f33045c795a7562987f1c5b1d392`
- Server log SHA-256: `527c52d90f767adb200a76536485ebcdfb5693336d7978cd4c94668182d78f25`
- Exact build receipt: `/tmp/trinity-magmaw-49e8f8bff8/build/worldserver-build-receipt-v8.json`
- Exact binary SHA-256: `ba6850b989664f3539e66ac6649bd6f5c82ff227244be77dca51feadf63a61e3`

Do not promote this failed run to DVC acceptance data.
