# Tank review notes

Use these checks for a bounded, trace-backed tank role review.

## Ownership and threat

- Reconstruct hostile victim ownership by actor and timestamp; a count of tank-owned hostiles does not identify which tank owns them.
- Separate generic taunts from encounter-assigned swaps, pickup actions, and threat transfers.
- A generic taunt is eligible only when a live hostile has a real non-tank victim; reject no-victim, self-owned, and other-cohort-tank-owned targets.
- Verify candidate, gates, priority, submission, native completion, and post-action victim transition. Submission is not a landed taunt.
- Preserve pickup behavior on healer/DPS victims when suppressing tank-to-tank taunts.
- Treat repeated alternating taunt submissions as a resolver/authority lead before editing class priorities.

## Mitigation and healer pressure

- Align health, incoming boss hits, defensive submissions, aura apply/remove, absorbs, and healer delivery on one timeline.
- Judge defensive timing by damage covered and survival margin, not cast count alone.
- Separate direct self-healing, absorbs, pets, and raid healing before quoting tank sustain.
- Attribute healer pressure across every actor; report tank and non-tank intake, avoidable damage, deaths, and recovery.
- Check trash and boss windows independently because control, positioning, and damage shapes differ.
- Do not lower defensive health gates without synchronized health and landed-effect evidence.

## Position and movement

- Tie distance and movement to mechanics, target identity, incoming damage, and timestamps.
- Event-weighted moving fraction is not wall-clock movement uptime.
- Distinguish tank positioning faults from encounter movement policy and post-kill route recovery.
- Verify target changes during vulnerability/add windows rather than inferring them from aggregate DPS.

## Measurement traps

- A clear proves completion, not tank-role quality or throughput acceptance.
- A combat-log event and a trace submission measure different stages; never compare their counts as casts landed.
- Keyword avoidable-damage classifiers need mechanic/timestamp confirmation.
- Compare external logs only with matched roster, duration, difficulty, targets, gear, effective stats, talents, glyphs, consumes, and cadence.
- Canonical gear acquisition can be valid while missing enchants/reforges still blocks numerical parity and coefficient tuning.
- Never normalize with GM auras, artificial health, or hidden buffs.

## Repair handoff

- Stop at the first broken observation-to-outcome edge and assign shared runtime/mechanic faults to one coordinator owner.
- Name the exact production path, sibling paths that can drift, focused behavior test, and explicit non-regression cases.
- Acceptance must include native outcome and role outcome: stable ownership, expected pickups/swaps, survival, healer demand, avoidable damage, and all-actor throughput.
- If victim transitions, health history, aura windows, or completion events are absent, request that observation instead of guessing a policy repair.
