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
   to see which actors pass, fail or have no reference. It judges the baseline
   label recorded by `scoreboard baseline`; `scoreboard show` prints that label
   in its header.
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
| Two-sided 95% Welch t | Regression check of the keep rule (step f); a positive delta need not pass it | Every keep/revert decision |
| 5 kills per label | Batch size of every keep/revert comparison (`kills_per_batch`) | `scoreboard run --kills 5`, baseline and candidate |
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

**b. Baseline batch.** `scoreboard run --scenario S --label base-<short-sha> --kills 5`
on the unchanged build, then `scoreboard show --scenario S --label base-<short-sha>`,
and record it with `scoreboard baseline --scenario S --label base-<short-sha> --reason TEXT`
unless a recorded baseline on this build already exists.
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

**d. Make one mechanism's change.** Make the smallest change that addresses that
mechanism, using the specialist skill that owns it (routing table in
raid-performance-loop). When the actor is below 0.85 of its target, bundle the
diagnosed fixes for that actor from the error ledger into one batch: a single
5% fix cannot be told from noise at these kill counts, and the batches kept so
far were bundles.
Classify its risk tier (section 4) and complete that tier's checks. Commit it,
so each label maps to one commit.

**e. Measure a batch.** `scoreboard run --scenario S --label <change-label> --kills 5`
with the baseline's route, roster and configuration. Nothing else may differ
between the two labels.

**f. Keep or revert.** Run
`scoreboard show --scenario S --label <change-label> --actor <target-actor-id>`.
It compares against the recorded baseline (`--vs L` overrides). With at least 3
counted native-clear kills per label, `show` classifies each metric with a
two-sided 95% Welch t-test as **improved**, **regressed** or **within noise**,
prints the delta it could have detected at these kill counts, and prints
**keep**, **revert** or **insufficient_kills** (a side below `kills_per_batch`;
`--min-kills N` overrides it and the decision line says so). Keep when every
kill recorded under the new label is a native clear, boss-window deaths per kill did not increase, neither the party nor any
non-healer actor regressed, and the target actor's mean (party mean without `--actor`) is not
below the baseline. A within-noise positive delta is kept only when the
change's mechanism is visible in the candidate kills: the new ability was
submitted and landed, the named gap shrank or the rejection count fell. Check
that in the ranked gaps or with `evidence_view` before keeping. Otherwise
revert it: revert the commit, and for SQL profile rows apply the reverse
migration and read the rows back. A kept change's label becomes the new
baseline: record it with
`scoreboard baseline --scenario S --label <change-label> --reason TEXT`
(it refuses a label with a wipe or a boss-window death unless `--force`).
Trash deaths the party recovers from are context only; a trash wipe that stops
the route already fails the kill. The random Massive Crash side moves casters
by several thousand DPS; read the RNG line and never credit a caster delta to a
change that did not touch that caster.

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

If two batches aimed at the same mechanism both leave the target actor's mean
flat, capture the missing observation (one diagnostic run or telemetry field)
and state what it will decide before trying a third.

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

Scenario `blackwing_descent_10n_magmaw`. The baseline label is recorded by
`scoreboard baseline` and printed in the header of `scoreboard show`; compare
every change against it and record a kept change as the new baseline. Kills
vary by about +/-3-4% even on a clean harness, and the random Massive Crash
side moves casters by several thousand DPS, so read the RNG line `show` prints
before trusting an actor delta.

Actor status comes from `scoreboard verdict`. The next diagnosed fix for each
failing actor is its open row in the error ledger (TANK-, DPS-, HEAL- IDs);
work the failing actors from the largest gap down and bundle per actor (step
d). Mangle is the fight's lethal moment for the sole Blood tank; any change
that touches tank cooldowns, healer movement or pincer riders must keep
boss-window deaths at 0. Encounter fidelity: only Magmaw 10N's melee is
calibrated (ENC-007 lists the other difficulties, the adds and the route
trash).

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
  reviewer in separate sessions. Model advisors (Jev, Laya) are not part of the
  workflow.

Stop only when `scoreboard verdict` passes every actor, the user limits or stops
the task, or a demonstrated external blocker prevents all remaining work.
