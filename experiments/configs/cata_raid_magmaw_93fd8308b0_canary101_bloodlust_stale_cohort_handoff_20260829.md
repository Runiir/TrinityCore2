# Magmaw Canary101 stale-cohort Bloodlust handoff

## Exact diagnostic evidence

- Source commit: `93fd8308b0043a730086a856a898a97a135d57d7`.
- Worldserver SHA-256: `b9b391c7d90f6fe063f2d8126a898b5329621bee9b7c2daed2ca4ef8858015b8`.
- Debugger run: `/tmp/trinity-magmaw-gdb-canary101.5RrSiZ/run`.
- Report SHA-256: `339b9fc5d13d00078a4185d81e7b86b4d193530fceee0762fcff4a88b4a7a26f`.
- Worldserver log SHA-256: `4404a089df68156a2db8d33f79c7915a46364542be11d6c0e2a094296c16801c`.

The non-certifying debugger replay cleared the Chainwielder and both Drudges, reached route generation 4, engaged Magmaw, and stopped at 361 seconds. It had three trash kills, zero bot deaths, and 13,230,593 party damage on the Magmaw node. The debugger stopped at the first `std::__throw_out_of_range`.

The exact main-thread stack is:

1. `std::__throw_out_of_range(char const*)`
2. `BotWorldPopulationMgr::Cohort()`
3. `BotWorldPopulationMgr::Party()`
4. `BotWorldPopulationMgr::SubmitMagmawBloodlustCandidate(BotUpdateContext&)::{lambda()#3}::operator()() const`
5. `BotActionArbitration::Kernel::Resolve()`
6. `BotWorldPopulationMgr::RunBotDecisionKernel(BotUpdateContext&)`
7. `BotWorldPopulationMgr::UpdateBot(...)`

The throw occurs inside the deferred Bloodlust candidate. At least one callback reached `Party()`, which used `_cohorts.at(_selectedCohortId)`, after the callback's selected-cohort context was no longer valid.

## Repair contract

Repair only the deferred Magmaw Bloodlust candidate's cohort/party lifetime and lookup boundary. Inspect all callbacks and helper lambdas captured by `bloodlust.Attempt`; do not leave an indirect `Cohort()` or `Party()` lookup that depends on mutable global cohort selection during resolution. Fail closed with a typed `NotApplicable` outcome if the original cohort, bot, encounter snapshot, route generation, attempt, wipe generation, or owner identity is no longer current.

Add focused regression coverage that constructs or statically proves the deferred candidate does not call `Cohort()` or `Party()` through mutable selection. Preserve normal Bloodlust submission for an unchanged valid Magmaw context.

Do not change class rotations, damage tuning, encounter mechanics, movement, route geometry, watchdog thresholds, or evidence handling. Do not generalize `Cohort()` globally without separate evidence. Do not run a live shard inside the specialist work unit.
