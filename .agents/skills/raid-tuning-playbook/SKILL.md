---
name: raid-tuning-playbook
description: The measure-change-measure loop that raises raid-bot kill DPS to Warcraft Logs parity. Use for every "implement/tune <boss> <mode> bots" request after startup, and whenever you choose, test, measure, keep or revert a bot change. Defines the finish line, the DPS metric, every threshold, the noise rule and the risk tiers.
---

# Raid tuning playbook

**Goal:** on the requested encounter, every non-healer bot's kill DPS reaches
Warcraft Logs (WCL) parity with lawful gear and native game rules. A kill is
the measuring harness, not the goal.

## 1. Start

1. In the checkout holding `master`, run
   `pixi run python -m tools.raid_program.raid_workloop start "<request>"`
   (for example `start "implement magmaw 10n bots"`). To continue the selected
   scenario, run `... raid_workloop resume`. Startup checks, graph commands and
   reviewer mechanics are in [trinity-orchestrator](../trinity-orchestrator/SKILL.md).
2. Open the target file `experiments/configs/raid_targets/<scenario>.json`
   (schema `raid_target_v1`), for example `blackwing_descent_10n_magmaw.json`.
   It lists each actor, its spec, its matched WCL reference and the finish line.
3. Run `pixi run python -m tools.raid_program.scoreboard verdict --scenario <scenario>`
   to see which actors pass, fail or have no reference.
4. Missing research, native scripts, rosters or runtime scenarios are
   implementation work: route them with [raid-performance-loop](../raid-performance-loop/SKILL.md).
   Never borrow another difficulty's result.
5. Check that the boss is Blizzlike before trusting any DPS or HPS ratio. Every
   run reports `encounter_fidelity` (report.json, and one line in
   `scoreboard show`): the preflight compares each engaged creature's
   `DamageModifier` with `experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json`,
   and `boss_melee` compares the boss's after-attacker melee with the WCL
   samples. An upstream migration set every creature's `DamageModifier` to 1,
   so an uncalibrated or mismatched boss is open fidelity work (the scenario's
   `encounter_damage_fidelity` requirement): calibrate it from matched WCL
   damage stages, stage the migration in `sql/custom/staged/world/`, and
   record it in the registry.

## 2. Finish line, metric and thresholds

**Finish line.** Each non-healer actor's mean encounter-window DPS over 3 kills
is at least 0.95 × the median matched WCL DPS for its spec, every kill is a
native clear, and there are 0 deaths in the boss window. `scoreboard verdict`
computes this from the target file. Status `no_reference` (Survival today)
means the matched WCL reference is missing: that is reference work to do, not a
pass. Healers have no DPS target; they pass with the encounter.

**DPS** means encounter-window DPS: the actor's originated damage from the first
to the last originated hostile damage in the boss window, divided by that
window, with pet and guardian damage counted for the owner. Report fields are
`encounter_window_dps` and `encounter_window_party_dps`. `dps`/`party_dps`
(in-combat seconds), `active_dps`, route wall-clock rates and
`capture_duration_sec` are diagnostics and are not comparable with WCL.

Each threshold has one meaning:

| Value | Meaning | Applies to |
| --- | --- | --- |
| 95% of WCL | The finish line above | `scoreboard verdict`, per non-healer actor |
| 75% of the hard reference | Per-class dummy qualification floor: one best DPS spec per class must reach it (Phase 8); for Death Knight prefer and keep optimizing Unholy | Isolated dummy calibration only |
| Two-sided 95% Welch t | Noise rule (step f) | Every keep/revert decision |
| 300 s | Exact scoring window of isolated training-dummy calibration | Never a raid or dungeon timer |
| 10 | Failures of one edge before the graph demands a changed hypothesis | Graph routing |
| 95% of self-provided WoWSims (`dps_gate`) | Legacy gate, checked only when a graph assessment cites no scoreboard verdict; not the finish line or a tuning target | Legacy graph assessment |
| 85%, 92.3%, "75/85% flags" | Historical; ignore | None |

## 3. The loop

Work one actor at a time in the tuning order (section 5). Only the coordinator
runs live kills; workers never launch a server. Each pass:

