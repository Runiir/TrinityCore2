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
`resume --program` or `resume --boss` to choose explicitly.

## Units

- **Boss units.** There is one per boss of the prerequisite DAG that exists on the
  mode. Each has:
  - cohort `<raid>_<size><diff>_<boss>_c0`, with scenario, profile and pool
    `<cohort>_diagnostic`;
  - its seeded-lockout plan: the transitive predecessor closure, or a fresh
    instance when it has none;
  - the boss-level scenario it references.
- **The e2e unit.** It is the composed full route
  (`experiments/configs/raid_route_compositions/<raid>_<mode>.json`) run on a fresh
  instance.
- **Missing inputs.** Each one is typed, with `blocks: run|acceptance` and an owner
  skill. Composition, scenario rows, research, native scripts, fidelity and targets
  are all listed. They are the round's work: never stop on them, and never borrow
  another difficulty's inputs.

## One round

1. **Plan.** Run `$W program plan`. It freezes the packets:
   - one `boss:<key>` packet per open boss unit;
   - one `shards` packet when shard inputs are missing or the e2e unit is due.

   Owned files are disjoint. Coordinator files (native runtime outside a boss
   content directory, the instance script, the fidelity registry, CMake, skills,
   AGENTS.md and both state files) are never owned. `--boss KEY` limits the packets.
2. **Implement.** A raid-level request authorizes one implementation agent per
   packet (user decision, 2026-09-25). Use no model override.
   - Give each agent `$W program packet --id <packet> --output /tmp/<packet>.json`.
     The packet names its skill, task, inputs, owned and forbidden files, focused
     tests, rules and the handoff schema.
   - Save each final handoff JSON at the packet's `handoff.save_as` path. Record it
     with `$W program handoff --id <packet> --file <path>`, which checks the schema
     and file ownership. Use `--abandon REASON` when a packet produced nothing, or
     `--external REASON` for work that landed outside the program (name its commits).
   - Patch requests to shard files go to the `shards` packet, or to you when this
     round has none. Apply coordinator files yourself.
   - Review each change per the playbook risk tier, in a separate session.
3. **Build.** Every agent must have stopped: an edit during a build aborts it.
   1. Apply the remaining patches.
   2. Reproduce the DVC stages whose inputs changed, and rebind the runtime asset
      closure ([raid-shard-architecture](../../raid-shard-architecture/SKILL.md)).
   3. Run the focused tests and report any earlier failures.
   4. Commit.
   5. Run `$W program build`. It does one configure and one worldserver build of
      that commit through queued_build, with `queued_build.DEFAULT_POLICY_RELATIVE`.
      The job count comes from the policy. Never build while a worldserver runs.
      `--dry-run` prints the argv.
   6. Commit the recorded build.
4. **Run.** `$W program run-plan` writes `raid_shard_run_plan_v1` batches of every
   ready shard. A batch holds at most the coordinator's per-worldserver capacity.
   For each batch:
   1. Run `pixi run python -m tools.raid_program.shard_coordinator --plan <file> --dry-run`.
   2. Run it again with `--output-dir <new directory outside the repository>`.
   3. Record it with `$W program run --shard-run <dir>/shard_run.json`.

   For each boss with a raid target, ingest its shard directory under one round
   label: `scoreboard ingest --scenario <target> --label <label> --run-dir <dir>/shards/<cohort>`.
   Repeat the batch until those bosses reach the target's `kills_per_measurement`.
5. **Assess.** Run `$W program assess --label <label>`.
   - A boss unit is accepted only when all of these hold: its last run is a native
     clear, its scoreboard verdict passes on this round's binary, and no input is
     missing.
   - Otherwise its typed stall or verdict gap goes into the next packet.
   - Accepted units run again in every round and reopen if they regress.
   - Then run `dvc status` and `dvc push`, and commit.
6. **End to end.** Once every boss unit is accepted and the e2e inputs exist:
   1. Run `pixi run python -m tools.raid_program.raid_route_composer --composition <file> --check`.
   2. Run `$W program run-plan`: one fresh-instance shard on the full route.
   3. Run the plan with shard_coordinator.
   4. Record it with `$W program e2e --shard-run <file>`.

   The unit passes only if every boss route node dies natively. A failure opens a
   round with the `shards` packet.

## Rules

- Seeded lockouts are `diagnostic_only_assistance`. They never certify a
  predecessor kill, and the e2e run must use a fresh instance.
- Each round gets one build, and only the coordinator commits, builds,
  provisions, runs servers and records steps.
- Raid runs use the completion watchdog. Recovered trash deaths are context;
  boss-window deaths fail a kill.
- The program is complete when every boss unit and the e2e unit are accepted.
  Until then, `resume` and execute the next action.
