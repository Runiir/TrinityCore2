# Magmaw Drudge recovery-latch handoff

## Closed evidence

- Capture: `/tmp/trinity-magmaw-ae1cfe9318/canary1/capture/report.json`
- Source commit: `ae1cfe93184a3d623c35120e55bba2c488389aa6`
- Source tree: `398e380805da0838798bde87abe00e62d8e50b2b`
- Binary SHA-256: `c0652761093c60b02ab0ac701fcca6bdd707ba29b6ab28d68c027c5b9d1ad97d`
- Report file SHA-256: `64add35053b9607c7d62e08ec28e50969d0cf7850cc9a97549d33d499db7cba1`
- Normalized trace SHA-256: `dae87ac33b393a3cc9388d7221e69df910becd7fbb912f50955fcd13f8fce4ac`
- Result: `gameplay_failure / repeated_decision_watchdog` at `bwd.magmaw.drudges`, with cleanup, demultiplexing, and forbidden-assistance gates passing.

The run cleared Chainwielder and reached the Drudge pair with all ten bots alive. One native Rush landed from each exact source on a cross-lane DPS target. Both tanks reached their recovery anchors, but the downstream tick recomputed the volatile exact-recovery predicate after one tank had rebound toward combat. The route then repeated `drudge_tank_recovery_anchor_strict_path_rejected` and never recorded exact-roster reseparation.

## Implemented repair

- Required fix commit: `4975d73314deb3eb5b8f53bc6e3bbd4edfdfd6ec`
- Required fix tree: `7c96409e7cf6ed6bfed0758359365dc6ec8315fa`
- Scope: downstream Drudge recovery gating consumes the already proven, observation-scoped two-tank recovery latch.
- The exact two-tank proof is still required to open the latch.
- Combat return still requires exact combat paths and anchors.
- Completion still requires exact roster reseparation.
- No teleport, forced movement, forced threat, resurrection, encounter mutation, or manufactured outcome was added.
- Related coordinator verification: 220 tests passed.

The same commit also contains trace-burst coalescing so a forced terminal trace remains fail-closed without losing non-repeatable decisions. All touched C and C++ sources and headers remain below 1,000 lines.

## Required live verification

Build identity is already available at `/tmp/trinity-magmaw-4975d73314/build/worldserver-build-receipt-v8.json` with binary SHA-256 `c99ee8aa9fa31c9a7186906232562199fcfadc396d157e9325e1f9453359ef57`.

Provision a fresh exact ten-player `blackwing_descent_10n_magmaw_diagnostic` cohort and run one completion-watchdog shard. Observe:

- one native Rush from each source lands on a valid cross-lane target;
- both exact tanks reach recovery and the latch stays open on later ticks;
- the route does not return to the recovery preflight loop after the latch opens;
- exact-roster reseparation is recorded;
- the Drudge node advances toward Magmaw without deaths or forbidden assistance;
- trace demultiplexing and cleanup pass.

Do not claim Magmaw completion without boss-death evidence. Do not claim current-standard acceptance until two consecutive fresh full route clears are published and remotely verified.