**a. Smoke kill: prove the harness.** Print the plan with `--dry-run`, then run
`pixi run python -m tools.raid_program.scoreboard run --scenario S --label smoke-<short-sha> --kills 1`.
The scoreboard runs the full-route manifest (entrance, trash and boss on one
worldserver) under the completion watchdog. It passes when the boss dies
natively and cleanup completes. Do this once per session and after every
`shared_runtime` change. If it fails, repair the harness before any tuning;
never switch to a boss-only slice.

**b. Baseline batch.** `scoreboard run --scenario S --label base-<short-sha> --kills 3`
on the unchanged build, then `scoreboard show --scenario S --label base-<short-sha>`.
Reuse an existing label when the binary, database profiles and configuration are
unchanged; `run` refuses to add kills to a label that already has some, and it
runs a pinned copy of the binary (`/tmp/worldserver-<sha12>`, delete it once the
label is settled). `--worldserver PATH` measures another binary. Add an already
completed run with `scoreboard ingest --scenario S --label L --run-dir DIR`
(or `--summary FILE`).

**c. Pick the gap.** `show` gives each actor's ratio to its target. For the
current actor, first read its open entries in the
[error ledger](../../../docs/bot_raids/error_ledger.md); they hold proven findings
and rejected approaches. Then rank its spell/component gaps with
`evidence_view compare --wcl` and take the largest. Name one mechanism from
retained evidence (idle or GCD waits, an ability never submitted, low uptime,
target/range/LOS loss, duty cost, deaths), using `events` for detail
([evidence views](../raid-rotation-review/references/evidence-views.md)).
Stop reading when you can say "changing X should raise actor A's DPS because Y".

**d. Make one change.** Make the smallest change that addresses that mechanism,
using the specialist skill that owns it (routing table in raid-performance-loop).
Classify its risk tier (section 4) and complete that tier's checks. Commit it,
so each label maps to one commit.

**e. Measure a batch.** `scoreboard run --scenario S --label <change-label> --kills 3`
with the baseline's route, roster and configuration. Nothing else may differ
between the two labels.

**f. Keep or revert.** Run
`scoreboard show --scenario S --label <change-label> --vs <baseline-label> --actor <target-actor-id>`.
With at least 3 counted native-clear kills per label, `show` runs a two-sided
95% Welch t-test per metric: **improved** or **regressed** when |t| exceeds the
critical value it prints, otherwise **within noise**. With 3 kills only large
effects (roughly 7% of party DPS) are detectable; use `--kills 5` for smaller
expected gains. Keep the change only if party
DPS or the target actor improved, no non-healer actor regressed, boss-window
deaths per kill did not increase, and every kill of the new label is a native
clear. Trash deaths the party recovers from are context only; a trash wipe that
stops the route already fails the kill.
Otherwise revert it: revert the commit, and for SQL profile rows apply the
reverse migration and read the rows back. Within noise means revert. A kept
change's label becomes the new baseline.

**g. Record and clean up.** The scoreboard appends each kill to
`artifacts/cata_raid_program/scoreboard/<scenario>.jsonl` and publishes, verifies
and evicts run evidence through DVC. Confirm it reported success and that
`dvc status` shows nothing left to push; if archiving failed, run
`scoreboard archive-pending --scenario S`. A kill lost to infrastructure (no
report, never reached the boss) is excluded automatically; any other exclusion
needs `scoreboard void --scenario S --kill-id K --reason TEXT`, which is audited. Add one line (label, Δ, kept or
reverted) to each ledger entry you touched. Record the graph steps with the
commands `raid_workloop` returns: write the validate receipt with
`pixi run python -m tools.raid_program.graph_acceptance receipt --label <label> --cleanup-verified`,
and at `assess` cite the verdict written by
`pixi run python -m tools.raid_program.graph_acceptance verdict --label <label>`,
because actor and encounter requirements close only on a passing scoreboard
verdict. Run `scoreboard verdict`, then continue with the next gap of this
actor, or the next actor once it passes.

If two changes aimed at the same mechanism both land within noise, capture the
missing observation (one diagnostic run or telemetry field) and state what it
will decide before trying a third.

## 4. Risk tiers

