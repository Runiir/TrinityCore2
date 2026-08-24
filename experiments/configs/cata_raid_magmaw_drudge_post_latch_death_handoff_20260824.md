# Magmaw Drudge post-latch death handoff

## Closed run

- Source commit: `4975d73314deb3eb5b8f53bc6e3bbd4edfdfd6ec`
- Source tree: `7c96409e7cf6ed6bfed0758359365dc6ec8315fa`
- Binary SHA-256: `c99ee8aa9fa31c9a7186906232562199fcfadc396d157e9325e1f9453359ef57`
- Build receipt: `/tmp/trinity-magmaw-4975d73314/build/worldserver-build-receipt-v8.json`
- Build receipt file SHA-256: `cb8ec8a2809fb6df875d6c9330786483fe186487c25067485738d88ed00276ae`
- Capture report: `/tmp/trinity-magmaw-4975d73314/canary1/capture/report.json`
- Report canonical SHA-256: `2eefff25c4bfbabc38b51495b8a3a84f82df3c8661e6ef6e2e6f003e95d15ca1`
- Report file SHA-256: `56fe09db1a027b5a2fcf299300b5a50f61a3ce4379943f1d25a6e24d37218b25`
- Normalized trace SHA-256: `8dc5a152fc28dff3f1d5a710aa2436fd13d389869fdbc8460d8a9322ccc18bcf`
- Result: `gameplay_failure / death_loop_watchdog` after 316.319 seconds.
- Cleanup, demultiplexing, identity, and forbidden-assistance gates passed.

The run cleared the entrance regroup and Chainwielder, then reached the Drudge pair with all ten bots alive. Ten native Rushes landed, five per source, on the intended cross-lane DPS targets. The native 20-second intervals were observed. Earlier observations recorded exact-roster reseparation, proving that the two-tank recovery latch fixed the prior edge.

The run then lost restoration druid `30003` at `1787580976143`, holy paladin `30004` at `1787580981427`, and fire mage `30006` at `1787580998739`. The controller stopped the run at the third death. Magmaw was not reached.

## First broken edge

The shared Drudge landed-Rush closure remains pending after the recovery latch opens. `RunFormationActions()` does not reach a true `LandedRushRecoveryComplete(...)` proof on every cycle. `NativeChargePending` therefore keeps the cohort in `drudge_native_charge_lane_reseparate` and prevents normal class actions.

Trace and status evidence:

- `profile_action_roster_guids` stayed empty;
- `health_sync_evaluated_roster_guids` stayed empty;
- health-sync hold fields stayed empty;
- immediately before the first death, bot `30003` reported `drudge_anchor_spacing_unsafe`, then `no_valid_profile_action`;
- another healer attempted adaptive support on `30003`, so the first edge is not a missing healer spell or a damage coefficient;
- trace deltas had no gaps.

## Bounded implementation

Owner: `raid-bot-runtime-implementation`.

Inspect and repair only the proof inputs and transition around `LandedRushRecoveryComplete(...)` and `CloseLandedThroughProof(...)` in `BotWorldPopulationMgrValidationRouteDrudgeActions.cpp`. Preserve exact recovery, exact combat-return, exact roster-reseparation, native-path, and no-cheat requirements. Do not alter healer priorities, spell coefficients, native Drudge damage, Rush targeting, native timers, or watchdog limits.

Acceptance requires every landed Rush to emit `drudge_native_charge_reseparation_complete`, all seven offensive slots to appear in `profile_action_roster_guids`, exact tank health-sync evidence to populate, no player death, and the Drudge route to terminate and advance under the completion watchdog.
