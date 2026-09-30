# Raid program: raid-level requests

A raid-level request names a raid and a mode but no boss: `implement bwd 10n bots`,
`implement firelands 25hc bots`. Raid aliases come from the prerequisite files
(`experiments/configs/raid_prerequisites/<raid>.json`: key, name, native save
header, name initials, optional `aliases`). The program carries every boss shard
in parallel rounds, then the end-to-end clear. It references boss-level scenarios
and never rewrites their graphs.

`W` below is `pixi run python -m tools.raid_program.raid_workloop`. `S` is the
current `state_sha256`. Every writing command takes `--expect S` and prints the
new one, and `$W resume` shows it too.

## Start and continue

```sh
$W start "implement bwd 10n bots"   # select or create the program; --preview writes nothing
$W resume                            # exact next action and commands (read-only)
$W program status                    # per-boss table; --boss KEY for one unit in full
```

State: `artifacts/cata_raid_program/raid_program_state_v1.json`. Commit it after
every step. A boss-level `start` switches plain `resume` back to the boss graph;
use `resume --program` or `resume --boss` to choose explicitly. The boss-level
`resume` also shows a one-line `raid_program` pointer.

The orchestrator's [standing rules](../SKILL.md#standing-rules) apply to every
step below.

## Units

- **Boss units.** There is one per boss of the prerequisite DAG that exists on the
  mode. Each has:
  - cohort `<raid>_<size><diff>_<boss>_c0`, with scenario, profile and pool
    `<cohort>_diagnostic`;
  - its seeded-lockout plan: the transitive predecessor closure, or a fresh
    instance when it has none;
  - the boss-level scenario it references.
- **The e2e unit.** It is the composition's `full_raid` cohort, run on its own
  scenario row. Scenario, profile and pool must be one ID. It runs on a fresh
  instance, and the composed route
  (`experiments/configs/raid_route_compositions/<raid>_<size><diff>.json`) gives
  the drift check and the boss nodes it must kill.
- **Missing inputs.** Each one is typed, with `blocks: run|acceptance` and an owner
  skill. They are the round's work: never stop on them, and never borrow another
  difficulty's inputs. `encounter_research` closes per mode (see the per-mode
  research gate in [raid-encounter-research](../../raid-encounter-research/SKILL.md)).
- **Raid-level inputs.** The strategy catalog, the prerequisite verification and
  the script-readiness audit gate the e2e unit and program completion.

## One round, command by command

Before each step, run `$W resume`. If its `next_action` differs from this list,
follow `next_action`. If it says "ASK THE USER", do step 2.6 first.

### 1. Plan

```sh
$W program plan --expect S
git add artifacts/cata_raid_program && git commit -m "<Raid> <mode> round N: plan"
```

The plan records the plan commit (the round base) and freezes the packets:

- one `boss:<key>` packet per open boss unit;
- `shards`, when shard or e2e inputs are missing. It owns the composition,
  scenario rows, profiles, prerequisite data, route composition and `dvc.yaml`;
- `research`, for raid-level research inputs. It owns the strategy catalog and
  the script-readiness audit. The audit waits until every boss unit is accepted,
  because boss packets change scripts.

Globs are segment-aware: `*` stays in one path segment and `**` spans segments.
Nobody owns the coordinator files: native runtime outside a boss content
directory, the instance script, the fidelity registry, CMake, skills, AGENTS.md
and both state files. Plan time catches only obvious overlaps. The
ownership guarantee is the build-time check of the actual git diff (step 5).

### 2. Implement (parallel workers)

A raid-level request authorizes one implementation agent per packet (user
decision, 2026-09-25).

