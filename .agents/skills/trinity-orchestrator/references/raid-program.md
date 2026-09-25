# Raid program: raid-level requests

A raid-level request names a raid and a mode but no boss: `implement bwd 10n bots`,
`implement firelands 25hc bots`. Raid aliases come from the prerequisite files
(`experiments/configs/raid_prerequisites/<raid>.json`: key, name, native save
header, name initials, optional `aliases`). The program carries every boss shard
in parallel rounds, then the end-to-end clear. It references boss-level scenarios
and never rewrites their graphs.

`W` below is `pixi run python -m tools.raid_program.raid_workloop`.

## Start and continue

```sh
$W start "implement bwd 10n bots"   # select or create the program; --preview writes nothing
$W resume                            # exact next action and commands (read-only)
$W program status                    # per-boss table; --boss KEY for one unit in full
```

State: `artifacts/cata_raid_program/raid_program_state_v1.json`. Commit it after
every step. Every writing command takes `--expect <state_sha256>` from `resume`.
A boss-level `start` switches plain `resume` back to the boss graph; use
`resume --program` or `resume --boss` to choose explicitly. The boss-level
`resume` also shows a one-line `raid_program` pointer.

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
  difficulty's inputs.
- **Raid-level inputs.** The strategy catalog, the prerequisite verification and
  the script-readiness audit gate the e2e unit and program completion.

## One round

1. **Plan.** Run `$W program plan`. It records the plan commit and freezes the
   packets:
   - one `boss:<key>` packet per open boss unit;
   - `shards`, which owns the composition, scenario rows, profiles, prerequisite
     data, route composition and `dvc.yaml`, when shard or e2e inputs are missing;
   - `research`, which owns the strategy catalog and the script-readiness audit,
     for raid-level research inputs. The audit waits until every boss unit is
     accepted, because boss packets change scripts.

   Globs are segment-aware: `*` stays in one path segment and `**` spans segments.
   Coordinator files (native runtime outside a boss content directory, the
   instance script, the fidelity registry, CMake, skills, AGENTS.md and both state
   files) are never owned. Plan time only catches obvious overlaps. The ownership
   guarantee is the build-time check of the actual git diff (step 3).
2. **Implement.** A raid-level request authorizes one implementation agent per
   packet (user decision, 2026-09-25). Use no model override.
   - Give each agent `$W program packet --id <packet> --output /tmp/<packet>.json`.
   - Record each handoff with `$W program handoff --id <packet> --file <handoff.save_as>`.
     It checks the schema, normalized paths and ownership. Use `--abandon REASON`
     when a packet produced nothing, or `--external REASON` for work that landed
     outside the program (name its commits).
   - Route patch requests: shard files go to `shards`, research files go to
     `research` (or to you when the round has no such packet), and coordinator
     files are yours.
   - Review each change per the playbook risk tier, in a separate session.
3. **Build.** Every agent must have stopped: an edit during a build aborts it.
   1. Apply the remaining patches.
   2. Reproduce the DVC stages whose inputs changed, and rebind the runtime asset
      closure ([raid-shard-architecture](../../raid-shard-architecture/SKILL.md)).
   3. Run the focused tests and report any earlier failures.
   4. Commit.
   5. Run `$W program build --dry-run`. It shows the argv and the ownership check,
      which is the ownership guarantee: every file changed since the plan commit is
      matched against the packets, and a file two packets can own stops the build
      (and `--finish`).
   6. Run `$W program build`: one configure and one worldserver build through
      queued_build with `queued_build.DEFAULT_POLICY_RELATIVE`. The job count comes
      from the policy. Step results persist in the queue receipts directory. A
      success records the worldserver sha256 or it is not a success. Never build
      while a worldserver runs.
   7. Commit the recorded build.

   Recovery:
   - An interrupted build: `$W program build --finish [--queue-receipt <ticket>]`
     adopts the completed ticket without compiling.
   - `$W program reopen --id <packet> --reason <text>` sends a packet back.
   - `$W program fix --reason <text>` records your own repair.
