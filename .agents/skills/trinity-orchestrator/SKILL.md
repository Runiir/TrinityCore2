---
name: trinity-orchestrator
description: Own broad requests such as implement boss bots (implement magmaw 10n bots) or implement raid bots (implement bwd 10n bots) through diagnosis, repair workers, builds and live validation. Use for encounter-wide and raid-wide implementation and optimization, not only explicit orchestration requests. Also defines worker model choice, the GPT-6.1 Sol review loop, checking agent claims, when to ask the user, known test failures and the standing rules.
---

# Trinity orchestrator

The primary agent owns the user's encounter or raid objective. A specialist
result is an intermediate step, not completion. The tuning loop, finish line,
thresholds and risk tiers are in [raid-tuning-playbook](../raid-tuning-playbook/SKILL.md).
This skill covers startup, the saved graph, workers and review.

A raid-level request names a raid and a mode but no boss (`implement bwd 10n bots`,
`implement ds 25hc bots`). `raid_workloop start` then selects a raid program:
parallel boss shards in seeded lockouts, one build per round, then the end-to-end
clear. Follow [raid program](references/raid-program.md) for the command-by-command
round.

## Startup and continuation

Inspect `git worktree list --porcelain`, use the checkout holding `master`, and
verify it matches the saved `coordinator_worktree`. Preserve unrelated dirty
work; do not build an old or detached checkout or copy task state between
worktrees. Run `raid_workloop start "<request>"` for a named boss or raid and a
mode, or `raid_workloop resume` to continue (read-only). `start --preview`
resolves a request without selecting it.

- For a boss, read the returned `unit.next_action`, `owner_skill` and
  `latest_assessment`.
- For a raid program, read `next_action` and `commands`.

