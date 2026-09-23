---
name: trinity-orchestrator
description: Own broad requests such as implement boss bots through diagnosis, repair workers, builds and live validation. Use for encounter-wide implementation and optimization, not only explicit orchestration requests.
---

# Trinity orchestrator

The primary agent owns the user's encounter objective; a specialist result is an
intermediate step, not completion. The tuning loop, finish line, thresholds and
risk tiers are in [raid-tuning-playbook](../raid-tuning-playbook/SKILL.md). This
skill covers startup, the saved graph, workers and review.

## Startup and continuation

Inspect `git worktree list --porcelain`, use the checkout holding `master`, and
verify it matches the saved `coordinator_worktree`. Preserve unrelated dirty
work; do not build an old or detached checkout or copy task state between
worktrees. Run `raid_workloop start "<request>"` for a named boss and mode, or
`raid_workloop resume` to continue (read-only); `start --preview` resolves a
request without selecting it. Read the returned
`unit.next_action`, `owner_skill` and `latest_assessment`, then execute the
returned step. After every transition execute the next step. Before a final
reply run `resume`; continue while the parent objective is open. After context
compaction, run `resume` once instead of rereading skills and old receipts.

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

## Workers and review

Work directly by default. Delegate one bounded implementation when useful;
several implementation workers need explicit user authorization and disjoint
file ownership. Workers do not launch nested agents. A worker packet names one
mechanism, owned files plus affected callers and tests, forbidden changes, one
focused command and the expected metric; see the
[bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).

Review follows the playbook's risk tier. For `class_native` and `shared_runtime`
the reviewer is a separate session that never edited the files:

1. Freeze the implementation (commit it) and hand the reviewer the file list,
   the declared tests and one review question. The reviewer checks what the
   behavioral test executes and asserts; stateful repairs need repeated updates
   with unchanged identity.
2. The reviewer returns one JSON object with only `verdict` (`approved` or
   `changes_required`), `file_hashes` (repo-relative path -> sha256 of the
   reviewed file), `findings`, and optional `tests` and `limits`. Save it as a
   file, for example `/tmp/reviewer-final.json`.
3. Record it with
   `pixi run python -m tools.raid_program.review_execution import-json --report /tmp/reviewer-final.json --transcript ~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<AGENT_ID>.jsonl --reviewer-session-id <AGENT_ID> --implementer-session-id <IMPLEMENTER_ID> --receipt artifacts/cata_raid_program/<unit>_review.json`.
   The reviewer id is the subagent's `agentId`; its transcript is the persisted
   JSONL named after it, and the JSON in its final message must equal the
   report. The implementer id must be the one recorded in the graph; every hash
   must match the working tree now; a self-review, a stale hash, a transcript
   that does not end with that JSON, or a report edited after import fails
   with a code. Then `workflow_step advance --receipt <that receipt>`.
   A Codex reviewer rollout can instead go through
   `review_execution preflight` and `import` (`--rollout` under `~/.codex/sessions`).

Changed files need a new review; unchanged approval may be reused. A receipt
import failure is an attribution problem, not a code verdict.

Details on native includes, telemetry, runtime identity and build resources:
[engineering and runtime rules](references/engineering-and-runtime.md).
