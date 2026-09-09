---
name: raid-rotation-review
description: Translate and compare TrinityCore bot rotation code, database action profiles, candidate arbitration, movement, native outcomes, route mechanics, and live traces with WoWSims Cataclysm APLs, result action logs, and timelines. Use when reviewing DPS rotations, spell priority, proc/resource gates, movement loss, boss-mechanic decisions, action rejection loops, gear/setup differences, simulator action cadence, or a discrepancy between WoWSims and observed bot behavior.
---

# Raid Rotation Review

Build an attributable comparison from simulator policy to native outcome. Keep
simulation, Trinity selection, movement, submission, landing, and encounter
mechanics as separate layers.
Before diagnosing a proc-gated action, map simulator action/aura IDs to native
DBC effects, replacement spells and script bindings. A simulator can represent
several native spell forms with one ID. Prove the actual native modifier or
action-bar override before building a synthetic proc fixture, and trace both
candidate eligibility and the direct bot cast path. Client opcode processing
and server-side `CastSpell` need not apply the same replacement logic.

For pet support spells, inspect the owner's actual group/subgroup state and
the native friendly-target list. A one-bot or "solo" fixture can still create
a group. Enabled autocast proves configuration, not target eligibility or a
landed owner buff; join native target restrictions and aura coverage.

A target damage row can be a forwarded/shared-health callback. Before claiming
direct target selection, join the actor's selected target and ordinary native
cast/hit; separate forwarding spell IDs and never sum mirrored target views.

For a parallel review, use the coordinator's exact actor subset and shared run
context. The overall reviewer joins all actors; do not repeat another worker's
deep review. Read only the matching note under `references/classes/` when one
exists. These notes supplement the common method and never replace current
references, runtime evidence or encounter ownership.

## Load the review model

For the dedicated DPS review of a closed raid, dungeon, or calibration run,
start with [references/post-run-dps-review.md](references/post-run-dps-review.md).
It reviews every bot and compares each DPS actor with promoted WoWSims action
structure and identified Warcraft Logs kills, then selects the next bounded
repair. Missing external access stays explicit. One accepted repair does not
certify the roster's overall performance or require simulator regeneration.

Read [references/translation-model.md](references/translation-model.md) before
interpreting a comparison. If a local WoWSims server or downloaded binary is in
scope, also read [references/local-wowsims.md](references/local-wowsims.md).

## Establish exact inputs

Record hashes and identities before comparing:

- WoWSims source revision, binary version/hash, APL bytes, exported
  `RaidSimRequest`, gear, talents, glyphs, spec options, encounter, and target.
- Trinity Git identity, worldserver binary, profile snapshot generation/hash,
  class/spec/role, route node/generation, target, gear/admission identity, and
  runtime report or trace.
- Whether the task is a static review, non-ledger diagnostic, or qualification
  audit. Never promote an exploratory UI run into qualification evidence.

Reference generated receipts for shared source/binary identity instead of
retyping long digests in every class report. Verify any repeated digest against
its actual file or receipt programmatically before freezing the report.

If a required identity is absent, continue a static review but label the result
`informational_only_identity_incomplete`.

For a growing live log, use the latest complete status matching the active
epoch/attempt for current progress. An earlier parsed prefix is history, not
the live state. After closure, use the final report for run-level outcomes.

Report parity per actor and field: proved match, measured mismatch, or missing
observation. Do not inherit a roster-wide mismatch from an earlier run. Normalize
serialized enchantment integers and distinguish permanent setup from temporary
native imbues. A calibration actor may have a different GUID if its exact setup
matches; missing effective stats do not erase verified gear identity.
Matching stored equipment is not proof that its effects apply. Check native
profession/rank requirements for equipped enchants against the actor's skills
and the simulator's actual applicability rules before diagnosing a proc or
stat-application defect.

Record `reference_class` explicitly. `self_provided_baseline` is a one-sided
minimum throughput floor with all external raid buffs and pre-applied target
debuffs disabled. It includes the frozen player's own pet, class effects,
professions, flask, food, pre-pot, combat potion, racial, and profession
actions. `controlled_live_parity` is the reference for exact action and damage
comparison. `upstream_full_throughput` is only a capability/UI cross-check
unless every runtime input matches. A difference among these classes is not a
rotation failure.

