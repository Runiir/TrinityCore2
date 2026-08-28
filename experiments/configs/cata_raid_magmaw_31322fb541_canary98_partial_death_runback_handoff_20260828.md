# Magmaw canary 98 partial-death runback handoff

- Runtime source commit: `31322fb541e7f3125465a856905c7016d5723acd`
- Coordinator commit: `e2219cb4fdc63aa26d25803334b4bcb0d8e587fe`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Binary SHA-256: `6e27dd39b3437e06153510748d44bad84f0c547418c13cfb8cf4f58a62815ca8`
- Report: `/tmp/trinity-magmaw-31322fb541-canary98.z80pE4/run/report.json`
- Report SHA-256: `17661f65af347440390f5201d2c934bd5a5c4348d42c9989b5a798bfeb4887ec`
- Heartbeat stream SHA-256: `45ffaece88e45688542f4a42061cc78b61249af749a8ec8216e81f16535c3b3c`
- Worldserver log SHA-256: `a4e0feeeca0dcb091b6a1537aa1f4942e1bf98fc2b1917f65208434ee8d7442f`

## Closed result

The exact replay did not repeat canary 97's `SIGBUS`. It cleared the Chainwielder and both Drudges in order with no future-encounter contamination. Protection Paladin `30001` died during the Drudge pack, released through native recovery, and moved on map 0 toward BWD's entrance. The ghost then stopped at `(-7482.93, -1383.73, 416.785)` while retaining an accepted recovery-owned native long path to `(-7542.91, -1184.93, 482.0)`.

The final diagnosis showed native current motion type `0`, native active motion type `19`, `is_moving=true`, `time_since_last_progress_ms=296092`, `time_since_last_path_change_ms=234557`, and `last_no_progress_reason=native_runback_no_progress`. The route stayed at `bwd.magmaw.drudges`, generation 3, with nine alive members and both Drudges dead. The completion watchdog ended the run after 300 seconds of semantic no progress. Return code was 0; this was a gameplay recovery stall, not infrastructure loss.

## Bounded repair hypothesis

The partial-death recovery loop preserves an accepted native generator after actual position progress has stopped, but its internal 30-second one-repath/terminal policy is not producing an observable repath or terminal edge. Repair the first policy-to-native-outcome edge so the same scoped recovery episode notices the stopped generator, submits exactly one fresh native path through the existing movement executor, and either resumes measurable position progress or emits its typed `native_runback_no_progress` terminal before the outer 300-second route watchdog.

Do not teleport, directly resurrect, manufacture route progress, change ghost speed, alter the route, suppress the death, or tune Drudge damage.