4. **Run.** `$W program run-plan` writes the batches once per round (`--replan`
   replaces them before any run). Every plan names the generated `raid_shard_plan`
   (`dataset/raid_shard_provisioning/<composition_id>/plan.json`) so the canonical
   cohorts are provisioned. A missing plan, or a cohort absent from it, is a typed
   shards input. For each batch:
   1. `pixi run python -m tools.raid_program.shard_coordinator --plan <file> --output-dir /tmp/<new run dir> --dry-run`
   2. The same without `--dry-run`. Run directories must lie under `/tmp`, the
      only place evidence is archived from.
   3. `$W program run --shard-run /tmp/<run dir>/shard_run.json`. The run must use
      this round's binary (`worldserver.sha256`). A batch that produced no
      `shard_run.json` is recorded with `$W program run --failed-batch N --reason <text>`.
5. **Ingest.** Run `$W program ingest --label <label>`. For each shard of a boss
   with a raid target, like `scoreboard run`, it:
   1. records the kill from the live run directory (timeline and summary kept in
      `<run dir>-analysis`), with the round binary and build commit;
   2. archives the evidence to DVC under `artifacts/cata_raid_program/`, which
      deletes the `/tmp` copy;
   3. appends the record with its pointer, or with `archive_error` so that
      `scoreboard archive-pending --scenario <S>` can retry.

   A kill without an evidence pointer never counts. Shards without a target and
   each batch's run-root files (`shard_run.json`, console journal, logs) are
   archived too, and their pointers are kept in the state. `ingest` exits
   non-zero while any error or pending archive remains. Repeat a batch (same plan,
   new `/tmp` output directory), record it and ingest again until those bosses
   reach their target's `kills_per_measurement`. A round uses one label.
6. **Assess.** Run `$W program assess --label <label>`. The label is required
   when a boss with a raid target ran.
   - A boss unit is accepted only when all of these hold: its latest run is a
     native clear, its verdict passes on this round's binary, and no input is
     missing.
   - Accepted units must pass again every round, or they reopen (not re-run,
     newly blocked, verdict missing or failing).
   - Then run `dvc status` and `dvc push`, and commit.
   - The next round follows, or the e2e stage once every boss unit is accepted, no
     raid-level input is open and the e2e unit is ready.
7. **End to end.**
   1. Run `pixi run python -m tools.raid_program.raid_route_composer --composition <file> --check`.
   2. Run `$W program run-plan`: one fresh-instance shard of the full-raid cohort,
      which the generated plan must contain.
   3. Run the plan with shard_coordinator into `/tmp`.
   4. Record it with `$W program e2e --shard-run <file>`. As with ingest, the
      result is recorded first, then the run root is archived to DVC, then the
      pointer is attached. The unit is accepted, and the program completes, only
      once that pointer is stored. If the archive fails, the command exits
      non-zero and `$W program e2e --archive-pending` retries from the kept `/tmp`
      root.

   It passes only if every composed boss node dies natively on the round binary,
   with no raid-level input open. If the plan cannot run or produced no
   `shard_run.json`, run `$W program e2e --failed <reason>`. A failure opens a
   round with the `shards` packet.

## Rules

- Seeded lockouts are `diagnostic_only_assistance`. They never certify a
  predecessor kill, and the e2e run must use a fresh instance.
- Each round gets one build, and only the coordinator commits, builds,
  provisions, runs servers, archives evidence and records steps.
- Raid runs use the completion watchdog. Recovered trash deaths are context;
  boss-window deaths fail a kill.
- The raid is done only when `resume` reports `parent_objective_complete`.

## AGENTS.md routing (applied by the coordinator)

This is the exact text proposed for AGENTS.md. Append it after the paragraph
that ends "…or a specific external blocker that cannot be resolved." The user
owns AGENTS.md; the coordinator applies this after approval.

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
