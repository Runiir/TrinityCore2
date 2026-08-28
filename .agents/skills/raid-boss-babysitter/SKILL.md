---
name: raid-boss-babysitter
description: Read-only monitoring of an already-started TrinityCore raid-boss shard. Use when a coordinator hands an agent a verified live worldserver, exact shard identity, and telemetry location to observe boss/trash decisions, progress, stalls, DPS execution, hazards, recovery, CPU, and log growth. Do not use for building, provisioning, restarting, publishing, or mutating the run.
---

# Raid Boss Babysitter

Accept only a handoff that names the live process/log, scenario, profile, cohort, roster, attempt, and target boss. If identity is missing or changes, report it and fail closed.

## Observe without interference

- Do not send commands, change files/DB/DVC, restart services, join groups, or manufacture state unless explicitly authorized.
- Read existing status, diagnose, trace, process, and disk evidence. The coordinator owns shutdown and remediation.
- Report meaningful transitions promptly; avoid repeatedly summarizing unchanged state.

## Judge decisions

Compare bot choices with native boss/trash scripts and observed casts, auras, targets, summons, geometry, and phases. Track:

`profile_loaded -> action_selected -> blocked_before_execute -> submitted -> landed`

Also watch hazard exits, tank ownership, formations, add control, recovery/ready-check order, stuck/unstuck events, CPU/RSS, and log growth. Engagement or a wipe does not prove tactics or fidelity.

For partial-death recovery, `raid_runtime.native_recovery` is not presence
proof: it is scoped to full-wipe recovery and may remain false. Join final
status with the affected bot's diagnose row and delta trace. Report ghost/map/
corpse/current position, `recovery_attempt_count`, ordered
`death_recovery_progress` results, and the exact matching
`validation_route_recovery` rejection. Never conclude that recovery was not
entered from the aggregate alone.

## Identify termination evidence

Keep the earliest causally linked gameplay failure separate from the final
terminal reason. A loud receipt, identity, recovery, or watchdog failure that
appears after an unrelated gameplay edit is not automatically the cause of the
wipe. Report it as a later blocker until the ordered trace proves that it
changed the earlier action or outcome. In particular, do not replace a missing
mechanic candidate, failed native submission, death, or wipe with the receipt
reason produced during corpse release, worldport, pet death, or shutdown.

When a terminal signal looks unrelated, enumerate the value's writers and
observers only far enough to classify it as stable identity, transient
lifecycle, or reporting state. Return that classification to the coordinator;
the read-only babysitter must not weaken the terminal or speculate that the
most visible failure is the root cause.

- Success: the shard's declared gate is independently observable.
- Semantic stall: no monotonic route, kill, health-low-water, generation, or native milestone progress for the configured window.
- Repeated-decision or death-loop failure: the configured typed watchdog is
  reached without a normal recovery/clear edge.
- Infrastructure loss: stale/missing status, diagnose, or trace; process loss; identity drift.
- Contamination: operator/gameplay intervention, forbidden assistance, cross-shard rows, or repeated stuck recovery.

Do not use a 300-second observation deadline for a raid or dungeon. That exact
window belongs to isolated training-dummy DPS calibration. Observe the route
until a typed success/failure condition occurs; an emergency host timeout is
noncompletion evidence, not success.

Tell the coordinator whether evidence is sufficient to stop. Do not stop the run yourself.

Once the owned worldserver is absent and its final `report.json` exists, the
observation job is complete. Read the terminal classification and final forced
diagnose/trace evidence, return the compact handoff immediately, and do not
continue waiting for a process that has already shut down.

Never print or ingest an entire raw JSONL/log line. For a decisive event count,
stream the normalized batch, filter only the required action/result fields,
deduplicate trace events by `(bot_guid, sequence)`, and cap the rendered output.
Count an explicit result such as `native_instance_runback_repath_submitted`, not
the number of times that text is repeated inside later trace snapshots.

## Report compactly

Return exact identity, last route/node and boss phase, decisive bot decisions, profile execution counts/blockers, native mechanic comparison, stuck/CPU/disk facts, and the smallest next investigation. Label unknown facts as unknown.
