# Handoff: faster lawful Magmaw kills and agent supervision

For resuming after this handoff, first run
`pixi run python -m tools.raid_program.raid_workloop resume` and read
[the saved development workflow](development_graph.md). The handoff below is a
historical snapshot; saved progress and newer evidence own the next action.

## Objective and stopping point

The parent objective is to improve all represented bots until Magmaw damage,
activity and kill speed are credible against Warcraft Logs, then reuse the
workflow across Cataclysm classes and encounters. A kill alone is insufficient.
Keep lawful player gear, native spell mechanics, assignments and survival.
Do not inflate spell radii, damage coefficients or buffs to reach a DPS number.

The latest user requested a Jev/Laya checkpoint for worker code and a callable
skill checking the main orchestrator's plan for drift. That implementation and
its bounded trials are complete. They provide advisory judgments, not proven
automatic correctness. The user then explicitly requested this full handoff
and a stop. **Do not continue live work from this tab.** The receiving tab may
resume the parent DPS task when instructed.

## Worktree, source and processes

- Continue on master at `/home/runiir/Games/trinity-magmaw-parity`.
- `/home/runiir/Games/trinity-cata` remains the separate, dirty/ongoing
  `codex/magmaw-jev-canary` checkout at `60ae9760b4`. Preserve it and the other
  dirty JEV integration worktree. Do not reset or blindly cherry-pick them.
- `master` is the repository mainline; no separate `main` branch exists.
- Native potion/reporting changes are committed at `fe3dadce4d`. Worker and
  orchestrator checkpoints are committed at `cbe81b0ffc`.
- Read the final handoff commit on master for the current source. The latest
  **built and live-tested binary** is still source `50ec676cdb5b47f5edfd0a95046ba93c2317b89b`.
  The new potion exclusion has passed tests/review but has **not been built or
  live-validated**. Do not bind the old binary to the new source.
- Build receipt: `/tmp/magmaw-master-50ec676cdb-build-20260919.json`, also archived.
  Policy: `experiments/configs/cata_raid_build_resource_policy_fast4_v2.json`.
  Use the existing queued build workflow and exact policy/configure arguments.
- No worldserver remains running from these experiments. The existing
  authserver PID `2126966` was left running. Verify current processes before use.
- Local Laya remains healthy at `http://127.0.0.1:8000/v1/systemone`, CUDA/float16,
  package `0.3.3`, model `convaiinnovations/laya-typed-decisions`, revision
  `c5d78730f3493e4fe16d61507ef4b78eef7318cf`. Deployment:
  `/home/runiir/.local/share/trinity-laya`. Do not start a duplicate service.
- Hosted Jev uses the existing client and `JEV` from the original checkout's
  `.env`; do not copy credentials into reports. Pilot responses resolved to
  `jev-1.13.0`.

Use Pixi for Python. If the current worktree environment is unavailable:

```sh
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml --frozen python ...
```

Run that command with the **master worktree as cwd**. One coordinator owns
builds, DB provisioning, server lifecycle and DVC publication. Keep C/C++ files
below 1,000 lines; `BotWorldPopulationMgrCalibrationBot.cpp` is currently 992.

## Benchmarks and what counts as improvement

The last lawful reviewed raid baseline is `d495bd1556`: **117.523 seconds,
239,894.514 exact raid DPS, 14,412.302 exact HPS**, all ten alive. Its roster was
one Blood tank, three healers and six DPS. Do not describe this as a 2-healer run.
Historical shard89's 241,249.360 DPS used enlarged Mushroom targeting and is not
a lawful floor. The user explicitly rejected that change.

The later `696a8f6f38` cleared in **123.672 seconds, 228,230.950 DPS,
17,884.153 HPS**, all ten alive. Performance fell 4.86% from d495 and was not
accepted. Its full actor table and accepted narrow fixes are retained in
`docs/bot_raids/magmaw_dps_baseline_20260913.md`. Keep Blood, the bait Fire,
regular Fire, Survival, Affliction, Elemental, Balance and all healers visible.

Raid DPS uses originated hostile damage through native boss death, including
owned pets and excluding friendly damage and mirrored spell 79010 callbacks.
Compare the same pull-to-death interval. Retain body/head/add damage, phase
coverage, duties, target-switch latency, deaths, healing and downtime. DoT/pet
tails do not prove fresh owner casts. Mandatory bait/pincer work is not fully
recoverable casting loss. Check body reacquisition after head disappearance,
optional parasite legality, melee parasite avoidance and head/Bloodlust timing
against the current ledger and native timeline, not aggregate DPS alone.

