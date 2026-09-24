# Class qualification and encounter validation

Class qualification is reusable across bosses. Encounter performance is not.

## Before scheduling a dummy calibration

Run `pixi run python -m tools.raid_program.calibration_reuse list --spec <spec>`.
Check the shared catalog and retained actor evidence before launching a server.
Hydrate missing DVC evidence; missing local files do not justify another experiment.
Thresholds (75% class floor, 90% WoWSims fallback, 85% bundling trigger, legacy 95% `dps_gate`, historical 92.3%) are
defined once in the [raid tuning playbook](../../raid-tuning-playbook/SKILL.md).
Index existing eligible evidence without rerunning it:

```text
pixi run python -m tools.raid_program.calibration_reuse register --spec <spec> --actor-id <actor> --packet <existing-packet.json>
```

Registration verifies the existing exact-300 packet through `dps_gate`. It does
not accept a boss. Keep this catalog in Git; raw measurements remain in DVC.
Calibrate once per unchanged class/spec, setup, policy, mechanics, scoring and
reference combination. A new boss, raid size, tab, or encounter assignment is
not itself an invalidation. Failed qualification still needs repair and validation;
"once" does not mean permanently accepting the first attempt.

Reuse the packet in the next actor review's `dps_calibration` field. The verifier
recomputes the `dps_gate` ratio and setup/reference admission from retained data.
For another build or roster actor, add `calibration_compatibility` pointing to a hash-bound JSON
with `statement` and `review` file references. The statement must contain:

- `calibration_packet`, `source_build`, `target_build`, `validation_identity`,
  `actor_id`, and `spec`, exactly matching the packet and current graph inputs.
- `changed_paths`, the sorted complete Git diff path list between source builds.
- `current_setup_evidence`, hash-bound provisioning/readback evidence for the
  current actor, plus a concrete compatibility `rationale` and `author_session_id`.
- `unchanged`, with true values for `gear`, `talents_glyphs`, `professions_race`,
  `pets`, `consumables_buffs`, `class_policy`, `class_mechanics`, `shared_runtime`,
  `scoring_contract`, and `reference`.

The independent review must inspect the actual source delta and current setup,
approve that exact statement, and bind its hash through `review_execution`.
This is a semantic compatibility review, not automatic dependency analysis.
Unknown impact is not unchanged. Recalibrate only affected specs after relevant
changes; a shared runtime change may affect several specs. Encounter-only or
unrelated-spec changes may reuse evidence after that review, without another
dummy run. Keep the original packet immutable and create a new compatibility
statement for the current build/context. For another roster actor, the statement's
`actor_id` names the current actor and the setup evidence must establish equivalence
to the calibrated actor. The original packet/run/native GUID stays unchanged.
That mapping reuses the measurement without pretending the new actor was measured.

## For each boss and difficulty

Validate assignments, targetability, target switches, movement, uptime, mechanic
duties, cooldowns, survival, recovery and damage/healing in that encounter.
Compare WCL only after recording gear, buffs, composition, duration, phases,
target scope and actor duty differences. Reuse class qualification while measuring
encounter losses. A boss clear neither qualifies a class nor proves WCL parity.

## Tank damage is a required objective

When the problem is low tank DPS, start with retained matched boss WCL damage
and cast timelines. Do not route to a threat fixture merely because role=tank.
The review must contain:

- Encounter-window DPS and damage by spell, including melee, periodic effects and pets;
  body/add/phase contributions; cast cadence, resource spending and idle time.
- Gear and buffs, main/off-tank assignment, tank swaps, incoming damage,
  Vengeance or equivalent class mechanics, melee uptime and movement duties.
- A signed, ranked damage-gap comparison with explicit unknowns and one next
  repair or missing observation. Use existing timeline/comparison producers.
- Threat retention, mitigation, defensive timing, deaths and healer pressure
  as safety checks alongside damage, not substitutes for damage acceptance.

Use a tank dummy/simulator result only when target count, incoming-damage model,
resources and setup are comparable. Never compare six-target threat output to
a single-target damage denominator. A threat test answers a demonstrated threat
failure. Fixing its reporting contract does not resolve the tank damage gap.
No universal raid tank DPS threshold is inferred from a WCL total alone.

For current Magmaw Blood, use the retained `magmaw_wcl_dps_reference_v1.json`
and `magmaw_wcl_cast_timelines_v1.json` under
`experiments/configs/cata_raid_encounters/blackwing_descent/`. Investigate rune
spending, Heart Strike/Death Strike/Rune Strike, diseases, Vengeance, main-tank
uptime and exposed-head coverage. The historical 26,152 and 28,446 DPS references
are context to match, not unconditional targets or proof that threat is automatic.

## Finish the decision, not just the report

Keep class qualification and encounter acceptance separate. Every A/B comparison
ends in keep or revert under the playbook's noise rule, or in one named missing
observation. Publishing a diagnosis does not close a damage gap.
