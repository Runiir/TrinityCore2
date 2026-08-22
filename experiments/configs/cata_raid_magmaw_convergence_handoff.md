# Magmaw shard convergence handoff — session state

Branch test/ox-aplha-det-bot-workflow. Coordinator-owned pipeline proven working:
build receipts gate-bearing per commit, prep/readback green, captures produce
typed immediate gameplay failures with full telemetry.

## Fixed chain (all worker-authored, runtime-confirmed unless noted)
1. dd554843f7 raid-seed entry + assert hygiene (coordinator-era)
2. 5d0e566672 adopt seed raid group (w6)
3. 1aad594117 LFG solo-disband killed seed on map entry (w8)
4. 9bfca50ead hunter pet pin -> cohort receipt freeze (w9)
5. 3144164122 gear identity -> cohort receipt freeze (w10)
6. dd554843f7 attempt-restart stale Raid reset (w11) — admission ACTIVE reached
7. 8ef7d2f25c gem padding canonicalization -> immediate typed failures (w12, runtime-confirmed)
8. 8ef7d2f25c drudge ownership requires engagement (w13): Z-transitions 22->6
9. 198bac19d6 non-tank offense hold until seed staged (w15): pet no longer dies early
10. 43521ba995 lane-tank threat window pre-staging (w16): staging completes,
    charges prepared 2/2

## Current blocker (run 43521ba995, typed gameplay_failure @293.9s)
validation_active_hunter_pet_missing again. Seed closed=true failure=true;
charges PREPARED_COUNT=2 DELIVERED_COUNT=1 — second lane charge not delivered.
Pet dies in extended fight window before seed completes.

## Next work unit (worker #17)
Diagnose why second lane charge never delivers + why hunter/pet dies in the
window: raw.jsonl at artifacts/cata_raid_program/phase1_foundation_43521ba995_
magmaw_diagnostic_20260821/. Check charge queue interval semantics
(charge_native_interval_ms=20000), lane tank threat retention post-first-rush,
healer coverage of tanks/hunter during seed window. Fix minimal edge; keep
typed fail-closed gates.

## Stop conditions (user-defined)
- One DPS spec on par with WoWSims reference (affliction 31312.97; canary rerun
  pending — fixes landed, unproven live).
- Bots clear 1 BWD boss flawlessly (Magmaw = node 3 of 4; currently node 2).

## Process rules in force
- Workers own specialist fixes; coordinator owns builds/captures/publication.
- Every native fix carries a runtime_verification_plan + post-capture verdict.
- Receipts committed each cycle; run artifacts DVC-published (dd55 + 8ef7 done).
- Known pre-existing test debt: 2 capture source-text assertions
  (ValidationRouteDrudgeAnchorAttemptId) + BotWorldPopulationMgr.h >1000-line
  bound — stale, unrelated to current edges.