1. Write each packet: `$W program packet --id <packet> --output /tmp/<packet>.json`.
2. Start one worker per packet. Choose the model with the orchestrator's
   [worker model](../SKILL.md#worker-model) table; a whole boss packet runs on
   Opus 5.5. Build the prompt from
   [every implementer prompt includes](../SKILL.md#every-implementer-prompt-includes):
   the packet file, its `owner_skill`, the user decisions quoted exactly, the
   pre-review checklist, the `needs_user_decision` rule and the `test_baseline`
   rule.
3. When a worker finishes, record its handoff:
   `$W program handoff --id <packet> --file <handoff.save_as> --expect S`.
   It checks the schema, normalized paths and ownership, and it ignores the
   handoff file's own path. Use `--abandon REASON` when a packet produced
   nothing, or `--external REASON` for work that landed outside the program
   (name its commits). Once every packet is handed off, the stage moves to
   `review`.
4. Read each handoff. Check every diagnosis before acting on it
   ([check agent claims](../SKILL.md#check-agent-claims-before-acting)). Check
   every "pre-existing" test failure with `test_baseline check`.
5. Route the patch requests: shard files to `shards`, research files to
   `research` (or to you when the round has no such packet), and coordinator
   files to yourself.
6. If `resume` says "ASK THE USER", ask the user each open decision, then
   record the answer word for word:
   `$W program decide --decision-id <id> --answer "<the user's exact words>" --expect S`.
   Forward the quote to the owning worker. If the answer changes the worker's
   task, run `$W program reopen --id <packet> --reason "user decision <id>"`.

### 3. Integrate (coordinator only)

Every worker must have stopped first.

1. Apply the coordinator patch requests.
2. Promote each calibrated boss damage modifier:
   1. read back the `creature_template` row the packet names, and check that it
      matches the packet's expected pre-state (usually `DamageModifier` 1);
   2. apply the packet's registry patch to
      `experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json`;
   3. run `git mv sql/custom/staged/world/<file>.sql sql/custom/world/`;
   4. update the test the packet names that asserts the staged path.

   The run then loads the Blizzlike value, and the review and build commit
   include it.
3. If the round changed composition, scenario, prerequisite, profile or route
   data, or `program build --dry-run` reports a data problem, run:

   ```sh
   $W program refresh-data --expect S
   ```

   It derives the raid data stages from `dvc.yaml`:
   `validation_gear`, `validation_provisioning`,
   `validation_provisioning_verify`, `raid_shard_provisioning` and
   `validation_scenarios`. It reproduces the stale ones in dependency order,
   sets 0644 modes, rebinds the runtime asset closure (both the gear-profile and
   the validation-route classes), and pushes only those stages. Commit every
   file it prints with the round.
   - Never hand-edit the closure manifest. Never run an old `/tmp` rebind
     script, and never run `dvc repro` by hand for these stages.
   - `world_planner` and `world_knowledge` read the live world DB. They are
     boundary stages: reported as a warning when stale, never reproduced or
     gated.
   - It is safe to run when nothing is stale.
4. Run the tests: every packet's `focused_tests`, plus the tests of the files you
   changed, through
   `pixi run python -m tools.raid_program.test_baseline check <pytest args>`.
   Fix or route every `new_failure`.
5. Check file sizes: `pixi run python -m tools.raid_program.module_size`
   (C/C++ files stay below 1,000 lines).

### 4. Review (before the build)

1. Write the round diff:
   `$W program review-diff --output /tmp/codexrev-<slug>-rNN-p<P>/round.diff`.
   The output must lie outside the source tree. The command prints
   `diff_sha256`. The diff runs from the plan commit to the working tree,
   including untracked files, and leaves out `raid_program_state_v1.json` and
   `raid_programs/**`. For a round with no source change, record
   `$W program review --empty-diff --expect S` instead and go to step 5.
2. Review it with GPT-6.1 Sol in a separate session
   ([independent review](../SKILL.md#independent-review-gpt-6.1-sol)).
   - The first pass gets the full diff and the handoffs.
   - Later passes get the earlier findings, the new diff and
     `diff -u <previous round.diff> <new round.diff>`.
3. Copy the verdict to
   `artifacts/cata_raid_program/raid_programs/<slug>/roundNN/review_p<P>.md`,
   which the diff leaves out, and record it:

   ```sh
   $W program review --verdict accept|reject --diff-sha256 <sha from 4.1> \
     --reviewer "gpt-6.1-sol <agent or session id>" \
     --report artifacts/cata_raid_program/raid_programs/<slug>/roundNN/review_p<P>.md --expect S
   ```

4. On `reject`, the round stays in `review`. Route each finding:
   - For a packet's file, run `$W program reopen --id <packet> --reason "<finding>"`.
     The worker fixes it and hands off again (step 2.3), and the stage returns
     to `review` after that handoff.
   - For a coordinator file, fix it yourself and run
     `$W program fix --reason "<finding>: <change>"`.

   Apply all of the pass's fixes as one batch. Then go back to step 3.3 if data
   changed (otherwise 3.4), and then to 4.1. Expect four or five passes.
5. On `accept`, the stage moves to `build`. Commit the round's changes, the
   state and the files that refresh-data printed. The review still matches after
   the commit, because the same sha covers the plan commit to HEAD. If anything
   changes after the accept, the build refuses: review the new diff.

### 5. Build

```sh
$W program build --dry-run          # argv, ownership, review and data checks
$W program build --expect S         # one configure + one worldserver build, host8 policy
git add artifacts/cata_raid_program && git commit -m "<Raid> <mode> round N: record the program build"
```

The build refuses in these cases. Each has one fix:

| Build refuses because | Fix |
| --- | --- |
| The latest review is not `accept` for exactly the committed diff | Review again (step 4) |
| A raid DVC stage is stale | Run `refresh-data` (step 3.3), commit, then review the new diff |
| A file two packets can own | Fix the ownership, or reopen the packet |
| A user decision is open | Ask the user (step 2.6) |
| A worldserver is running | Wait. If it is a pytest fake, see the standing rules |

A success records the worldserver sha256, or it is not a success. Recovery:

- An interrupted build: `$W program build --finish [--queue-receipt <ticket>]`
  adopts the completed ticket without compiling.
- `$W program reopen --id <packet> --reason <text>` sends a packet back.
- `$W program fix --reason <text>` records your own repair.

### 6. Run and ingest

```sh
$W program run-plan --expect S && git add artifacts/cata_raid_program && git commit -m "<Raid> <mode> round N: shard run plan"
$W program run-batches --label <label> --expect S [--max-batches N]
```

`run-plan` writes the batches once per round; `--replan` replaces them before
any run. Every plan names the generated `raid_shard_plan`
(`dataset/raid_shard_provisioning/<composition_id>/plan.json`), so that the
canonical cohorts are provisioned. A missing plan, or a cohort missing from it,
is a typed shards input.

`<label>` is the one that `resume` prints in `commands`, for example
`blackwing_descent_10n-r02-a82a035b81`. A round uses one label. For each batch,
`run-batches`:

1. waits, bounded, until no `worldserver*` process runs. A pytest fake is waited
   out; a real worldserver refuses the run;
2. checks `/tmp` headroom, meaning free space and the per-user quota;
3. runs `shard_coordinator --plan <round plan> --output-dir /tmp/<label>-bN-<utc> --gdb-backtrace`;
4. records the run, or a failed batch when there is no `shard_run.json`;
5. ingests it, as `program ingest` does. Each kill is recorded from the live
   run directory, its evidence is archived to DVC, and the `/tmp` copy is
   removed. A kill without an evidence pointer never counts.

It repeats until every target boss has `kills_per_measurement` counted kills.
It stops early after `--max-batches` (default 5), or when a batch adds no
counted kill for a boss that is still short. It does not commit, so commit the
files it prints.

If it stops early, do not rerun it unchanged. Read each batch's terminal reason
and the sanity findings (step 7).

Manual equivalent, for debugging one batch:

1. `pixi run python -m tools.raid_program.shard_coordinator --plan <file> --output-dir /tmp/<new run dir> [--dry-run]`
2. `$W program run --shard-run /tmp/<run dir>/shard_run.json --expect S`. For a
   batch with no `shard_run.json`, use
   `$W program run --failed-batch N --reason <text> --expect S` instead.
3. `$W program ingest --label <label> --expect S`. It exits non-zero while an
   error or pending archive remains; `scoreboard archive-pending --scenario <S>`
   retries the archive.

### 7. Assess

```sh
$W program assess --label <label> --expect S
dvc status && dvc push
git add artifacts/cata_raid_program && git commit -m "<Raid> <mode> round N: assessment"
```

- A boss unit is accepted only when all of these hold:
  - its latest run is a native clear;
  - its verdict passes on this round's binary;
  - no input is missing;
  - it has no `blocking` sanity finding.
- Accepted units must pass again every round, or they reopen.
- `next_action` lists sanity findings as "investigate before tuning". A
  blocking finding means the result is not real yet. Triage it with the
  playbook's [sanity table](../../raid-tuning-playbook/SKILL.md#sanity-findings-is-the-result-real)
  before any DPS work, and put the triage into the next round's packets.
- Then run `$W resume`. It returns the next round's plan, or the e2e stage once
  every boss unit is accepted, no raid-level input is open and the e2e unit is
  ready.

### 8. End to end

1. Run `pixi run python -m tools.raid_program.raid_route_composer --composition <file> --check`.
2. Run `$W program run-plan --expect S`: one fresh-instance shard of the
   full-raid cohort, which the generated plan must contain.
3. Run the plan with shard_coordinator into `/tmp`.
4. Record it with `$W program e2e --shard-run <file> --expect S`. As with
   ingest, the result is recorded first, then the run root is archived to DVC,
   then the pointer is attached. The unit is accepted, and the program
   completes, only once that pointer is stored. If the archive fails, the
   command exits non-zero, and `$W program e2e --archive-pending` retries from
   the kept `/tmp` root or adopts an archive that completed before its state
   update.
5. If the root is gone (`/tmp` is tmpfs, so a reboot clears it) and no completed
   archive exists, run `$W program e2e --evidence-lost <reason>`. A clear
   without evidence never passes: the unit reopens, and the next round re-runs
   the full route.
6. If the archive keeps failing while the root still exists (for example, DVC
   is unreachable), abandon the attempt with `$W program e2e --failed <reason>`.
   The kept evidence can still be archived later.
7. If the plan cannot run, or it produced no `shard_run.json`, run
   `$W program e2e --failed <reason>`.

Only a pending clear blocks a new e2e run, and a program that awaits e2e
evidence cannot be switched away from. The e2e unit passes only if every
composed boss node dies natively on the round binary, with no raid-level input
open. A failure opens a round with the `shards` packet.

## Rules

- Seeded lockouts are `diagnostic_only_assistance`. They never certify a
  predecessor kill, and the e2e run must use a fresh instance.
- Each round gets one build. Only the coordinator commits, builds, provisions,
  runs servers, archives evidence and records steps.
- Raid runs use the completion watchdog. Recovered trash deaths are context;
  boss-window deaths fail a kill, except where a recorded user decision exempts
  them (the Chimaeron Mortality phase).
- Before a final reply, run `$W resume`. The raid is done only when it reports
  `parent_objective_complete`; until then, execute `next_action`.

## AGENTS.md routing (applied by the coordinator)

AGENTS.md already carries this text (applied 2026-09-25). The user owns
AGENTS.md, so propose any change to it as exact text.

```text
For raid-level requests naming a raid and difficulty but no boss (for example
"implement bwd 10n bots"; raid aliases come from experiments/configs/raid_prerequisites,
such as bwd, bot/bastion, tofw, fl/firelands, ds/dragon soul), run the same
`raid_workloop start "<request>"`. It selects a raid program: one unit per boss
shard in a seeded lockout, synchronized rounds (plan, parallel implementation,
one build, every ready shard in one worldserver, ingest, per-boss assessment),
then the end-to-end clear with trash and interactions. Follow
`.agents/skills/trinity-orchestrator/references/raid-program.md`. Plain
`raid_workloop resume` continues whichever of the raid program or the boss
graph was started last; `resume --program` and `resume --boss` choose
explicitly. A raid-level request authorizes one implementation agent per round
packet (no model override; reviewers in separate sessions). The raid is complete
only when `raid_workloop resume` reports `parent_objective_complete`; until then
execute the returned next action.
```
