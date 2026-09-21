---
name: raid-rotation-review
description: Translate and compare TrinityCore bot rotation code, database action profiles, candidate arbitration, movement, native outcomes, route mechanics, and live traces with WoWSims Cataclysm APLs, result action logs, and timelines. Use when reviewing DPS rotations, spell priority, proc/resource gates, movement loss, boss-mechanic decisions, action rejection loops, gear/setup differences, simulator action cadence, or a discrepancy between WoWSims and observed bot behavior.
---

# Raid rotation review

Build an attributable comparison from simulator policy to native outcome. Keep
simulation, Trinity selection, movement, submission, landing, and encounter
mechanics as separate layers. The review finds the first missing edge; it does
not turn a metric delta into a gameplay patch.

## Retrieval and stage routing

Start with `evidence_view task` and execute its returned saved-task command, then
run the returned `evidence_view admission` and comparison commands as applicable.
Use the resulting compact admission/compare output before reading any reference or
source. If command syntax or output fields are needed, read only
[references/evidence-views.md](references/evidence-views.md); then issue selected
narrow queries. Never dump full histories, nested reports, or raw JSON into
context. Load this skill once.

For an unanswered schema question, use `inspect --path` once to list nested field
names/types, then select only the relevant observation. Never enumerate every key
with separate queries or concatenate many full pages into one tool response.
For diagnosis, inspect the highest-ranked unresolved gap first. Stop retrieval
when the evidence supports the conclusion or identifies a specific missing
observation; another page without a new question is not progress.

Load a deep reference only for the unanswered question named by that compact
output: [post-run-dps-review.md](references/post-run-dps-review.md)'s damage-loss
accounting section only before recommending an implementation; it requires signed
component gaps, ordinary casts versus triggered/proc copies, and bounded net gain.
Missing attribution routes to diagnosis. Read [translation-model.md](references/translation-model.md)
for action or condition mapping, [runtime-and-parity.md](references/runtime-and-parity.md)
for exact inputs and gates, and [decision-trace-and-mechanics.md](references/decision-trace-and-mechanics.md)
for a decision-chain, route-mechanics, or reporting question. Read
[local-wowsims.md](references/local-wowsims.md) only when a local server/binary is
in scope, and only a matching class note. Parallel reviewers use the coordinator's
actor subset and shared context; the overall reviewer joins all actors.

For local Laya or hosted Jev, use the existing shadow procedure and check the pinned
model/revision. Packets must fit both question/options and total context budgets;
token saturation, confidence, or prediction agreement does not prove retention or
repair. Keep missing external access explicit. One accepted repair does not certify
the roster or require simulator regeneration.

## Exact inputs and gates

Class dummy qualification is shared across encounters; consult the calibration
catalog before requesting a new measurement. For tank damage gaps, compare boss
WCL damage/casts with matched incoming-damage, tank-duty and phase context;
retain survival/threat as separate safety checks. Follow
[class and encounter validation](../raid-performance-loop/references/class-and-encounter-validation.md).
Do not turn an incompatible threat-fixture denominator into another class tuning
task, or refuse a proven partial recovery solely because it remains below 95%.

Resolve the denominator with `tools.raid_program.raid_workloop spec <spec>` and
the promoted `wowsims_cata_dps_reference_requests_v1.json` cohort. Embedded DPS
in `all_spec_references_cata_p4_v1.json` is not promotion authority; hydrate the
existing cohort through `raid-wowsims-reference` when needed. Historical
`optimization_target_met` can mean only 85% of a compatible reference and stays
separate from unresolved parity. Current acceptance requires 95% per DPS actor,
using policy v3 and a run-bound `dps_calibration` packet verified by
`tools.raid_program.dps_gate`. Account for DTR within the total 5% gap, never as
an additional 1,000 DPS waiver. Review remaining losses even when the ratio passes.

Record simulator revision/binary, APL bytes, exported `RaidSimRequest`, gear,
talents, glyphs, options, encounter/target, Trinity commit/binary, profile
generation, class/spec/role, route node/generation, target, admission identity,
runtime report/trace, and whether the review is static, diagnostic, or
qualification. If an identity is absent, continue only as
`informational_only_identity_incomplete`. Use the latest complete live status
for the active epoch/attempt and the final report after closure. Report parity per
actor/field as proved match, measured mismatch, or missing observation; never
inherit a roster mismatch.

Before interpreting total DPS, stat-sensitive cadence, or damage per event, join
the full exported request/result/debug input to the immutable native scoring-window
observation. Require exact gear/setup/consume parity,
`gear_parity.status == "match"`,
`effective_stat_parity.status == "match"`,
`dps_tuning_gate.tuning_admitted == true`, and
`total_dps_comparison_gate.comparison_admitted == true`. For
`self_provided_baseline`, gear and ratings remain exact while a higher native
monotonic throughput stat may be admitted and marked `favorable`; lower fails.
For `controlled_live_parity`, effective stats are exact. Do not tune native
coefficients or priorities from raw deltas before these exact joined gates pass.
Missing or mismatched inputs route to recapture/reference/stat application, not
a guessed repair. Trace-only action membership, priority, rejection, and eligible
cast mix may remain usable only when every mismatch is labeled and sensitive
actions are excluded.

Compare aggregate result metrics with the immutable aggregate input and ordered
first-iteration debug timeline separately; never substitute debug for aggregate
DPS/action values. Keep ordinary player casts separate from triggered copies,
ticks, AoE impacts, and pet actions. A configured item or aura is not proof of
native use: verify food/flask pre-score uses, count changes, expected auras, and
pre-pot/combat-potion phase actions. Preserve caster/owner provenance for aura
IDs.

## Causal review and report

Use the forward chain:
`policy -> observed state -> candidate/gates -> arbitration/resource claim ->
movement/authority -> native submission -> core outcome -> landed
effect/damage/progress`. Stop at the first missing or contradictory edge. Do not
call a profile correct because a spell exists, or a rotation wrong when range, LOS,
route authority, setup, resource ownership, or mechanic preemption is the first
failure. Ordinary movement yields to hazards at declared priority without taking
unrelated GCD/cast resources; ordinary DPS continues when independent. Route
evidence is completion-watchdog driven with typed terminal reason. Exactly 300
seconds is reserved for isolated training-dummy calibration, never raid completion.

Report one concrete counterexample with severity/type, exact actor/spec/node/target
and source identities, policy/profile/trace paths, expected versus observed
predicate/action/outcome, comparison validity, smallest player-like fix, and
static/non-ledger/live verification. Never recommend state manufacture, forced
target/cast success, teleportation, scoring-time health/resource refill, or
denominator-derived tuning. Keep clear acceptance, repair acceptance, and overall
roster performance separate.