WCL remains the encounter benchmark. Do not use rough 40k targets as matched
class floors. Use the retained source reports, gear and phase timelines in
`experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_cast_timelines_v1.json`
and the baseline document. Self-only dummy simulations are a separate controlled
diagnostic, not a replacement for a matched raid comparison.

## Exact dummy work completed in this run

Implemented `tools.raid_program.run_dummy_calibrations` and
`dummy_calibration_batch.py`. They run up to two independent native fixtures
on one worldserver, with per-spec requests, clocks, progress, full final
diagnostics and cleanup. They use private phases 32512/32513 at the same verified
geometry. Name filtering alone would not prevent shared debuffs or splash.

The target matches the pinned simulator: level 88, armor 11977, passive mechanical
raid dummy, 15-yard ranged geometry and exact 300,000 ms scoring. Its health follows
the pinned execute-threshold schedule; a permanently full-health city dummy
would be a different comparison. Raid/dungeon runs still use the completion
watchdog, never a fixed 300-second success timer.

Initial `b8e9803721` attempts failed before scoring because the first native
area update cleared the directly assigned phase. `50ec676cdb` initializes area
before phase assignment and reads current native phases rather than cached
spawn observations. All five windows then completed. Peer damage and scoring
continued after addressed cleanup, and both owned servers exited 0.

| Spec | Native exact DPS | Promoted mean | Current disposition |
| --- | ---: | ---: | --- |
| Survival | 35,394.117 | 36,534.932 | Close aggregate accepted by user for moving forward; reference omits legitimate cooldown actions. |
| Fire | 35,324.493 | 35,138.962 | Close aggregate; actual extra profile potion overlaps fixture ownership. |
| Affliction | 27,820.990 | 31,312.967 | Formal setup admitted; per-event/cadence review retained. |
| Elemental | 30,763.317 | 36,999.280 | Formal setup gate passes; reference/profile and stat-observation issues remain. |
| Balance | 30,205.077 | 35,447.589 | Missing self buffs/passive proven; extra potion also observed. |

The current catalog is
`experiments/configs/wowsims_cata_dps_reference_requests_v1.json`, with pinned
WoWSims revision `70d87383a9b92f30fb9e370c4676d3ce33b6e6b6` and DVC bundle
`artifacts/all_spec_program/wowsims_exact_reference_bundle_pet_identity_v4.dvc`.
It contains 16 references/181 files. Embedded historical DPS and the legacy 85%
optimization threshold do not establish parity. Fire/Elemental/Balance lacked
detailed debug timelines; these were generated from their same pinned requests
without changing promoted means.

New output separates `measurement_completed`, `reference_comparable`,
`diagnostics_complete` and `performance_accepted`. A setup mismatch no longer
implies no valid damage measurement. Strict reference admission remains intact.
HPS now reads full native `healer_metrics.effective_healing`; Affliction had
116,580 effective self-healing, or 388.600 HPS, previously summarized as zero.

## Proven and unresolved class edges

**Shared potion ownership, implemented but live pending.** Fire and Balance
used prepot, an ordinary profile potion at elapsed 0, then the fixture combat
potion around 61s. Inventory 20→19, later 18→17 proves the extra intermediate use.
This was not merely a counter bug. `UpdateCalibrationBot` now excludes the
fixture-owned potion from both preview and executor profile resolution, only
for self-provided `single_target_300`. Ordinary raid profiles remain unchanged.
Tests prove the extracted candidate exclusion and caller forwarding, not native
inventory callbacks. Independent review approved that limited claim. An earlier
test manufactured inventory values; those assertions were removed.

**Balance should lead the next native class investigation.** Mark of the Wild (1126)
was absent in all 2,999 samples; Leather Specialization (87505) was absent from the
scoring-start intellect multiplier ledger despite the all-leather set. Removing
temporary potion/Lightweave contributions gives native static Int 8,162. Applying
the two missing 5% multipliers gives 8,998.605, exactly the simulator value. Repair
normal self-casting and native armor-specialization application, never injected
stats/auras. Then revisit DoT refresh/Eclipse policy and Wrath cadence. Current
data cannot isolate their recoverable damage until the stat setup is correct.