Set `risk_tier` in the graph plan (or unit); an unset tier counts as
`class_native`. Run only that tier's checks; plan-drift review is never required.

| Tier | Covers | Required before the measurement batch |
| --- | --- | --- |
| `profile` | Rotation/action-profile rows, SQL data, configuration | Affected tests pass |
| `class_native` | Class/spec C++ in `src/server/game/Bots` | Tests, one independent reviewer in a separate session, build |
| `shared_runtime` | Shared bot runtime, arbitration, movement/recovery, harness and validation tooling | Tests, full independent review (diff, every affected caller and harness behavior), build, one smoke kill |

Every tier then gets one measurement batch (step e). A `profile` unit skips the
build when its plan cites `reuse_build` (a verified build with no native change
since); a change that touches native code counts as at least `class_native`.
Reviewer procedure and build commands are in trinity-orchestrator; plan fields
are in `docs/bot_raids/development_graph.md`.

## 5. Magmaw 10N now

Scenario `blackwing_descent_10n_magmaw`. The spell-queue build (label
`spellqueue-b8a897`) averages 236k encounter-window party DPS over three kills
against WCL about 246k. Those kills, and every earlier one, were measured while
each in-combat heartbeat froze the world thread for 3.6–12.3 s (11–21% of the
boss window), so they are not comparable with kills on the fixed harness:
re-baseline (step b) once runs report no boss-window stalls. Single kills vary
by about ±10%, which is why every decision uses batches. Order:

1. **Blood DK tank**, about 45–60% of WCL. Compare with
   `magmaw_wcl_dps_reference_v1.json` and `magmaw_wcl_cast_timelines_v1.json`
   in `experiments/configs/cata_raid_encounters/blackwing_descent/`: rune
   spending, Heart Strike, Death Strike, Rune Strike, Dancing Rune Weapon,
   diseases, Vengeance, main-tank uptime and exposed-head coverage. Threat and
   survival are safety checks, not substitutes for damage.
2. **Balance**, about 70–80%; include Mushroom placement and duty cost.
3. **Elemental**, then **Survival** (which first needs its WCL reference), then
   **Affliction**, then any other actor still below the finish line.

## 6. Constraints that always apply

- **Lawful play.** Gear comes only from the pinned, obtainable profile. Never
  invent auras, buffs, procs, damage multipliers, forced targets or casts,
  health/resource refills or teleports. Native pathing owns terrain: no bot Z
  steering, global tolerance loosening or MMAP workarounds. Change native
  damage, coefficients or stat math only with evidence that the native value is
  wrong (pinned spell or client data, or WoWSims source), never to fit a gap.
- **Raid clock.** Raids and dungeons use the generated completion-watchdog plan
  with typed terminal reasons: clear, stall, repeated decisions, death loop,
  infrastructure loss or interruption. There is no 300-second raid success
  timer; reaching an emergency wall-clock cap is a failure.
- **Builds.** Never build while a worldserver runs. Build only through
  `workflow_build run`. Documentation and progress commits need no rebuild.
- **Source size.** C/C++ files stay below 1,000 lines; see AGENTS.md for the hook.
- **Storage.** Python runs through Pixi, code and configuration live in Git,
  generated data lives in DVC, and as little as possible stays on disk.
- **Tests.** Report every earlier failing test, even when a narrower rerun
  passes, and classify its relevance.
- **Models.** Use the model preference in AGENTS.md, with implementer and
  reviewer in separate sessions. Jev (hosted) is optional and only chooses
  between the top two ranked gaps; Laya (local) shadows Jev on the same packet so
  their signal can be compared. The default backend runs both:
  `pixi run python -m tools.raid_program.bot_improvement_advice --comparison <file> --top 2 --output <dir>`.
  After the measurement batch, log both picks with
  `pixi run python -m tools.raid_program.jev_outcomes append --unit U --candidate G1 --candidate G2 --jev-pick G --laya-pick G --chosen G --label-before B --label-after A --party-delta D --actor-delta D`
  (omit a pick when that model was offline); `jev_outcomes summary` shows
  whether either model's picks gain DPS.

Stop only when `scoreboard verdict` passes every actor, the user limits or stops
the task, or a demonstrated external blocker prevents all remaining work.
