# Magmaw Canary122 planner-to-launch divergence handoff

Canary122 ran clean source `2bfbd48bdafae41950fbfcaaf26df6f70a3784a3`. Entrance regroup, Chainwielder, and Drudges completed with all ten bots alive. All ten used their ordinary flask, food, and pre-pot from inventory. Magmaw remained active until the completion watchdog stopped the run after 27 repeated decisions. One tank died and nine members remained alive.

The earlier seq741 diagnosis was wrong. Mgwhealc, bot `30005`, rejected `parasite_contact_evade` at seq741 and seq743 without submitting movement. Those failures were contained. Do not widen partial-path admission for path type `132` from this evidence.

The first observed state-infecting edge is seq745 at `1788016935018`. The planner accepted a complete path for `ranged_formation_restore` and the executor submitted it. The planned endpoint was `(-308.91, -36.4524, 211.581)`. The same proof recorded `floor_observation_conflict=true` and `sample_floor_gap` at `(-311.814, -32.2758, 209.392)`, where the resolved floor was `211.39`. `SampleFloorGap` is deliberately nonblocking for complete-path proof.

Production then loses the proved route. `PathPlan` retains endpoint metadata but not the planner's ordered path controls. The executor calls `MovePoint(..., generatePath=true)`, which creates a second `PathGenerator`; on failure, that layer can use a direct two-point fallback. The bot-specific admission and floor invariant are not applied to this launched path. Canary122 did not serialize the launched spline, second path type, or fallback decision, so the exact physical mechanism remains unproven.

The resulting live-position contamination is proven. At seq749, a new parasite movement was built from the bot's live Z of `202.591`. The later Massive Crash movement was built from its live Z of `6.70457`. Both producers copy the actor snapshot Z, and the blackboard obtains that value from `GetPositionZ()`. State only supports the statement that the actor's live Z dropped after seq745. It does not identify the exact spline, collision, or falling transition.

The required fixture must cross the production planner-to-launch boundary. It must capture actor XYZ before planning and after launch; planner path type, endpoint, floor observation, and ordered-control fingerprint; launched spline controls and fingerprint; the second path type; and whether direct fallback was used. It must replay seq745 and require the launched path to satisfy the same path and floor invariant as the admitted proof. A helper-only executable, source-string assertion, widened tolerance, or special case for path type `132` is not sufficient.

The bounded implementation hypothesis is to bind execution to the planner-proved path controls, or fail closed after immediate launched-spline revalidation when the launched path diverges from the proof. Preserve ordinary set-and-forget movement. Do not change global Z thresholds, pincer behavior, Exposed Head targeting, class rotations, or encounter strategy in this work unit.

Queue ordering was not the first failure. Cross-bot candidate-key collision is refuted because every bot owns a separate decision kernel and lifecycle map. Candidate-key correctness under parasite GUID replacement is underdetermined and requires semantic-transition telemetry before modification. Canary122 did not exercise Exposed Head entry `42347`; Canary121 remains the latest evidence for successful pincer interaction.

Magmaw throughput was `73,300.517` active party DPS and `19,076.322` active party HPS. Affliction contributed `31,644.215` active DPS and its Felhunter contributed `1,023,930` damage, or `25.8122%`. The encounter recorded 39 direct Parasitic Infection damage events across five players. These are diagnostic values because the route did not clear.

Evidence identities:

- recurrence admission: `444aa8dfc41fafe3f0c40b7d21eabc407551a30779335eb72cab00084d10b09c`
- report: `724383fa20ff93bd70ab167a65cfadf8c5922b2d740a98420b6cee6dcdc415ac`
- normalized JSONL: `0f04777b7365cbe8ddf692ddda83815a3595c94244542914689732523e337ab0`
- worldserver log: `54ec23a36121324905bc34eef32d5cd7994fe962541a0390ffda383fbcc02870`
- binary: `e9dd1be550fab2e0b7d8a195e795965b28257a937906466f9504eb16a5dd9584`

No unchanged canary is authorized. First add the compiled planner-to-launch replay, pass it against the production seam, increment the invalidated fixture revision, and pass the complete retained regression bank at one clean committed identity.

## Fixture-feasibility result

A Sol-high implementation pass proved that the existing unit-test harness cannot construct the required boundary. It syntax-compiled a proposed planner-control handoff, but no test could initialize a populated map-669 `Map`, MMAP, live `Player`, `BotWorldPopulationMgr`, `MotionMaster`, and launched spline without world/DBC/DB singleton startup. The proposal and its surrogate test were rejected and removed. Syntax-only compilation is not fixture evidence.

The next work unit belongs to shard architecture, not gameplay implementation. Add one isolated worldserver-backed replay profile that provisions the exact map-669 bot identity and invokes the production planner, executor, `MotionMaster`, point generator, and launched spline. It must stop on a typed replay receipt, infrastructure loss, or bounded no-progress. It is an evidence capture, not a raid canary, and it cannot certify boss completion.