Then execute the returned step, and after every transition execute the next one.
If `next_action` starts with "ASK THE USER", do [When to ask the user](#when-to-ask-the-user)
first. Before a final reply, run `resume` and continue while the parent
objective is open. After context compaction, run `resume` once instead of
rereading skills and old receipts.

## Saved graph commands

All run as `pixi run python -m tools.raid_program.<module>`:

- `workflow_step advance --receipt <path> [--owner <claim owner>] --dry-run`,
  then the same without `--dry-run`. The helper derives revision, hashes and
  token; never hand-copy them or retry a rejected transition unchanged.
- `workflow_step tests --owner <owner> --producer <implementer session ID> --behavior-command '<declared command>'`
  runs every declared check and returns the advance command only when all pass.
- `workflow_step amend-tests --file tests/<fixture> --command '<cmd>' --reason '<why>' --owner <owner>`
  adds a needed fixture; never drop one to fit the first file list.
- `workflow_step packet --output /tmp/worker-packet.json` builds the worker handoff.
- `workflow_build preflight`, `snapshot` and `refs <paths>` before a build claim;
  `workflow_build run` builds and returns the exact `next_command`;
  `workflow_build finish [--queue-receipt <ticket>]` after an interrupted handoff.
- A run that completed before newer commits: `workflow_step advance --receipt <run> --owner <owner> --recorded-source`.
  It permits diagnostic closure only. Never rerun combat to repair bookkeeping.
- `evidence_view task [--section unit|receipts|requirements|references]` and
  `evidence_view result <report>` answer saved-task and run-outcome questions.

Read [development_graph.md](../../../docs/bot_raids/development_graph.md) only
when one of these commands fails or needs a field you do not have.

## Evidence budget

Name the question and the decision it changes before each evidence call. Use
`--max-chars 6000` and about 2,000 tool-output tokens; on truncation narrow the
query instead of enlarging it. After two queries that add no new fact, change the
query or route the missing observation. Full evidence stays on disk or in DVC.

## Workers

Work directly by default. Delegate one bounded implementation when useful.
Several implementation workers need explicit user authorization and disjoint
file ownership. A raid-level request authorizes one worker per round packet,
and `raid_workloop program packet` supplies the ownership. Workers do not launch
nested agents (except GPT-6.1 Sol through `codex exec` for WCL and browser
work), and they do not commit, build, run servers or run `dvc repro/push`. A worker
packet names one mechanism, owned files plus affected callers and tests,
forbidden changes, one focused command and the expected metric; see the
[bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).

### Worker model

No model is enforced. The user is still finding the best models ("lets not
enforce models ... We just need to find the best models for now", 2026-09-29).
Pick the model you expect to do the task right the first time. Quality comes
before cost, and iterations should be as few as possible ("if sonnet is not
relyable enough for the task we need to use opus 5.5 like we did before so we
keep the quality. and reduce iteration count as much as possible").

What has worked so far (guidance, not a rule):

| Task | Worker that has worked |
| --- | --- |
| Well-scoped: a review-finding fix in named files, a test update, a bounded data extraction, or a single-module change with a clear spec | `sonnet-implementer` subagent (Sonnet, xhigh effort) |
| A whole boss packet, open-ended diagnosis, cross-cutting design, or multi-file boss or class tuning | Opus 5.5 (Agent `model: "opus"`) |
| A task where the first worker missed the spec, or a review found a real defect in its work | A stronger model from the next attempt on; don't let a weaker worker iterate |
| Review, re-review, WCL and other browser work | GPT-6.1 Sol (see [Independent review](#independent-review-gpt-6.1-sol)) |

### Fewer iterations

1. Write the complete spec up front: owned files, invariants, test
   expectations and the user decisions that apply.
2. Give each review pass one batched fix pass that covers all of its findings.
3. Re-review only the delta.

### Every implementer prompt includes

1. The packet file (or spec) and its owner skill.
2. Every user decision it touches, quoted exactly with its date (see
   [Recorded user decisions](#recorded-user-decisions)).
3. The [pre-review checklist](#pre-review-checklist) below, verbatim.
4. "Tactic and policy questions go into the handoff's `needs_user_decision`.
   Never decide them yourself."
5. "Classify every failing test with `test_baseline check`. Only
   `new_failures` count, and never call a failure pre-existing without that
   output."

## Pre-review checklist

Every item below comes from a real GPT-6.1 Sol rejection in rounds 1–2.
Implementers check their change against each one before handing off.

1. Fail closed when evidence is missing or truncated. Never certify 0 or pass
   from absent data.
2. Scope every state per attempt, run or cohort. Reset it on wipe, reset,
   stop/start or cohort change, and keep it stable across recording rotation.
3. Validate the final emitted destination, after offsets and clamps, against
   every hazard and line-of-sight rule, not just the slot.
4. When two positions each have an arrival tolerance, the guarantee must hold
   at the worst combined corner.
5. Scope changes to 10N, or to the mode the evidence covers. Do not change
   other difficulties without same-mode evidence.
6. Keep accepted results reproducible: Magmaw `b5-d1898555` stays
   byte-identical. Use canonical and raid scope only, so Stonecore and dummy
   calibration stay untouched.
7. Validate config fields strictly: type, allowed values and the actor's role.
   Malformed input must raise, not pass.
8. Record events where they actually complete. For example, a delayed
   resurrection happens after the teleport acknowledgement.
9. Add an adversarial test for each guarantee, plus a negative control that
   fails without the fix.
10. Run `test_baseline check`. Only `new_failures` count.

## Independent review (GPT-6.1 Sol)

Every review and re-review runs on GPT-6.1 Sol (user decision 2026-09-30, "seems to be better than astra"; GPT-6 Astra before that) in a
separate session that never edited the files. There are two routes:

- the `sol-reviewer` subagent; or
- Codex, run as a background command with one scratch directory per pass:

  ```bash
  mkdir -p /tmp/codexrev-<name> && codex exec -m gpt-6.1-sol -s workspace-write -C /tmp/codexrev-<name> --skip-git-repo-check --ephemeral -o /tmp/codexrev-<name>/verdict.md "<prompt>" < /dev/null > /tmp/codexrev-<name>/log.txt 2>&1
  ```

  The sandbox keeps the checkout read-only, so the reviewer exports and
  compiles under its `-C` directory. When a boss-level receipt needs the
  rollout (below), drop `--ephemeral`.

The review prompt gives the reviewer:

- the diff (raid program: the `program review-diff` file) or the file list;
- the handoffs or packet;
- the declared tests;
- one review question;
- the pre-review checklist.

It asks for:

- one JSON verdict at the end: `verdict` (`accept` or `reject`), `findings`
  (each with id, severity, file, a concrete failure scenario and a fix) and
  `tests`;
- every accepted scope the change would alter;
- `PYTHONDONTWRITEBYTECODE=1`, `pytest -p no:cacheprovider` and
  `test_baseline check` for every failing test.

### Review loop

Expect several passes: round 1 took five and round 2 took four.

1. The first pass reviews the whole change.
2. Route each finding to its owner:
   - a file a packet owns: `raid_workloop program reopen --id <packet> --reason "<finding id and text>"`.
     The fix then goes to one worker, chosen by the model table above;
   - a coordinator file: fix it yourself and record it with
     `raid_workloop program fix --reason "<finding id>: <what changed>"`;
   - a finding you believe is wrong: check it against the evidence (next
     section), and answer it with that evidence in the next pass. Never drop a
     finding silently.
3. Apply all of the pass's fixes as one batch.
4. Re-review the delta. Give the reviewer its earlier findings, the new diff,
   `diff -u <previous pass diff> <new diff>` and the files the fix touched. Ask
   it to confirm each fix and to look for regressions the fix introduced. Fixes
   introduced new regressions twice in round 2.
5. Repeat until a pass returns `accept`. Keep every pass's verdict file.
   Non-blocking follow-ups go into the next round's packet or the error ledger.

Changed files need a new review; an unchanged approval may be reused. A receipt
import failure is an attribution problem, not a code verdict. For a raid
program, record each pass with `program review` (see
[raid program](references/raid-program.md), step 4).

### Boss-level review receipts

The boss graph follows the playbook's risk tier. For `class_native` and
`shared_runtime` changes:

1. Commit the implementation, then give the reviewer the file list, the declared
   tests and one review question. The reviewer checks what the behavioral test
   executes and asserts; stateful repairs need repeated updates with unchanged
   identity.
2. The reviewer returns one JSON object with only `verdict` (`approved` or
   `changes_required`), `file_hashes` (repo-relative path -> sha256 of the
   reviewed file), `findings`, and optional `tests` and `limits`. Save it, for
   example as `/tmp/reviewer-final.json`.
3. Record it:
   - For a subagent: `pixi run python -m tools.raid_program.review_execution import-json --report /tmp/reviewer-final.json --transcript ~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<AGENT_ID>.jsonl --reviewer-session-id <AGENT_ID> --implementer-session-id <IMPLEMENTER_ID> --receipt artifacts/cata_raid_program/<unit>_review.json`.
     The reviewer id is the subagent's `agentId`, and its final message must
     contain exactly the report's JSON. The implementer id must be the one the
     graph recorded, and every hash must match the working tree now. The import
     fails with a code on a self-review, a stale hash, a transcript that does
     not end with that JSON, or a report edited after import.
   - For a Codex review: `review_execution preflight`, then `import` with
     `--rollout` under `~/.codex/sessions`.
   - Then run `workflow_step advance --receipt <that receipt>`.

## Check agent claims before acting

An agent's diagnosis is a hypothesis until evidence confirms it. Check it before
you reopen a packet, change code, ask the user or dismiss a problem because of
it:

1. Name the claim and the one observation that would refute it.
2. Look for that observation in the retained evidence (`evidence_view`, the
   kill's trace or events, the scoreboard record). Or give the claim and the
   evidence path to a second agent that did not make it.
3. Act only on a confirmed claim. Write a refuted claim into the handoff or the
   ledger so nobody repeats it.

Examples from rounds 1–2:

- "The Blood DK never uses its cooldowns" was false when checked against the
  casts.
- The Chimaeron "route stall" was actually the completion watchdog. The fix
  was to reset the watchdog on a confirmed kill.
- "The mage dispels Remedy" was checked and found false. The health samples
  showed one full Remedy in each hold, and the only removal was a Spellsteal
  before the hold. The user's conditional decision then applied: the hold starts
  at 50%.

The same rule covers two other kinds of claim:

- "Pre-existing", "unrelated" or "another packet's edit" test failures: confirm
  them with `test_baseline check`.
- An expected gain ("about +1k DPS") is unmeasured until a batch shows it.

## When to ask the user

Tactic and policy choices belong to the user. Examples:

- which tanks are DPS-gated;
- whether deaths are allowed in a phase;
- a boss-phase threshold, such as when to stop DPS or when to switch targets;
- dropping an ability from a rotation;
- changing an acceptance gate or the finish line.

1. A worker that needs such a choice puts it in its handoff's
   `needs_user_decision` as `{"id", "question", "options": [...], "recommendation", "context"}`.
   It keeps working on everything else and never picks an option itself.
2. `program handoff` records it. `resume` then returns `next_action` "ASK THE
   USER" with the open decisions, and the build is blocked.
3. Ask the user each question with its options, recommendation and context,
   then wait for the answer.
4. Record the answer verbatim:
   `raid_workloop program decide --decision-id <id> --answer "<the user's exact words>" --expect <state_sha256>`.
5. Forward the user's exact words and the date to the owning worker, never a
   paraphrase. Agents may refuse a permission that only another agent relays,
   so the quote and where it is recorded must travel with it.

Never invent a user decision. A recommendation, an agent's opinion or your own
inference is not a decision. Without a user answer the question stays open.

### Recorded user decisions

Reuse these, and do not ask again.

| Decision | User's words | Date | Recorded in |
| --- | --- | --- | --- |
| The Blood DK tank is DPS-gated; the Feral tank is exempt | "Just count blood tank as dps, leave feral out. Feral dps is negligible, but bdk is relevant." | 2026-09-27 | raid targets, `dps_gate_exempt_decision` |
| Chimaeron: deaths after Mortality begins (boss below 20%) do not fail a kill; earlier deaths do | recorded as a rule | 2026-09-27 | `blackwing_descent_10n_chimaeron.json`, `boss_window_death_exemptions` |
| Maloriak: the mage does not dispel Remedy during the add switch; otherwise stop boss DPS at 50% | "Mage should not dispell remedy. If it does maybe thats why it gets over. If not stop dps at 50%" | 2026-09-27 | `maloriak.md` dossier |
| Assassination never uses Fan of Knives in raids | "Assasination rogue dont need to use fok. Its always a dps loss" | 2026-09-27 | round-2 class rotation (dc32876966) |
| Agents pass WCL human and Cloudflare checks | "If a check appears they can click it" | 2026-09-27 | raid-encounter-research |
| Raid fixes stay raid- or canonical-scoped | "raid-only for now" | 2026-09-25 | standing rules below |
| Worker model: none enforced; pick the model that gets it right first time, quality before cost | see [Worker model](#worker-model) | 2026-09-29 | this skill |
| Research is judged per mode: a 10N unit's research counts as accepted when every claim covering 10N is resolved, even with heroic claims still open | "your decision is fine" | 2026-09-29 | `raid_program_inputs.mode_scoped_research_state` |
| WCL references must match the roster's item level: keep the ~409 roster gear, and choose reference kills near that level (about 400–415), recording each one's item level | chose "Keep ~409 gear, match refs" | 2026-09-29 | raid-encounter-research |
| Boss tactics (Atramedes, Maloriak, Nefarian) | "User raid experience" sections | 2026-09-25 to 27 | boss dossiers |

## Known test failures

Before you call a failing test "pre-existing", "unrelated" or "caused by another
packet", run:

```sh
pixi run python -m tools.raid_program.test_baseline check <pytest args, for example tests/test_raid_program.py>
```

- `new_failures` are tests missing from the baseline, or failing with a
  different reason. They are yours to fix or route, and the command exits
  nonzero.
- `known_failures` fail with the baseline's reason. Report them as known and do
  not let them block.
- `fixed` lists baseline failures that now pass. Report them.

Copy the `new_failures` and `known_failures` lists into the handoff's `tests`
entries. Only the coordinator runs `test_baseline refresh`: from committed
HEAD, after every new failure is fixed or routed, and never to hide one. Commit
`experiments/configs/known_test_failures_v1.json` with the refresh.

- Exit code 3 means pytest itself broke, for example an internal error or a
  crashed worker. Treat it as a failed test run, not as a pass.
- Known limitation: if the supervisor is killed with SIGKILL, test processes
  that detached into their own session survive. The next `check` or `refresh`
  reaps them at startup.

## Standing rules

- **Scope.** Raid and canonical scenarios only. Stonecore canaries, Phase 8
  dummy calibration and legacy Magmaw `b5-d1898555` must stay byte-reproducible
  (user decision 2026-09-25). The reviewer lists every accepted scope a change
  touches.
- **Boss damage.** A worker writes calibrated `DamageModifier` SQL to
  `sql/custom/staged/world/`, plus a registry patch request. Before the run,
  the coordinator applies the registry patch and moves the SQL to
  `sql/custom/world/`. The updater applies SQL in `sql/custom/world` at the
  next worldserver start, committed or not.
- **Builds.** Build only through `raid_workloop program build` (raid program)
  or `workflow_build run` (boss graph). Both use the host8 policy: 8 jobs, the
  exact `--parallel 8`. A round gets one build. Never build while a worldserver
  runs, and nobody edits the tree while a build runs.
- **Data.** Code and configuration go in Git. Generated data and evidence go in
  DVC: run `dvc status` and `dvc push` after each stage. Keep as little on local
  disk as possible.
- **`/tmp`.** It is a tmpfs with a per-user quota. `df` can show free space
  while the quota is full. A full quota cuts console replies, and the run then
  stalls on its command timeout. Keep `/tmp` for run directories (ingest
  archives and removes them) and small review scratch. Put WCL captures and
  other scratch in `~/.cache`.
- **Pytest fakes.** Some tests start fake processes named `worldserver`, with
  their exe under `/tmp/pytest-of-*` or `~/.cache`. A leftover fake blocks
  provisioning and runs.
  1. List them with `pgrep -a -x 'worldserver.*'`, then run
     `readlink /proc/<pid>/exe` for each.
  2. If the exe is a fake, wait for its test to end, or stop that PID with
     `kill <pid>`.
  3. Anything else is a real server, including `build/.../worldserver` and
     the pinned `/tmp/worldserver-<sha12>` copies. Do not touch it; find out
     whose it is. Never stop or restart the user's play session without
     asking.

  Never use `pkill -f` or `pgrep -f` with a pattern that also appears in your
  own command line.
- **Tests.** Report every earlier failing test, classified with
  `test_baseline check`.
- **Sessions.** Implementer and reviewer are always separate sessions.

Details on native includes, telemetry, runtime identity and build resources:
[engineering and runtime rules](references/engineering-and-runtime.md).