An aura ID alone does not distinguish an external buff from the player's own
class effect. Bind permitted self effects to the frozen spec setup and retain
caster/owner provenance. Missing provenance is an observation gap, not proof of
external contamination or permission to accept the aura globally.

## Build the normalized comparison

Obtain the live profile with:

```text
.botauto rotations dump <class_id> <spec_tag> <role>
```

Save the returned JSON. Use a pinned APL file or the UI's `CLI Export`, then run:

```bash
pixi run python -m tools.bot_ml.review_rotation_mechanics \
  --reference-class self_provided_baseline \
  --wowsims-apl /path/to/apl-or-raid-request.json \
  --wowsims-result /path/to/raid-sim-result.json \
  --wowsims-compute-stats /path/to/compute-stats.json \
  --trinity-profile /path/to/botauto-rotation-dump.json \
  --runtime-report /path/to/report.json \
  --route-manifest dataset/validation_scenarios/validation_routes.jsonl \
  --route-scenario-id stonecore_5h \
  --output /tmp/rotation-mechanics-review.json
```

Before a worldserver is admitted, a read-only database projection can be used
for an explicitly non-authoritative static review:

```bash
pixi run python -m tools.bot_ml.review_rotation_mechanics \
  --wowsims-apl /path/to/apl-or-raid-request.json \
  --trinity-worldserver-conf trinity-worldserver-test.conf \
  --trinity-class-id 6 \
  --trinity-spec-tag frost_death_knight \
  --trinity-role dps
```

This path never claims a loaded runtime generation and is emitted as
`informational_only_identity_incomplete`. Replace it with the exact
`.botauto rotations dump` before interpreting live behavior or qualification.

Pass only the available inputs. The tool hashes every supplied file and emits:

- normalized WoWSims actions, sequences, condition leaves, and priority order;
- prepull timing, tagged ActionID variants, channel/movement/special actions, and
  prepull-versus-combat phase mismatches;
- WoWSims aggregate player/pet casts, hits, damage, aura uptime, resources, and
  per-iteration values;
- ordered first-iteration cast/completion/landed-effect/aura/resource/movement
  events when debug logs are present, preserving line index and timestamp;
- normalized Trinity spell identity, bucket/score/sort priority, gates,
  movement directive, target selector, and mechanic tags;
- shared/missing spell identities, pairwise order inversions, condition-family
  gaps, and explicitly unmapped expressions;
- runtime attempts, selections, native results, landed damage, and rejection
  reasons as distinct facts;
- the bounded calibration `decision_timeline`, including health, mana, target
  distance, movement/range waits, native outcomes, and the first observed death;
- attributed `off_target_damage_events`, including attacker, victim entry/GUID,
  spell, damage, and whether the victim was the acting player;
- route-node mechanic obligations, target identities, and completion policy.

Before interpreting total DPS, stat-sensitive cadence, or damage per event,
pass the full exported `RaidSimRequest` to `--wowsims-apl` and require
`gear_parity.status == "match"`, `effective_stat_parity.status == "match"`,
consume and setup parity, `dps_tuning_gate.tuning_admitted == true`, and
`total_dps_comparison_gate.comparison_admitted == true`.
Trace-only review may still compare unaffected action membership, priority,
rejections, and eligible cast mix when it labels every mismatched input and
excludes sensitive actions. The tool compares the exact request
equipment manifest with Trinity's scoring-window gear observation, then the
exact WoWSims `finalStats` owner vector with Trinity's immutable
`scoring_start_stats` captured at the published `t=0` edge. For a required pet,
it also compares Trinity's scoring-start pet vector with the debug result's
timestamp-zero `Pet stats`, while retaining `Pet inherited stats` as the
inheritance diagnostic. `mismatch` means gear/setup/stat application is the first
broken edge; `insufficient_data` means recapture the missing artifact. In both
cases stop rotation tuning rather than changing priorities or coefficients to
hide the discrepancy.

