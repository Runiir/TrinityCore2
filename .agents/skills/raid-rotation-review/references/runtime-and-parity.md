# Runtime inputs and parity gates

Read this reference when the review needs exact simulator/native inputs, admission
identity, consumables, effective stats, or normalized comparison output.

## Resolve and bind inputs

Resolve the current denominator with
`tools.raid_program.raid_workloop spec <spec>` and the promoted
`wowsims_cata_dps_reference_requests_v1.json` cohort. Embedded DPS in
`all_spec_references_cata_p4_v1.json` is not promotion authority. Hydrate the
existing cohort through `raid-wowsims-reference` when needed; do not infer a new
reference from different catalog numbers. Keep historical
`optimization_target_met` (which can mean 85% of a compatible reference)
separate from unresolved parity.

Record simulator source revision, binary version/hash, APL bytes, exported
`RaidSimRequest`, gear, talents, glyphs, spec options, encounter, and target.
Record Trinity Git identity, worldserver binary, profile generation/hash,
class/spec/role, route node/generation, target, gear/admission identity, and
runtime report/trace. Mark static, non-ledger diagnostic, or qualification scope.
A missing required identity permits a static review only when labeled
`informational_only_identity_incomplete`; an exploratory UI run is never
qualification evidence.

Reference shared source/binary receipts instead of retyping digests and verify
repeated digests against the actual file or receipt before freezing a report.
For a growing log, use the latest complete status matching the active epoch/attempt;
a parsed prefix is history. After closure use the final report. Report parity per
actor and field as proved match, measured mismatch, or missing observation. Do not
inherit a roster mismatch. Normalize serialized enchantment integers and separate
permanent setup from temporary native imbues. A calibration actor may have a
different GUID when its exact setup matches.

Before declaring stats or aura evidence missing, inspect retained
`botauto_diagnose` rows at `bots[].snapshot.effective_stats` and
`snapshot.native_combat_stats`. The owner's
`modifier_ledger.primary_stats[].aura_effects` records contributing spell,
caster, and amount. Bind `observed_at_ms` to the boss pull and actor; admission
gear does not describe a bot after trash deaths. Compare temporary proc carryover
and rebuff timing before blaming role code. This modifier subset is not a complete
aura or consumable ledger. Matching equipment is not proof that effects apply:
check native profession/rank requirements against skills and simulator
applicability rules.

## Native identity and edge cases

Before diagnosing a proc-gated action, map simulator action/aura IDs to native DBC
effects, replacement spells, and script bindings. One simulator ID can represent
several native forms. Prove the actual modifier or action-bar override before a
synthetic proc fixture, and trace both candidate eligibility and the direct bot cast
path; client opcode processing and server `CastSpell` need not share replacement
logic.

Derive effective cast time through native scaling and modifier precedence. A zero
base cast-time entry is not proof of an instant spell; fixtures retain calculation
inputs rather than stubbing the expected result. For a moving filler, separate a
stationary APL use condition from native cast eligibility. A missing damage proc can
make an instant unattractive while stationary without making it uncastable during
movement. Inspect loaded action rows after migrations, retain native GCD/mana/cast
checks, and validate moving-only fallback end to end.

A current-spell ID may remain during projectile flight. Join native spell state and
blocked-action results before treating it as casting time. For an interrupted cast
followed by another submission, inspect exact event order. An old terminal before a
new prepare does not identify the cancellation caller; require its native call path
or an initiator observation before adding an active-cast gate, preserving legitimate
hazard, target-change, and vehicle interruptions.

For pet support spells, inspect the owner's actual group/subgroup and native friendly
target list. A one-bot or solo fixture can still create a group. Autocast enabled
proves configuration, not eligibility or a landed owner buff; join target
restrictions with aura coverage. A target damage row can be a forwarded/shared
health callback. Join selected target to ordinary native cast/hit, separate
forwarding IDs, and never sum mirrored target views.

## Capture and normalized comparison

Obtain the live profile through
`.botauto rotations dump <class_id> <spec_tag> <role>` and save its JSON. Use a
pinned APL or UI CLI export. A read-only database projection is allowed only for a
non-authoritative static review; it has no loaded runtime generation and must be
labeled `informational_only_identity_incomplete`. Replace it with the exact live
dump before interpreting runtime behavior or qualification.

The normalized review should preserve:

- WoWSims actions, sequences, conditions, priority, prepull timing, ActionID tags,
  channels, movement/special actions, aggregate player/pet casts, hits, damage,
  aura uptime, resources, per-iteration values, and ordered first-iteration
  cast/completion/landed/aura/resource/movement events with line index/timestamp.
- Trinity spell identity, bucket/score/sort priority, gates, movement directive,
  target selector, mechanic tags, runtime attempts/selections/native results,
  landed damage, and rejection reasons as distinct facts.
- Bounded calibration `decision_timeline` with health, mana, distance,
  movement/range waits, native outcomes, first death, and attributed
  `off_target_damage_events` including attacker, victim entry/GUID, spell,
  damage, and whether the acting player was the victim.
- Route-node obligations, target identities, and completion policy.

The review tool hashes every supplied input. Before a worldserver is admitted, pass
the full exported request and require `gear_parity.status == "match"`,
`effective_stat_parity.status == "match"`, setup/consume parity,
`dps_tuning_gate.tuning_admitted == true`, and
`total_dps_comparison_gate.comparison_admitted == true`. A
`mismatch` identifies gear/setup/stat application as the first edge;
`insufficient_data` requires recapture. Stop rotation tuning in either case.
Trace-only review may compare unaffected membership, priority, rejections, and
eligible cast mix only when every mismatched input is labeled and sensitive
actions are excluded.

For `self_provided_baseline`, effective-stat matching is one-sided only for
monotonic throughput stats: exact parity or higher native value is admitted and
marked `favorable`; lower fails. Gear identity and ratings remain exact. Pass the
immutable aggregate result with `--wowsims-result` and the exact one-iteration
log with `--wowsims-debug-result`; never substitute debug for aggregate DPS/action
data.

Compare configured item IDs and native outcomes separately. Every spec receives
exact flask, food, pre-pot, and combat-potion inventory items. Food/flask require
successful pre-score native use, item-count changes, and expected auras.
Pre-pot/combat potion each require one successful native action in the correct
phase; aura presence alone is insufficient. If the simulator uses two potions and
Trinity uses none, total DPS is ineligible while unaffected rotation signals remain
usable. An aura ID alone does not distinguish external from player-owned effects;
bind permitted self effects to the frozen spec and retain caster/owner provenance.
Missing provenance is an observation gap, not permission to accept the aura globally.

Keep WoWSims aggregate metrics separate from first-iteration debug timeline and
preserve equal-timestamp log line order. Use exact route manifest and scenario
identities for dungeon review; do not substitute an older hydrated live-output
manifest.
