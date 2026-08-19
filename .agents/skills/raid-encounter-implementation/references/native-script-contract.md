# Native encounter contract

Use this checklist to keep a boss implementation small and auditable.

## Identity and lifecycle

- Instance, boss, mode, map, creature, gameobject, spell, and achievement identifiers are explicit.
- Loader and database bindings resolve to the intended native script.
- Reset, engage, wipe/evade, death, and encounter-credit paths use normal server lifecycle APIs.
- Instance state and predecessor dependencies survive only where the reviewed route requires them.

## State machine

- Every phase has an entry condition, exit condition, scheduled events, and cleanup rule.
- Timers state whether they are fixed, ranged, health-based, or actor-state based.
- Events cannot silently duplicate across reset, phase change, or summon recreation.
- Summons have an owner, lifetime, despawn rule, threat/targeting rule, and wipe cleanup.

## Mechanic fidelity

- Every material numeric value is linked to a reviewed claim or explicitly marked as a compatibility value.
- Difficulty lookup cannot accidentally use 10-player or normal-mode values in 25H.
- Actor, target eligibility, range, facing, line of sight, immunity, aura stacking, and dispel semantics are explicit.
- Server behavior remains client-valid; the script does not perform actions for bots or bypass mechanics.

## Deterministic observability

Emit stable identifiers at the boundaries needed to diagnose:

1. encounter/phase observation;
2. mechanic activation and target set;
3. bot candidate eligibility and rejection reason;
4. native action submission;
5. completion/interrupt/cancel;
6. aura, damage, healing, threat, movement, or summon outcome;
7. phase transition and encounter completion.

The identifier tuple must be sufficient to join a decision to the exact run, roster slot, actor GUID, encounter, mode, phase, and source revision.

## Proof tiers

1. Static binding and contract checks.
2. Unit or native replay of production helpers.
3. Built binary receipt from the queued-build coordinator.
4. Provisioning readback for the exact shard.
5. Live trace showing intended mechanic execution.
6. Normal server-side completion and credit.

Higher tiers do not erase missing lower-tier identity. A test double or command-response smoke check does not satisfy live mechanic proof.