The replay receipt must bind the exact binary/config/data/MMAP identities and record actor XYZ before planning and after launch, planner path type and ordered-control fingerprint, executor destination, active generator type, launched spline controls and fingerprint, direct-fallback or no-replan state, and multi-tick displacement/floor outcome. Missing assets or any unobserved boundary fail closed. Only after this receipt exposes the actual launch may a runtime implementation hypothesis be admitted.

## Observation seam result

Commit `75c12a3d1f28215021aa83c3b6af099b6609a193` adds an observation-only correlation receipt from bot planner admission through native point-generator and spline launch. The neutral Movement observer has no bot dependency and is null for ordinary callers. It records stable identity and scope, planner and launched control counts and fingerprints, second-path type, direct two-point fallback, actor positions, and submission and generator outcomes. History is bounded to 128 receipts and trace rows per bot and four launch attempts per receipt; no ordered controls are retained or serialized.

The six touched production translation units passed syntax compilation. The focused telemetry and existing movement-diagnostic tests pass. This validates the receipt schema and callback plumbing only. It does not initialize map 669, MMAP, a live player, or multiple world ticks and therefore does not prove the Canary122 mechanism.

The active work unit is now the isolated worldserver-backed map-669 replay. The replay must emit the same correlation key from candidate through native launch and later consumed movement state, bind binary, config, data, and MMAP identities, and stop on a typed receipt, infrastructure loss, or bounded no-progress. Gameplay movement remains frozen until that evidence is captured.

## First worldserver-backed replay result

The rebuilt worldserver completed successfully with eight jobs. Binary SHA-256 is `dedef34290297a86e1776e6668f9e9205fa09ab503457371c651f9ae2d7ff0a4`. The observation seam loaded with the real map 669, MMAP, frozen ten-bot roster, planner, executor, MotionMaster, and native movement generators.

The evidence-only one-node overlay did not reach the target movement edge. The initial Magmaw platform anchor body-pulled the boss before formation and prepull completed, leaving eight bots dead by 40 seconds. A single trace-backed correction moved the start to the proven rear-room staging area near `(-305.6, -65, 213)`, but the boss node still advanced tanks into body-pull range, leaving seven dead by 40 seconds and all ten dead by 85 seconds. No qualifying `ranged_formation_restore` launch receipt was emitted.

Both owned servers were stopped, the disproven temporary controller and tests were removed, and no DVC evidence was published. This refutes the assumption that a one-node boss manifest plus a safe rear start can reproduce seq745. The exact missing production boundary is a post-trash, pre-pull checkpoint that keeps the boss node sealed until the roster has completed formation, consumables, and prepull readiness. The next shard-architecture unit must restore such a checkpoint or replay the canonical route into one, then release the existing boss node and receipt observer without changing boss or bot gameplay.

## Checkpoint interface audit

No safe production hold and release control exists. `.botauto` exposes start and stop, not a route-node checkpoint. The internal `BotActionsEnabled` gate is admission-wide. `ApplyRaidPrepullBossPullGate()` suppresses hostile actions only after a boss target is acquired; it does not seal bossward route or adaptive movement, pet engagement, taunt, or native body aggro. Earlier canonical runs reaching prepull do not make this boundary deterministic.

The missing interface is a validation-only route-node state machine `staging -> ready -> released`, keyed by cohort, attempt, route generation, and node. During staging it must allow formation movement, friendly healing, and ordinary bag consumables while suppressing bossward movement and hostile player or pet actions. Readback must prove all ten members alive, out of combat, formed, flasked, fed, and prepotted before a single release. The default production path must remain unchanged when the diagnostic checkpoint is disabled.

This is now a narrow `raid-bot-runtime-implementation` work unit. Once its focused fixture proves the state and suppression boundary, ownership returns to `raid-shard-architecture` for one canonical checkpoint and correlated launch receipt.

## Validation checkpoint implementation result

Commit `da3b637159` adds the default-off validation prepull checkpoint. It is keyed by route scope, admits only typed formation movement, friendly healing, and ordinary bag consumables during staging, and suppresses unknown, offensive, pet, taunt, and bossward work until all ten frozen-roster readback rows are alive, out of combat, formed, flasked, fed, and prepotted. Release is single-shot and the ordinary runtime is unchanged while the config flag is disabled.

The focused checkpoint and adjacent arbitration tests pass, and the committed worldserver rebuilt successfully with eight jobs. Binary SHA-256 is `109757f535e0a0561bfd19dcb8bac28c93d0f8bd2096a20caff432fa2e31e8aa`.

This closes only the missing setup interface. It does not validate map-669 formation convergence, checkpoint release, the seq745 launch, or the physical movement outcome. Ownership returns to `raid-shard-architecture` for one canonical-route worldserver replay with `BotWorld.ValidationRoute.PrepullCheckpointEnable=1`. The replay must capture the checkpoint readback and the same correlation key through candidate, native launch, and multi-tick consumed movement state. Missing release, premature combat, missing receipt, infrastructure loss, or monotonic no-progress fail closed.
