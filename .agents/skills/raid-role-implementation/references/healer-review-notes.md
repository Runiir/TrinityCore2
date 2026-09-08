# Healer review notes

Use these checks for class/role diagnosis. Encounter-specific tactics remain in the encounter contract.

## Evidence identity

- Bind commit, profile generation/hash/source, actor and target GUIDs, route node/generation, attempt, instance, difficulty, gear/talents/glyphs, and capture time.
- Require a controlled healer role record before tuning throughput. Raid HPS alone does not declare delivered demand.
- Treat external logs as exact denominators only when composition, spec, duration, gear/effective stats, buffs, consumes, and damage demand match.
- An acquisition-valid fallback gear set can be intentionally unenchanted when slot-applicability authority is missing. Record it as a setup limitation; do not compensate in priorities or coefficients.

## First-edge checks

- Follow `observation -> target -> candidate -> native gates -> submission -> completion -> landed heal/absorb -> health outcome`.
- Retain actor-to-target distance, LOS, moving/instant-only state, each candidate rejection, selected spell, native failure, and fallback result.
- Correct target selection does not prove the selected spell is in range, in LOS, ready, affordable, or instant while moving.
- Pin DBC positive/friendly and negative/hostile ranges, then follow core range calculation before judging selector or executor behavior. Retain exact distance, combat reach, and range modifiers.
- `spell_cast` is submission evidence. A post-submission `result=ok` can carry `already_casting`, `global_cooldown`, or cooldown state; do not relabel it as rejection.
- Deduplicate trace records by actor plus decision/recorded time. One combat attempt may recur in decision, lifecycle, and mechanic entries.
- Separate retryable rejection from no-demand idle. `no_valid_profile_action` without health/demand context is not proof of healer inactivity under demand.
- If encounter movement puts a healer out of range or LOS, return the position error to the encounter owner. Preserve instant-only movement safety and do not extend spell range.

## Role measurements

- Require health floor, deaths, effective healing, raw healing/overheal, effective absorbs by caster/target, mana slope/time-to-OOM, response latency, target accuracy, dispels, cooldown periods, idle-under-demand, and cast failures.
- Healing aggregates keyed only by player entry can merge targets. Use GUID-bearing submissions and landed events for triage distribution.
- Absorb application is not absorb value. Aura presence and refresh blocking prove acquisition only; retain absorbed amount and prevented-damage attribution.
- Separate direct casts from HoT ticks, proc heals, trinket/weapon procs, encounter-attributed damage, and duplicate raw damage attribution.
- A low direct-heal HPS for Discipline is uninterpretable when shield absorbs are absent from telemetry.
- Review healer DPS only against demand state. Offensive casts are low value when they delay needed healing; DPS volume alone cannot prove displacement.
- Count cooldown use against declared required periods. Absence of a boss cooldown cast is not a miss when no required-period marker exists.
- Verify prep with native item submission, aura, cooldown, and item-count delta. Reserve count does not prove combat-potion use.

## Focused acceptance

- Test the first broken edge through the production selector, executor, caller, and final native result at both legal and illegal boundaries.
- Preserve movement ownership, GCD/cast resources, spellbook identity, ordinary native legality, and stable rejection reasons.
- Source-shape assertions can guard wiring but cannot prove native range, LOS, completion, absorbs, response latency, or survival.
- One matched healer demand window should show the expected edge moving. Raid completion is supporting evidence, not healer qualification.
