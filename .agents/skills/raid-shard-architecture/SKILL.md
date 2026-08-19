---
name: raid-shard-architecture
description: Design and coordinate isolated TrinityCore raid-boss experiments and their canonical full-raid composition. Use for per-boss route manifests, runtime profiles, bot pools, frozen rosters, predecessor instance saves, server preparation, parallel shard orchestration, or promotion from boss shards to sequential full-raid validation. Do not use for a read-only live babysitter handoff.
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
- A capture that must leave the worldserver alive must pass
  `--preserve-worldserver --transport session --session-runtime-dir <stable-dir>`.
  This is a fail-closed contract, not a prompt convention: process transport
  appends a server shutdown command and is non-accepting for such a canary.
  Cleanup stops and reads back only the named cohort and calibration fixture;
  it must report `worldserver_preserved=true` without changing the server epoch.

## Compose routes

- Make each boss route contain only its required entrance/preparation, prerequisite trash, and target boss.
- Keep unrelated bosses and trash out of a diagnostic shard. Magmaw must not traverse Omnotron.
- Build the canonical full-raid route from the reviewed boss-node sets, preserving one authoritative ordering and node identities.
- Keep executable mechanic contracts on boss nodes. Unresolved or undeclared targets must hold offense fail-closed.
- Scope wipe/recovery latches to the exact node, route generation, attempt, and
  recovery policy that observed them. Trash recovery state must not cross into
  a later boss ready-check contract.
- Require the same typed recovery policy in the route data, runtime handler,
  telemetry label, and acceptance verifier. Never synthesize a policy name in
  code when the active node did not declare it.
- For charge/split packs, declare separate exact pre-pull member anchors and
  post-pull tank combat anchors. Prove every pre-pull path and the full frozen
  roster before the first taunt; then let native threat and charge scripts run.
- Validate combat anchors against authoritative native spawn coordinates and
  melee stopping distance. Tank separation is not source separation: require
  the tanks' outward displacement, minus arrival tolerance and native melee
  reach, to guarantee the configured source separation plus navigation margin.
  Revalidate every non-tank anchor against the resulting source positions.
- Treat algebraic anchors and navmesh endpoints as different identities. Seal
  the declared contract coordinate plus the exact native path terminal; prove
  the full arrival disk, and require a fresh strict path when either identity,
  instance, source pair, route generation, attempt, or wipe changes.
- Separate tank ownership acquisition from ordinary engagement. After both
  exact tank paths and arrivals are proven, allow only a real assigned taunt
  (with its native range/LOS checks) even if a body-pulled source briefly
  crossed lanes. Keep threat seeds, healing that can move, and all damage held
  until observed source separation, frozen lanes, and bound geometry recover.
- For cross-lane threat seeds, bind at least one trained ranged DPS slot per
  source. Validate `anchor distance + member arrival tolerance <= resolved
  hostile action range`, source danger clearance, lane side, and spacing;
  runtime must still recheck the actual hostile action, LOS, power, cooldown,
  and exact target before submission.
- Treat a successful seed cast only as creation of a native threat reference,
  never as proof of the eventual selector result. After both ordinary seed
  submissions, keep every non-tank hostile action suppressed while the
  assigned tanks use real profile actions/taunts to regain exact victims and a
  declared threat-headroom multiplier. Immediately before the native clock
  edge, inspect the real live threat lists with the core selector predicate and
  require each configured seed to be the unique farthest eligible player. Do
  not rewrite threat or force the native target.
- Treat pre-native-selector threat readiness as a temporal invariant, not a
  one-tick threshold. Seed DoTs and required healing keep generating threat
  after readiness first becomes true, so assigned tanks must continue ordinary
  single-target profile actions until the first native selector edge is
  actually observed. Re-evaluate victim, headroom, and unique-farthest identity
  every decision tick; a transient ready snapshot must never stop tank threat
  production while the native timer is still running.
- Keep the same guard after the first Rush. Before admitting a new ordinary DPS
  action, prove that this prospective threat-list member is still nearer than
  the configured opposite-lane seed by the sealed arrival margin. A static
  formation check that ignores threat-driven source movement is not equivalent
  to native selector parity.
- Validate native farthest-target geometry as a steady-state invariant, not
  only at the initial pull. Reconstruct the source's post-Rush return point at
  the sealed tank/melee-stop anchor; the intended opposite-lane DPS must remain
  farther than every same-lane member and every healer after both arrival
  tolerances. Run the identical predicate in manifest generation and live
  admission, while leaving native target selection untouched.
- Treat periodic native displacement as a deadline contract. Prove the real
  tank approach/taunt, source chase, member return paths, decision cadence, and
  exact-roster acknowledgement fit below the observed native interval. If the
  next native edge arrives first, retain it and terminalize the missed recovery
  instead of accumulating an unbounded queue or telemetry flood.
