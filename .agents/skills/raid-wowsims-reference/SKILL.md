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

Generate all 16 DPS specs as one cohort because promotion is all-or-nothing.
One owner handles the cohort. Do not launch one agent per spec.
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
