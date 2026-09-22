---
name: raid-performance-loop
description: Coordinate bounded raid and class repairs, join specialist results, and continue through live validation until the user's objective is achieved.
---

# Raid performance loop

Coordinate one bounded repair at a time while preserving the encounter-wide parent
objective, every actor's open requirements, and the distinction between diagnosis,
implementation, review, build, live acceptance, and publication. A specialist
handoff or passing canary is progress, not completion while the parent remains open.

## Authority and evidence

Startup, worktree selection, `start`/`resume` semantics, and continuation authority
belong to [trinity-orchestrator](../trinity-orchestrator/SKILL.md); follow that skill
instead of creating a second startup protocol. Use the existing command first. For
admission and saved-task queries, use `evidence_view admission` and
`evidence_view task`, with command details in
[rotation evidence views](../raid-rotation-review/references/evidence-views.md).
Then issue selected narrow queries. Pass compact comparisons and decisive event pages
to workers or advisory models; never dump graph history, raw reports, or generated
datasets. Missing evidence is unknown and becomes a bounded capture task.
For post-run triage, use the [tool-call examples](../raid-rotation-review/references/evidence-views.md#tool-call-examples):
read failed checks and the requested repair's metric, then act. Keep repair outcome,
reference eligibility and parent acceptance separate. A missing reference binding
does not justify repeating the same gameplay run or discarding a measured repair;
resolve that binding while leaving qualification open.

Read the current result at the top of
[shared_worldserver_workflow_20260907.md](../../../docs/bot_raids/shared_worldserver_workflow_20260907.md)
and only the matching [error-ledger entry](../../../docs/bot_raids/error_ledger.md).
Historical entries do not override current state. Keep the active-work-unit status
consistent with the observed edge, preserve immutable receipts, and update the
workflow's latest-run paragraph and ledger edge together when closing a run,
including failures before the boss.

## Parent objective and repair loop

For a roster-wide request, keep an actor acceptance table with each actor's native
result, reference limitations, unresolved cause, next action, and validation state.
Update every actor after each closed run; an accepted actor or improved raid total
does not close other rows. Continue to the next actionable row after publication.
Preserve the requested composition and distinguish actual from requested roles.

Use one loop: inspect the failed run, identify the earliest actionable mismatch,
repair it, test affected behavior, independently review risky changes, build once,
run the completion-watchdog attempt, close evidence, publish, and route the next
edge. Before repeating a measurement, inspect `recent_attempts`,
`failure_counts_by_edge`, and prior unit names; a renamed edge is not new evidence.
At ten repeats of the same first-broken edge, stop unchanged retries and change the
hypothesis or architecture after recording the causal summary.

A short diagnostic may answer startup/lifecycle questions but cannot be accepted DPS:
isolated dummy calibration is exactly 300 scoring seconds, while raids and dungeons
use the generated watchdog and typed terminal reasons. A development clear requires
native boss death but does not qualify a full raid, every mechanic, or training data.
A trash skip does not validate a route regression. Count death, release, runback,
resurrection, regroup, and resumed progress separately; bind recovery entrance to
the immutable admission receipt, and keep death-loop/stall limits. Read full-route
lifecycle events before declaring an optional recovery gate exercised.

## Gates and routing

Separate reusable class qualification from per-boss validation. Before scheduling
a dummy run, check the shared calibration catalog and retained evidence using
[class and encounter validation](references/class-and-encounter-validation.md).
For low tank DPS, require the matched WCL damage/cadence review described there;
a threat test is not a substitute. A proven partial recovery may be accepted below
95% while final qualification stays open. Every comparison must end in a repair,
revert, supported keep decision, or one explicit missing observation.

Every DPS actor must reach at least 95% of its current promoted self-provided
WoWSims reference in an attributable, setup-admitted 300-second dummy window.
Use policy v3 and `tools.raid_program.dps_gate` to bind the retained run/report to
the actor review's `dps_calibration` packet. Historical 75/85% flags, a tank/healer
role check, an observation repair or a raid clear cannot close this requirement.
A roughly 1,000 DPS Dragonwrath difference explains part of the total gap; it is
not an extra allowance, denominator reduction or permission to round up to 95%.
Keep raid mechanics, WCL comparison and per-actor encounter acceptance separate.

Do not tune native class coefficients, priorities, or damage from a raw delta. Before
any stat-sensitive cadence, event-damage, or DPS repair, join the exact promoted
WoWSims request/result/debug inputs to the native scoring-window observation and
require gear identity, effective-stat parity, setup/consume parity,
`dps_tuning_gate.tuning_admitted == true`, and
`total_dps_comparison_gate.comparison_admitted == true`. For
`self_provided_baseline`, exact gear/ratings remain required and a higher native
monotonic throughput stat may be marked `favorable`; lower values fail.
`controlled_live_parity` requires exact parity. Missing or mismatched joined gates
route to capture/reference/stat application, never guessed coefficients. Keep
ordinary player casts separate from proc/triggered copies, ticks, AoE impacts, and
pet actions before accounting for loss.

Route cadence, targeting, resources, healing choices, and pet policy to
`raid-role-implementation`; matching setup/stats/cadence with wrong event damage
to `raid-class-mechanics-implementation`; encounter facts or native scripts to
`raid-encounter-research` or `raid-encounter-implementation`; shared movement,
submission, recovery, or lifecycle to `raid-bot-runtime-implementation`; exact
references to `raid-wowsims-reference`; evidence and cleanup to
`raid-evidence-lifecycle`. Movement-only work does not require a new simulator
run. Native terrain owns pathing: no bot Z steering, teleportation, global
tolerance relaxation, or encounter MMAP workaround.

## Workers and review

Use Luna max for implementation, ambiguous causal diagnosis, and independent review;
keep implementer and reviewer in separate sessions. Do not use nested agents.
Give one owner one evidence packet, one hypothesis, production files plus affected
callers/tests, forbidden changes, focused Pixi command, and expected native outcome.
Use the [bounded packet](references/bounded-work-unit-contract.md),
[causal routing](references/causal-routing.md), and
[handoff contract](references/handoff-contract.md). Predictions and confidence are
advisory; preserve provider/model identity, requests, responses, missing fields,
and contradictory findings. A `no_action` resolution or wait is not a failed
native cast. Keep healing denominators explicit, and do not let model agreement
erase another actor's open issue.

Assign one dedicated `raid-rotation-review` owner to every raid, dungeon, or
calibration attempt, including successful clears. It reviews every actor and
returns a compact DPS/HPS table, matched WoWSims/WCL comparisons, ranked losses,
and one next repair or missing observation. Keep throughput acceptance separate
from boss-clear and overall roster acceptance.

Read [coordination and live-validation details](references/coordination-and-live-validation.md)
only for run closure, recovery, development/qualification boundaries, or dispatch/build
rules. Read [parallel role review](references/parallel-role-review.md) only when
several roles underperform, and [recurrence procedure](references/recurrence-procedure.md)
when a previously green edge returns.