- During a landed-displacement recovery, move any geometry-unsafe member before
  routine healing or support; allow support first only while staging or once
  that member is back in the sealed formation. A single bait/recovery anchor is
  valid only when combined arrival envelopes prove both hostile-action range
  and post-return source clearance and its native return path is exact.
- Do not certify post-charge formation from the source home or initial radial
  chase alone. Once the source returns to its tank, it may stop anywhere in the
  native melee-reach disk. Seal a separate pull-away tank anchor when needed,
  preflight both tank paths before either moves, and prove the worst-case disks:
  source-pair separation subtracts both `(melee reach + tank tolerance)` radii;
  every member clearance adds melee reach, member tolerance, and tank tolerance.
  Keep the native victim unchanged so the source follows by ordinary threat.
- Give the active mechanic state ownership of generic safety movement while a
  landed displacement remains unresolved. The generic controller may compute
  and submit the outward escape, but it must not return outside the mechanic's
  durable return obligation. Dynamic source/spacing rejection must retry on
  the first safe edge and must not arm the expensive native-path heartbeat;
  rate-limit only a real floor/path rejection. Emit the rejected predicate,
  path flags, and native-end delta so a live failure is exactly diagnosable.
- A prerequisite patrol is pullable only in a path-proven phase whose entire
  chase stays outside every future-encounter guard. A native combat link to a
  future encounter permanently contaminates that route generation; terminalize
  it instead of accepting a later evade and quiet `trash_cluster_cleared`.
- Make the pull anchor own the raid as well as the hostile chase. Stage the
  exact leased roster at that anchor, admit only the declared ranged puller at
  the declared safe patrol phase, and inspect every native chase-path point
  against every future source identity before the ordinary pull. While the
  hostile is still approaching, suppress pursuit and keep all members at the
  anchor; a safe creature path is not sufficient if profile range movement can
  chase the patrol back into the protected pack. Hazard exits may temporarily
  preempt the anchor, but the route must reacquire it before ordinary offense.
- Bind hazard activity to native spell timing, not the visual marker's summon
  lifetime. A non-attackable marker may outlive its cast/effect; prove the
  radius, cast time, effect duration, and summon lifetime from native data,
  move during that bounded danger window, then permit stationary friendly
  support from a proven safe side. Rotate a bounded rejected exit bearing;
  never repeat one GUID-derived path forever or shrink the native radius.
- If native body combat begins during geometry staging, keep hostile offense,
  taunts, and threat seeds gated but allow ordinary friendly class support.
  A pre-seed death must terminalize/restart the dirty attempt; do not label a
  partial body-pull as a reachable native full wipe.
- Order prerequisite actions against the native encounter clock explicitly.
  After exact staging and tank ownership, submit required ordinary threat or
  assignment actions before a post-pull/reseparation gate can return. Keep all
  regular offense and kill synchronization behind that geometry gate. Never
  force the native target to compensate for a prerequisite that ran too late.

## Arbitrate actions instead of accumulating gates

- Keep route sequencing in the manifest, but express each node's live behavior
  as prioritized candidate actions: emergency safety, mechanic movement,
  stationary support, ownership, ordinary role action, then route movement.
- A retryable candidate rejection must expose a typed reason and let the next
  compatible candidate run in the same decision tick. Reserve terminal latches
  for identity loss, forbidden assistance, contaminated scope, or a missed
  native deadline—not a single rejected path or temporarily unavailable spell.
- Give movement one explicit priority/owner token. A higher-priority mechanic
  may preempt a lower one; equal/lower priorities preserve the active path.
  Clear ownership on observed completion or scope change, not on every tick.
- Keep evidence assertions observational. Do not make a certification field a
  live prerequisite unless the mechanic itself needs that fact for safety.
- Prefer small trigger/action/multiplier components with prerequisites and
  alternatives over adding another early return to a monolithic route handler.
  Borrow this arbitration shape from Playerbots, but not its WotLK/AzerothCore
  APIs, incomplete-path acceptance, forced movement, or teleport recovery.

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
6. Keep route observation completion-driven. Terminate on success, explicit
   user interruption, stale telemetry/infrastructure loss, a monotonic
   semantic/no-progress stall, repeated-decision watchdog, or excessive death
   loops—not an arbitrary fight deadline.

## Keep timing semantics separate

- Reserve the exact 300-second scoring window for isolated training-dummy DPS
  calibration. It measures stable throughput, action mix, cadence, and pet
  contribution; it does not model raid or dungeon completion.
- Never pass `--observe-sec 300` as a raid/dungeon success condition. Use
  `--duration-policy completion-watchdog` and poll at the configured heartbeat.
- For raids and dungeons, require typed terminal evidence: normal clear,
  monotonic semantic/no-progress stall, repeated decisions, excessive death
  loops, stale telemetry/infrastructure loss, contamination, or explicit
  interruption.