**Elemental:** WoWSims 66843 is Call of the Ancestors, summoning Earth (2062) and
Fire (2894); the native APL translation substitutes only Fire. Earth contributes
about 381 DPS in the retained debug example, so it is not the whole deficit.
The stat comparator double-counts simulator haste and compares converted spirit
against raw hit. Corrected speed still differs by 5%, but absence of a native
scoring-start aura observation prevents proving Wrath of Air nonapplication.
Fire Elemental event damage/cadence differ substantially; the pinned simulator
itself labels its values estimated/TODO. Do not treat that as coefficient authority.

**Affliction:** Corruption/UA cadence is close while periodic crit realization
was 91 against 120.738 expected from recorded chances across 348 events. That is
one seed, not proof of a native RNG bug. Bane cadence matches but event damage
is lower; crit/modifier observations are missing. No pet, coefficient or Drain
Soul patch is justified by these aggregates. Soulburn 3 versus sim 7 also needs
resource-semantics review; native has three shards and consumes them.

**Survival:** do not delete Blood Fury to make an incomplete reference pass.
The transformation removed upstream `autocastOtherCooldowns`. A separately
bound, unpromoted control restoring it produced 37,454.161 DPS over 2,000 × 300s.
It enabled Blood Fury 3, Rapid Fire 1, Rabid 7 and Call of the Wild 1, with those
counts also observed natively. The old catalog remains immutable. Simulator
Blood Fury 33697 maps to native 20572. Explosive Shot 56 versus control 77.017 is a
larger remaining cadence signal; investigate Lock and Load generation/consumption
before changing priorities. Crit/pet activation timing and haste projection
must be reconciled before claiming a stat-mechanics mismatch.

Blood mitigation/damage and healer efficiency remain part of the raid objective.
The prior Blood Shield semantic review is retained at
`/tmp/magmaw-blood-shield-semantics-20260919.json`; it was not implemented here.
Do not silently drop these actors while working on a DPS class.

## Jev/Laya workflow delivered

- `tools.raid_program.worker_checkpoint`: task/evidence/claim checks with local,
  hosted or both providers; exact inputs/responses/source hashes retained.
- `tools.raid_program.worker_precommit` and `.githooks/pre-commit`: actual staged
  diff, task bytes, HEAD and index-tree binding. Rechecks detect concurrent changes.
  Explicit file-scope and reported-test failures are separate from model advice.
- `.agents/skills/plan-drift-review/SKILL.md`: callable for a worker **or the main
  orchestrator**. Includes parent objective, latest user direction, active plan,
  completed work, unresolved requirements and the intended next action.
- Usage and research sources: `docs/bot_raids/worker_checkpoints.md`.

Use `$plan-drift-review` or ask the receiving agent to read that skill. It gathers
the conversation's current plan and repository evidence; Git alone cannot know
unstored user intent. Use two worker checkpoints, proposed repair and returned
result. Do not call a model on every tool action. A user-requested focus change
is authorized, not drift.

The hook is repository-provided, **not globally installed** across ongoing
worktrees. Use `git -c core.hooksPath=.githooks commit` with the current task in
the worktree-local `git rev-parse --git-path worker-task.json`, or invoke the CLI
with `--task`, `--env-file` and `--backend both`. Scores are separate categorical
probabilities/confidence, not one averaged code-quality score. Test receipts are
reported evidence, not independent proof that tests exercised the staged tree.

Pilot findings matter: both models initially accepted an unsupported native
test claim. One question correction made Jev flag it; Laya still missed it.
Jev rejected forbidden Blood Fury removal and a counterfactual orchestrator plan
that discarded remaining class work. Laya missed important scope/claim judgments.
The actual staged-diff trial exceeded Laya context and received an inaccurate
Jev evidence contradiction. These failures are retained. **No automatic model
gate or calibrated accuracy claim is justified.** Use Jev to inform coordinator
review; Laya remains an experimental second opinion. Predictions are not labels.

Independent review approved the workflow and native potion patch. The final
focused suite passed 38 tests. Native compilation/live validation are separate
and remain pending for the potion patch. No full raid was run after 696a.

## Evidence and recovery

