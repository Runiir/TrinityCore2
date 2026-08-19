---
name: raid-encounter-implementation
description: Implement or repair one Cataclysm raid boss or instance-script slice from an evidence-reviewed encounter contract. Use for native C++ boss state machines, instance state, spell scheduling, summon and targeting behavior, difficulty handling, loader or database bindings, replay coverage, and the observation/action/outcome hooks bots need. Do not use to research mechanics, tune class rotations, orchestrate shards, or publish evidence.
---

# Raid Encounter Implementation

Implement one bounded encounter work unit without inventing missing mechanics or hiding server-side assistance in bot behavior. The reviewed dossier and claim ledger define the intended encounter; native execution and telemetry prove it.

## Required inputs

Before editing code:

1. Run the exact work-unit query:

   ```bash
   pixi run python -m tools.raid_program.raid_workloop boss INSTANCE BOSS --mode 25H
   ```

2. Read the returned strategy dossier, encounter contract, claim ledger, script-readiness entry, and source paths.
3. Read [references/native-script-contract.md](references/native-script-contract.md).
4. Stop if a material numeric or behavioral claim is unresolved. Hand it back to `raid-encounter-research`; do not guess.

The input identity is `(git commit, instance, boss, mode, strategy revision, script-readiness revision)`. Report it in the handoff.

## Scope rules

- Own one boss and the smallest required instance slice.
- A missing boss script may require loader, instance-state, and database bindings; keep those changes in the same work unit.
- Do not change class rotations, roster composition, WoWSims inputs, route policy, or unrelated encounters.
- Reuse current repository conventions and production helpers. Do not create a parallel Python model of encounter truth.
- Keep client-valid mechanics native. Do not force bot targets, teleport bots through mechanics, grant immunity, fabricate damage, or award encounter credit outside normal server paths.
- Preserve unresolved current behavior only when the contract explicitly labels it as a temporary compatibility value.

## Implementation loop

### 1. Classify the gap

Use the work-unit classification:

- `implement_missing_boss_script`: add the smallest complete native slice.
- `audit_and_validate_existing_boss_script`: compare every material contract claim with source and fix the first mismatch.
- `blocked_by_research`: make no gameplay implementation.

Record the first broken edge, not a vague symptom:

`encounter state -> event schedule -> actor/target choice -> native cast or movement -> aura/damage/summon result -> phase transition -> completion/credit -> telemetry observation`

### 2. Implement production behavior

Cover only the mechanics needed by the reviewed contract:

- reset, engage, wipe, evade, death, and credit paths;
- deterministic phase transitions and event scheduling;
- difficulty-specific spell IDs and numeric values;
- valid actor identity, target filters, range, facing, and line-of-sight rules;
- summon ownership, cleanup, and instance-state persistence;
- loader and database bindings where required;
- stable mechanic identifiers exposed to diagnostics.

Prefer helpers used by both production execution and native replay/tests. A test-only reimplementation is not proof of the production state machine.

### 3. Add observation, not control

Expose enough deterministic state for bot arbitration and evidence:

- encounter and phase identity;
- active mechanic and affected actor/target GUIDs;
- relevant aura, timer, position, or targetability state;
- submitted native action, rejection reason, completion, and landed outcome.

The encounter script publishes facts. The priority queue remains responsible for candidate ranking and action choice.

### 4. Validate in increasing cost order

Run the narrowest applicable static and unit checks, then native replay. If native code changed, request the required build only through:

```bash
tools.raid_program.queued_build
```

Do not run direct heavyweight builds. After deterministic checks pass, hand one
exact route/mode shard to `raid-shard-architecture`; use the generated
completion-watchdog validation plan, not a 90-second command smoke test or a
fixed 300-second observation. The route ends on normal completion or typed
stall/repeated-decision/death-loop/infrastructure evidence; any generous
emergency wall-clock expiry is noncompletion. `raid-boss-babysitter` observes
an already-started run and `raid-evidence-lifecycle` owns capture and
publication.

## Completion gate

The unit is complete only when:

- the reviewed contract maps to production code with no unexplained material gaps;
- reset, wipe, completion, and mode-specific behavior have deterministic coverage;
- replay/native checks exercise production helpers;
- one exact live shard emits attributable diagnostics and a normal server outcome;
- the evidence handoff separates implemented, deterministically tested, live-observed, and still-unproven claims.

Return the shared handoff shape from `raid-performance-loop/references/handoff-contract.md`. Never report a responsive diagnostic command as boss completion.