- A generous emergency wall-clock cap may protect the host. Expiry is an
  infrastructure/noncompletion result, never a successful fight result.

## Keep roles separate

- The coordinator builds, provisions, starts, stops, restarts, and mutates state.
- A babysitter receives a verified live handoff and only observes and reports unless explicitly authorized otherwise.
- Give babysitters only the `raid-boss-babysitter` skill; do not load this coordinator skill into every watcher.

## Parallelize safely

- Use one isolated cohort, pool, frozen roster, instance/save, capture namespace, and babysitter per boss.
- Audit the runtime scheduler before promising same-process fan-out. The
  current BotWorld design is serialized when `MaxActiveCohorts == 1` and
  `Update()` selects only `_runningCohortId`; raising the constant alone is
  unsafe and still does not schedule every cohort. Implement iteration over a
  frozen active-cohort set, restore cohort scope after each update, and bind
  every status/trace row to that cohort before enabling parallel shards.
- Do not let native spell, heal, damage, death, or creature callbacks consult
  a process-wide selected cohort. Route each callback from actor GUID plus
  map/instance into an explicit or thread-local cohort scope; test with map
  worker threads enabled so cross-shard attribution cannot race.
- Give one coordinator exclusive ownership of worldserver stdin. It must poll
  cohort-qualified status/diagnose/trace commands and demultiplex immutable
  per-cohort streams; six babysitters consume those streams read-only instead
  of racing unqualified commands on the same console.
- Freeze process-global adaptive state during diagnostic fanout: disable bot
  learning, global-memory fallback, and semantic outcome writes unless they
  are cohort/run keyed. Block rotation/profile reload or rollback while any
  cohort is active; a pinned hash is audit evidence, not isolation.
- Share a worldserver only after confirming instance, group, lease, roster, and telemetry isolation under concurrency.
- Budget CPU, log rate, and disk before launching all shards. A single pathological shard blocks fan-out.
- Run six boss shards in parallel only after the single Magmaw rehearsal is clean.
- Finish with three to four sequential canonical full-raid runs; shard success cannot replace end-to-end validation.

## Separate profile selection from execution

Do not diagnose low damage from profile presence alone. Record these distinct
edges for every bot and target scope:

`profile_loaded -> action_selected -> movement_or_authority_block -> action_submitted -> action_landed`

- A correct DB profile can select a valid spell while route movement, hazard,
  formation, future-encounter, recovery, or target authority returns before
  execution. Treat that as an architecture/path failure, not lost tuning.
- Prove every selected profile has an executable action envelope at its node.
  A boss-only shard may clone a reviewed, mechanic-compatible trained profile
  into an independently provisioned slot while preserving the frozen 2/3/5
  roster; keep that override explicit and leave the canonical full-raid roster
  unchanged until its own melee/ranged node geometry is proven.
- Keep counters for selected, blocked-before-execute, submitted, landed, and
  rejection reason. Emit full candidate masks only on profile-generation or
  material target-state changes.
- Cache expensive native path checks by bot, route generation, attempt/wipe,
  and candidate anchor. Invalidate on route, charge/geometry, target, or
  instance identity changes; never let a stale cache authorize movement.
- Require one single-shard rehearsal to reach stable profile execution and a
  bounded CPU/log rate before six-way fan-out.

## Validate with production-parity replay

- Extract fragile raid state transitions into small C++ functions called by
  both the worldserver and a deterministic replay executable. Do not maintain
  a separate Python model of production decisions.
- Replay captured native inputs such as event order, scope identity, target
  ownership, spell availability, geometry predicates, and wipe generations.
  Cover reordered/asynchronous bot ticks and transient failures exhaustively.
- Keep the parity boundary explicit: replay certifies the shared decision
  transition; one live shard must still certify native pathfinding, spell
  legality, threat selection, SmartAI timing, and observable script behavior.
- For a live native-path counterexample, add an asset-hash-bound preflight that
  loads the exact map `.mmap`/tiles and uses PathGenerator-parity filter flags,
  nearest-poly extents, corridor cap, and smoothing to prove the recorded
  start→sealed-anchor terminal. Missing or changed assets fail live prep; a
  source-shape assertion or algebraic straight line is not navigation proof.
- Keep offline Detour and live height authority distinct. Detour may preserve
  the requested terminal Z even when production `Map::GetHeight` and
  `PathGenerator::GetActualEndPosition()` choose another floor. Before native
  combat opens, run the exact live PathGenerator from each sealed start,
  require its actual XY/Z terminal within the configured bounds, and latch a
  terminal preflight failure instead of discovering a bad endpoint after the
  mechanic timer starts.
- Run the replay gate before every native rebuild/live attempt. A failed replay
  blocks the live run; a passing replay reduces but never replaces the final
  native confirmation.
