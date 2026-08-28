# Magmaw Canary100 crash-stack handoff

## Identity and closed outcome

- Source commit: `93fd8308b0043a730086a856a898a97a135d57d7`.
- Worldserver SHA-256: `b9b391c7d90f6fe063f2d8126a898b5329621bee9b7c2daed2ca4ef8858015b8`.
- Run: `/tmp/trinity-magmaw-93fd8308b0-canary100.cIXN4o/run`.
- Report SHA-256: `f4ad2a970957db7f134aa1f84c4869fce393e4123a3a2bfb0243071d4c10ed5a`.
- Worldserver-log SHA-256: `e67faaaf06db9cad55c0a5f3838662c785ba8708dba4fa4207ce1f70b3274355`.
- Controller result: `worldserver_process_exit`, return code `-11`.

Canary100 cleared the Chainwielder and both Drudges with all 10 bots alive and zero generation-2 Drudge contamination. It reached Magmaw and continued until one protection-paladin tank died. The other nine bots remained active when the worldserver exited. The final retained combat snapshot contained 14,938,582 party damage.

Canary99 previously printed `std::out_of_range`, `map::at`, and signal 6 before the same controller-level nonzero exit. Canary100 retained no exception or signal text, so the exact crashing caller remains unproven.

## Diagnostic contract

Run one fresh, non-certifying Magmaw replay with the exact worldserver under a debugger wrapper. Stop on either `std::__throw_out_of_range(char const*)`, `SIGABRT`, or `SIGSEGV`, and retain `thread apply all bt`. The wrapper must preserve console stdin so the normal completion-watchdog remains the sole controller. Do not use the debugger run as acceptance evidence.

After the stack identifies a source location, repair only that proven unsafe edge with total typed handling and one focused counterexample. Do not change rotations, encounter strategy, route coordinates, movement policy, watchdog thresholds, or evidence commands.

The observed parasite movement floor mismatch (`requested z=210.948`, sampled floor `-93.7013`) remains a separate later gameplay work unit. Do not mix it into the crash repair.