For `self_provided_baseline`, effective-stat `match` is one-sided only for
monotonic throughput stats: exact parity or a higher Trinity value is admitted
and marked `favorable`; lower values still fail. Gear identity and ratings stay
exact. Pass the immutable aggregate result with `--wowsims-result` and the exact
one-iteration log result with `--wowsims-debug-result`; never substitute the
debug result for the DPS/action aggregate.

For consumables, compare configured item IDs and native outcomes separately.
Every spec receives its exact flask, food, pre-pot, and combat potion as
inventory items. Food and flask require successful pre-score native item uses,
item-count changes, and the expected auras. Pre-pot and combat potion each
require one successful native item action in the correct phase. Aura presence
alone cannot prove item use. If WoWSims uses two potions and Trinity uses none,
total DPS is ineligible, but unaffected rotation signals remain usable.

Treat its comparisons as review leads, never semantic-equivalence or DPS
claims. Inspect the exact code/data for every reported gap.

Use the translation primarily in the forward direction:

```text
APL or Trinity policy -> observed state -> chosen/submitted action -> game effect
```

The reverse direction is only attribution: take an observed spell, aura,
resource event, movement, or mechanic outcome and locate the APL path or Trinity
candidate/code path that could have produced it. Do not try to synthesize a
correct APL from arbitrary C++ control flow.

For dungeon review, prefer the canonical generated `validation_routes.jsonl`
plus an exact `--route-scenario-id`. Do not silently substitute an older
hydrated live-output manifest. Confirm that the selected scenario and route
node identities match the current generated run plan before interpreting the
result.

## Trace a decision end to end

Include decision complexity when traces show conflicting owners, oscillation,
repeated decisions, or opaque fallback behavior. The 2026-08-28 native audit
measured average CCN 15.80, p95 73, 45 functions above 100, and a maximum of
464. These values are a baseline, not proof of a bug: remeasure the current
tree and identify the first broken edge. Recommend a split only when it removes
overlapping ownership or branches from the effective decision graph. Moving
branches into helpers while calling all of them preserves the same complexity.
Prefer independent typed candidates, explicit resource claims, stable intent
reasons, and traces for admission, rejection, execution, and outcome. Keep the
priority queue as the decision boundary and movement as a separate
set-and-forget execution concern.

For each suspicious spell or mechanic, reconstruct this chain:

```text
source policy
  -> observed player/target/encounter state
  -> built candidate and executable gates
  -> priority/resource arbitration
  -> movement or mechanic preemption
  -> native request submission
  -> core outcome
  -> landed effect/damage/progress
```

Stop at the first missing or contradictory edge. Do not call a rotation wrong
when the real failure is range, LOS, route authority, setup, resource ownership,
or a higher-priority mechanic. Do not call a profile correct merely because the
spell exists in it.

Deduplicate replayed trace rows by actor and native sequence. Keep submissions,
primary impacts, periodic ticks, triggered effects and per-target AoE impacts
separate; event counts are not cast counts. A no-impact interval can contain
useful instant actions or required movement. Join native terminal outcomes before
classifying a missing impact as a failed cast or idle time.

Inspect counter producers before using their labels. In the current DPS/tank
calibration collector, `action_attempts` counts valid selections even when the
outcome is casting, global cooldown, or no action; it is not a cast-start count.
Use per-spell `decision_timeline` rows with `result=ok` for successful submissions,
retain excluded outcomes separately, and still distinguish submission from landing.

Do not treat aggregate reasons such as `no_trained_heal` or
`no_instant_heal_while_moving` as the first broken edge. Correlate the exact
actor and target with distance, LOS, movement state, profile identity, and the
per-spell rejection mask. Verify geometry in full 3D when the runtime range
gate does. A selected target plus a profile row is still insufficient until a
legal candidate reaches native submission and a landed effect.

Inspect these sources as applicable:

- `BotClassSpecActionProfile.{h,cpp}` for profile gates and candidate evidence.
- `BotWorldPopulationMgr.cpp` for context, movement, mechanic ownership, and
  runtime telemetry.
- `BotActionArbiter.h`, `BotNativeActionIntent.h`, and
  `BotMeleeAutoAttackIntent.h` for priority and resource conflicts.
