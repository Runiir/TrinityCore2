---
name: raid-shard-architecture
description: Design, validate, and operate isolated TrinityCore raid-boss experiments and their canonical full-raid composition. Use for per-boss route manifests, runtime profiles, bot pools, frozen rosters, predecessor instance saves, parallel boss babysitters, prestarted worldserver handoff, or promotion from boss shards to sequential full-raid validation.
---

# Raid Shard Architecture

Build every boss shard as an isolated, executable slice of the canonical raid. Treat identity mismatches as failures, not recoverable defaults.

## Bind the shard identity

Require one exact tuple across config, generated route, runtime status, capture, and evidence:

`scenario_id + runtime_profile_id + pool_tag + route_manifest + frozen roster + assignment generation`

- Give each boss a distinct scenario, runtime profile, pool tag, ten-character roster, evidence namespace, and route.
- Require the selected profile to own the selected route manifest. Reject empty, foreign, or substituted manifests.
- Never inherit Stonecore, canonical BWD, or another boss profile as a fallback.
- Reject transports that cannot prove config ownership. In particular, do not use SOAP for scenario-scoped live execution unless the running server's exact config identity is independently bound.

## Compose routes

- Make each boss route contain only its required entrance/preparation, prerequisite trash, and target boss.
- Keep unrelated bosses and trash out of a diagnostic shard. Magmaw must not traverse Omnotron.
- Build the canonical full-raid route from the reviewed boss-node sets, preserving one authoritative ordering and node identities.
- Keep executable mechanic contracts on boss nodes. Unresolved or undeclared targets must hold offense fail-closed.
- Scope wipe/recovery latches to the exact node, route generation, attempt, and
  recovery policy that observed them. Trash recovery state must not cross into
  a later boss ready-check contract.

## Model prerequisites as a DAG

- Encode actual encounter dependencies, not a convenient linear chain.
- Precomplete only predecessors required by the selected boss.
- Mark precompleted state as `diagnostic_only_assistance`; it cannot certify a natural full-raid clear.
- For Nefarian, require all five predecessors and prepare on the upper ledge before the native descent/start action.
- Bind the native instance-save rows and live runtime identity; never trust caller-authored boss-state booleans.

## Start and hand off a live shard

1. Review and build one exact clean commit.
2. Reprovision the exact shard roster and verify DB readback: ten expected characters, offline, unleased, and free of group/instance/corpse/ghost residue.
3. Start one verified worldserver with the generated shard config.
4. Confirm console/process readiness and active runtime identity.
5. Only then attach the boss babysitter. The babysitter monitors; it does not silently repair or manufacture state.
6. Keep observation uncapped. Terminate on success, explicit user interruption, stale telemetry/infrastructure loss, or a monotonic semantic stall—not an arbitrary fight deadline.

## Parallelize safely

- Use one isolated cohort, pool, frozen roster, instance/save, capture namespace, and babysitter per boss.
- Share a worldserver only after confirming instance, group, lease, roster, and telemetry isolation under concurrency.
- Budget CPU, log rate, and disk before launching all shards. A single pathological shard blocks fan-out.
- Run six boss shards in parallel only after the single Magmaw rehearsal is clean.
- Finish with three to four sequential canonical full-raid runs; shard success cannot replace end-to-end validation.

## Review decisions, not only outcomes

Compare bot decisions with native boss/trash scripts and observed casts, auras, targets, summons, geometry, and phase state. Check damage-profile activation, hazard exits, tank ownership, formation, recovery/readycheck ordering, stuck/unstuck frequency, CPU, and telemetry volume. Do not infer tactics or 4.4.2 fidelity from engagement, wipe, or synthetic evidence alone.

## Separate profile selection from execution

Do not diagnose low damage from profile presence alone. Record these distinct
edges for every bot and target scope:

`profile_loaded -> action_selected -> movement_or_authority_block -> action_submitted -> action_landed`

- A correct DB profile can select a valid spell while route movement, hazard,
  formation, future-encounter, recovery, or target authority returns before
  execution. Treat that as an architecture/path failure, not lost tuning.
- Keep counters for selected, blocked-before-execute, submitted, landed, and
  rejection reason. Emit full candidate masks only on profile-generation or
  material target-state changes.
- Cache expensive native path checks by bot, route generation, attempt/wipe,
  and candidate anchor. Invalidate on route, charge/geometry, target, or
  instance identity changes; never let a stale cache authorize movement.
- Require one single-shard rehearsal to reach stable profile execution and a
  bounded CPU/log rate before six-way fan-out.
