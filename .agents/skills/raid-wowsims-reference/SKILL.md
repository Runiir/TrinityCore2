---
name: raid-wowsims-reference
description: Build, verify, reconstruct, and promote exact WoWSims Cataclysm reference values for the frozen 25-player roster. Use for simulator checkout or binary binding, RaidSimRequest construction, per-spec DPS denominators, APL/gear/talent/glyph/consume identity, exact result generation, WoWSims revision changes, stale promotion repair, or questions about the proper DPS value for a roster spec. Do not use for Trinity class-policy fixes, boss scripts, or live raid qualification.
---

# Raid WoWSims Reference

Own the complete reference lifecycle for the 16 unique DPS specs. Duplicate
roster characters reuse a spec reference; they need separate provisioning
proof, not duplicate simulations.

## Admit exact inputs

Start with:

```bash
pixi run python -m tools.raid_program.raid_workloop status
pixi run python -m tools.raid_program.raid_workloop spec <spec>
pixi run python -m tools.bot_ml.build_wowsims_reference_requests --check
pixi run python -m tools.bot_ml.run_wowsims_exact_references validate-catalog
```

If the first status reports `workspace_state=remote_requires_hydration`, do
not run `validate-catalog` yet and do not regenerate the cohort. Materialize
and verify the already promoted cohort with:

```bash
pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate
pixi run python -m tools.raid_program.raid_workloop status
```

Continue only when the receipt reports `state=locally_verified`, 181 files,
16 accepted references, and
`promotion_states.locally_reconstructed_current=16`. When the reference work
unit is finished, run:

```bash
pixi run python -m tools.raid_program.wowsims_reference_workspace evict
```

That command verifies the catalog and remote before removing only the exact
workspace. It preserves the shared DVC cache and never runs broad garbage
collection.

Require one explicit WoWSims source checkout at the revision in the request
catalog. Do not guess a replacement when a handed path such as
`tools/wowsims-amd554` is absent. A downloaded web-server binary is exploratory
until its bytes and source/build identity are bound.

Bind request bytes, revision, build receipt, binary hash, APL, gear, talents,
glyphs, race, spec options, pet, consumes, raid buffs/debuffs, target, duration,
execute schedule, distance, iterations, and seed. Any changed input creates a
new reference cohort. Resolve `wowsims_source_relative_apl` only inside that
pinned WoWSims checkout. Keep the request-catalog canonical JSON SHA-256,
request-catalog file SHA-256, target-catalog SHA-256, and receipt SHA-256 under
their exact labels; never compare or rename them as a generic catalog hash.

## Keep three reference classes separate

Name the reference class before reporting or comparing DPS:

- `self_provided_baseline` is the one-sided minimum throughput floor. Disable
  every external raid buff, individual external buff, and pre-applied target
  debuff. Keep the frozen player's exact gear, talents, glyphs, race,
  professions, pet, class effects, APL, flask, food, pre-pot, combat potion,
  racial, and profession actions. Self-applied class buffs or debuffs must come
  from normal simulator actions, not from an externally enabled checkbox. Use
  an exact 300-second duration with zero variation. Passing means Trinity DPS
  is greater than or equal to this value; there is no upper rejection bound.
  Bind per-spec consumable item IDs. Configure one pre-pot and one combat
  potion, not a generic potion shared across every spec.
- `controlled_live_parity` binds every simulator input to one Trinity canary.
  Use it for cast mix, cadence, owner and pet damage per event, stats, and a
  like-for-like DPS ratio. If the bot does not execute food, a pre-pot, or a
  combat potion, disable those in this reference or report consumables as the
  first mismatch. The qualifying bot path must provision the real items and use
  them through native item actions. Never credit a static aura as item use.
  Record those downstream requirements, but do not implement or claim the
  runtime receipts: inventory provisioning belongs to `raid-shard-architecture`
  and action policy belongs to `raid-role-implementation`.
- `upstream_full_throughput` preserves the original WoWSims preset and its
  duration as a capability and UI cross-check. It is not a tuning denominator
  unless Trinity reproduces every input.

Different values between these classes are expected and never block static or
trace-only rotation diagnosis. A missing or mismatched class blocks only the
claim that depends on it. An exploratory UI number is not qualifying until its
export proves player identity, consumes, buffs, debuffs, duration, variation,
distance, and encounter settings.

Use the current `raid_workloop` catalog projection as the status authority.
Older run reports may retain the catalog classification that existed when they
were captured; they cannot downgrade a value the current work unit explicitly
labels `current_accepted`.

Treat equipment identity as necessary but insufficient. Bind the exact
`ComputeStats` artifact and retain its normalized `effective_stat_reference`
from `finalStats`. This is the scoring-start owner denominator for primary
stat, relevant attack/spell power, hit/crit/haste/mastery ratings, effective
hit/crit, and total attack/cast speed. For a pet spec, also generate the
one-iteration debug result used by rotation review; its timestamp-zero `Pet
stats` and `Pet inherited stats` records are the pet denominator. Missing owner
or required-pet stat evidence makes the reference unusable for tuning even when
the item manifest matches.

## Generate one atomic cohort

Use `tools.bot_ml.run_wowsims_exact_references` for build, materialization,
generation, DVC reconstruction, promotion-index construction, and promotion.
Inspect each subcommand's `--help`; never handcraft receipt JSON.

Generate all 16 DPS specs as one cohort per reference class because promotion
is all-or-nothing. Do not mix reference classes in one promotion. One owner
handles the cohort. Do not launch one agent per spec.
Use the exact `required_reference_work_unit` emitted by `raid_workloop`; do not
narrow it to the spec that exposed the blocker.

Follow [references/reference-gate.md](references/reference-gate.md). A native
result before reconstruction is a candidate, not a proper reference value.

## Publish usable values

Report for every spec:

- current request catalog SHA-256 and WoWSims revision;
- native result and generation receipt;
- iterations, exact duration, DPS, and simulator errors;
- normalized scoring-start owner stats and, for pet specs, the bound debug-log
  pet stat reference;
- DVC pointer/reconstruction receipt and promotion status;
- classification: current promoted, current unpromoted, stale, or exploratory.

Only `locally_reconstructed_current` or equivalently rehydrated and verified
current evidence may supply the acceptance denominator. Keep single-target,
AoE, execute, movement, and encounter-specific profiles separate.

WoWSims TPS/HPS can inform tank or healer review, but raw TPS/HPS never replaces
the tank-threat or controlled-damage healer harness. Hand role behavior to
`raid-role-implementation` after the reference gate passes.