- Route manifests and `BotEncounterMechanicCatalog` for encounter obligations.
- `action_attempts`, `spell_damage`, `last_action_rejections`,
  `last_chosen_action`, `combat_attempt`, and `decision_kernel` in evidence.

## Review rotations

Compare more than spell membership:

- prepull/persistent setup and initial resources;
- player, pet, poison, form, presence, stance, seal, totem, and autoattack state;
- exact priority and tie-breaking;
- proc, owned aura/disease/dot, stack, duration, resource, rune, combo point,
  target-health/execute, target-count, cooldown, and cast-time predicates;
- range envelope, movement compatibility, target selection, area/multidot
  semantics, and pet commands;
- waits, strict sequences, item actions, unsupported simulator-only actions,
  and absent-state numeric semantics;
- observed action distribution, failure/rejection distribution, active uptime,
  resource starvation/capping, movement loss, and off-target effects.

For pet specs, compare owner and pet separately. Bind pet identity, alive/target
uptime, action or landed-event counts, per-event damage, and total damage share.
A matching pet share can hide uniformly low output, while low absolute pet
damage does not prove idle AI when event cadence matches.

After producing the closed review for a bounded spec canary, run
`tools.bot_ml.spec_canary_gate`. Its policy deliberately routes event-cadence
failures to `raid-role-implementation` and matching-cadence damage failures to
`raid-class-mechanics-implementation`; it never authorizes repeated tuning.

WoWSims aggregate metrics cover all iterations; its debug log/timeline normally
covers the first iteration only. Compare aggregate distributions separately
from exact ordered timeline events. At equal displayed timestamps, preserve log
line order because the formatted timestamp has limited precision.

Flag an APL leaf with no Trinity observation/gate as a coverage gap. Flag a
Trinity heuristic with no simulator analogue as an intentional divergence until
its player-like rationale and evidence are documented.

The static profile dump has no live candidate score. Treat same-bucket ordering
as unresolved unless runtime candidate evidence supplies scores; only bucket
differences and observed score/tie-break facts establish an ordering.

## Review boss and dungeon mechanics

Do not compare a raid or dungeon against a fixed 300-second observation as if
it were a completion gate. That exact duration belongs to isolated
training-dummy DPS calibration. For route evidence, inspect the complete
watchdog-driven attempt and its typed terminal reason: normal clear,
semantic/no-progress stall, repeated decisions, excessive death loops,
infrastructure loss, contamination, or interruption.

Map every required route obligation to a typed observation, candidate, resource
claim, native action, and terminal/completion observation. Verify that:

- hazards and mechanic movement preempt ordinary movement at the declared
  priority without unnecessarily owning GCD/cast resources;
- ordinary DPS continues when its resources are independent and pauses only
  for observed safety/authority reasons;
- target switches, interrupts, dispels, cooldowns, tank swaps, recovery, and
  interactions retain exact actor/target/attempt/route identity;
- retryable rejection falls through or retries with bounded diagnostics;
- a repeated fail loop terminates attributable evidence for investigation,
  while dungeon execution itself has no arbitrary overall time cap.

WoWSims does not model route pathing or boss-script authority. Use it for class
action semantics and controlled encounter inputs, then review mechanics against
Trinity's native route and script observations.

## Report findings

Lead with the first broken edge and give one concrete counterexample. For each
finding include:

- severity and whether it is a correctness, liveness, evidence, or tuning issue;
- exact spec/node/actor/target and source hashes;
- WoWSims policy path and Trinity code/profile/trace path;
- expected versus observed predicate/action/outcome;
- whether the mismatch invalidates comparison or only explains performance;
- the smallest player-like fix and the static/non-ledger/live verification.

Never recommend direct state manufacture, forced target/cast success, teleport,
health/resource refill during scoring, or denominator-derived tuning. Prefer
typed observations, candidates, native requests, and later outcome receipts.

A pinned reference contract and a counterexample through the actual production
evaluator can establish a policy defect before its frequency is visible in a
live trace. Do not require an observation-only build solely to admit that repair.
Keep native frequency, DPS cost and improvement claims unproven until measured.
This does not justify coefficient tuning, missing-reference assumptions or
fabricated runtime outcomes.
