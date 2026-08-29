# Canary114 current-route combat-authority architecture stop

Canary114 ran exact source `ade3eb701d4418e41d7ec0e50653821cd5aafbaa`
and stopped after 20 repeated `validation_route_regroup /
hold_anchor_no_focus` decisions on the Chainwielder node. The exact current
Chainwielder, entry 42649 GUID 27, remained alive, attackable, in combat, and
tank-owned. Affliction GUID 30008 had already selected and attacked GUID 27.
The generic non-tank regroup branch then cleared that valid target. Later
fallback considered Magmaw GUID 39, correctly rejected it as
`future_encounter_target_forbidden`, and never restored GUID 27. There were no
deaths; native recovery was not exercised.

This is the tenth retained manifestation of one parent invariant, not a new
watchdog family. Earlier manifestations displaced live current-node authority
through undeclared prerequisite selection, future targets, alive-pack
retirement, stale safe-memory anchors, partial-wipe retreat, or movement/action
contamination. The ten retained identities are `e75f5ba2`, `ef04a6f22a`,
`fae9049d`, `c35ead7a`, `476ec4c0`, `9a3afe4def`, Canary40, `02e3ba1ba8`,
Canary102, and Canary114.

The architecture decision is one precedence table below all target producers:

1. preserve a valid exact current-node target;
2. otherwise recover an alive valid persisted current-pack target;
3. only when neither exists may generic regroup own the tick.

Safety movement can still preempt combat through its typed candidate. The
table does not permit attacking prior/future encounters, bypass target
eligibility, force combat, or manufacture a target. The original Canary114
state is retained as a compiled transition replay and permanent regression-bank
fixture. No next canary is admissible until the complete bank passes after
Canary114 at the exact rebuilt source identity.