Closed batch, five actor reviews, simulator timelines/control, builds, tests,
initial/final code reviews and all checkpoint trials are in:

`artifacts/cata_raid_program/dummy_50ec676cdb_calibration_20260919.tar.gz.dvc`

Remote MD5 `48a86ff525d72ac125dafa641a2a8470`, size 20,696,061 bytes. `dvc status`
and `dvc push` completed; a fresh remote download verified all 201 members by
size/SHA256. Exact local raw/comparison/archive/cache duplicates were removed
after verification; compact actor reviews, receipts and batch summaries remain.
The cleanup receipt records 881,671,158 logical bytes removed. Initial failed
setup evidence remains under `dummy_b8e9803721_initial_20260919.tar.gz.dvc`.

The compact publication/cleanup and model-adjudication receipt is
`artifacts/cata_raid_program/dummy_50ec676cdb_closure_20260919.json.dvc`
(MD5 `62be805f4f18d83db74a3334e29a9ec4`), also verified from a fresh remote copy.

To recover this closed evidence:

```sh
pixi run python -m dvc pull artifacts/cata_raid_program/dummy_50ec676cdb_calibration_20260919.tar.gz.dvc
mkdir -p /tmp/dummy-50ec-recovered
tar -xzf artifacts/cata_raid_program/dummy_50ec676cdb_calibration_20260919.tar.gz -C /tmp/dummy-50ec-recovered
```

Actor reviews are in `receipts/dummy-50ec676cdb-*-review-20260919.json`.
Native reports are under the `dummy-50ec676cdb-pair-20260919/` and
`dummy-50ec676cdb-casters-20260919/` members. Simulator debug/control and
`worker-checkpoint-pilot-20260919/` have their own directories. Archive manifest
retains member hashes. Do not search deleted raw files indefinitely or regenerate
experiments merely because local payloads were evicted.

## Mainline and worktree cleanup

All work from this tab is committed on `master`, the repository's mainline.
The clean retired checkout at
`/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/source`
was removed after confirming its `779f62087f` source is already an ancestor of
master and no process was using it. Its 1,188 ignored asset/reference/dataset
files (864,356,733 bytes) were preserved in:

`artifacts/cata_raid_program/retired_shared_instance_worktree_20260919.tar.gz.dvc`

The 240,429,783-byte archive has MD5 `868f5c505df65f84366e15e8652c8a7c`.
A fresh remote download verified every member's SHA256 before removal. Local
archive and exact cache copies were then evicted. Recover with `dvc pull` on
that pointer; `manifest.json` records the original relative paths and hashes.
Source files remain recoverable from Git. Disposable Python/DVC caches were
removed with the retired checkout; no broad cache collection was performed.

The original `trinity-cata` and detached `trinity-jev-integration` checkouts
contain uncommitted work and were preserved. Cleanup does not mean their changes
were merged or approved. Do not delete them based only on branch age.

## Next receiving-agent work unit

1. Read this handoff, the current actor table, ledger `CAL-001`/`REF-003`, and the
   relevant specialist receipt. Run plan-drift review with the latest user request.
2. Prefer the proven Balance self-buff/passive setup edge. Give a bounded worker
   exact owned paths, native observations, allowed repair and forbidden synthetic
   stat changes. Review the real spellbook/aura path before implementation.
3. Review the worker's plan and returned diff using the new checkpoints. Interpret
   predictions against evidence; keep the remaining actors visible.
4. After deterministic checks and independent review, commit clean source and
   build once using the exact queued-build policy. Include the already reviewed
   shared potion fix. Run one bounded Fire/Balance pair to validate both setup
   repairs, exact 300-second measurements and native potion counts.
5. Update every actor row from the closed results. Repair references/comparator
   semantics where needed; do not tune coefficients to compensate for missing
   native setup. Publish through DVC, verify remote and remove exact duplicates.
6. Once controlled class comparisons support it, return to one watchdog-bounded
   Magmaw run. Review every DPS/tank/healer, target/phase/duty behavior and exact
   damage accounting. Compare against the identified lawful raid baseline and
   matched WCL evidence. Accept clear, requested repair and overall performance
   separately, then continue with the newly proven edge.

Keep one bounded hypothesis per repair. Stop unchanged retries after ten
occurrences of the same first broken edge and change the investigation. Do not
use repeated whole-raid canaries to avoid a measurable class/setup mismatch.
