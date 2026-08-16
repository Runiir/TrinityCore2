# Rotation and mechanic translation model

Use this model to compare intent and evidence without pretending Trinity is an
APL interpreter or WoWSims is a dungeon engine.

## Common action record

Normalize each action to:

```text
source                 wowsims | trinity_profile | trinity_runtime | route
phase                  setup | prepull | combat | recovery | post_window
identity               spell | item | pet_command | movement | interaction | wait
actor/target scope     GUID/entry/selector and attempt/route generation
priority               APL index or bucket + score + sort order
conditions             typed observed facts plus the original expression/hash
resources              movement, target, GCD, cast, pet, interaction
movement               range envelope, LOS/path, stationary/instant constraints
outcome                 rejected | selected | submitted | finished | landed | progressed
reason                  typed rejection/outcome reason
```

Keep the original source path and content hash. A family mapping is an index for
review, not proof that predicates are equivalent.

## Condition families

Use these families to locate missing observations and gates:

| Family | WoWSims examples | Trinity examples |
|---|---|---|
| aura_state | `auraIsActive`, stacks, remaining time | required/forbidden self aura, stack/duration gates |
| owned_target_aura | dot active/remaining | owned target aura, maintain/refresh receipt |
| primary_power | current/max mana, rage, energy, focus, RP | min/max primary power and resource result |
| runes | rune count/cooldown/slot | ready-rune observation and minimum gate |
| combo_points | current combo points | min/max combo point gate |
| cooldown | spell/GCD readiness | native SpellHistory/GCD/cooldown group |
| action_availability | spell known/can cast | learned-spell and executable native gate |
| target_health | execute phase | min/max target health and observed schedule |
| enemy_count | target count, multidot | min/max enemies, strict ST/AoE flags |
| movement_range | distance/movement | native melee/range/LOS/path and movement directive |
| pet | pet option/action/uptime | exact ordinary pet identity, autocast, command, uptime |
| pet_totem_state | pet/totem duration or snapshot | exact pet/totem identity and observed state |
| proc_state | proc aura/trinket/ICD | observed aura/ICD receipt or an explicit unsupported gap |
| target_scope | source/target/owner selector | exact actor/target selector or GUID ownership |
| spec_resource_state | eclipse or other spec state | exact native spec-resource observation |
| sequence_state | sequence completion | typed state-machine receipt or explicit divergence |
| execution_latency | input/channel clipping delay | observed scheduler/cast timing policy |

Preserve unknown leaves as `unmapped_expression`. An absent numeric value is not
the same as a false boolean predicate: for example, an unavailable aura's
remaining time may evaluate as zero and make `<= 3s` true.

## Priority comparison

WoWSims normally selects the first usable APL action. Trinity selects the lower
`priority_bucket`, then higher score, then lower `sort_order`, then stable action
identity. Compare pairwise order only among shared actions and inspect every
inversion in context; conditional duplicates and strict sequences can make a
simple first-occurrence ranking incomplete.

## Runtime edge classification

Keep these edges distinct:

1. Profile loaded: exact generation/hash and action row exist.
2. Candidate built: live observations were captured.
3. Candidate valid: all executable gates passed.
4. Candidate selected: arbitration chose it and resource claims won.
5. Movement/authority admitted: range/path/LOS/route/mechanic permit submission.
6. Native submitted: session/core request accepted.
7. Finished: core cast/item/pet/movement completion observed.
8. Landed: exact target effect, damage, aura, interrupt, or progress observed.

The first missing edge is the diagnosis boundary.

For WoWSims, use aggregate action/aura/resource metrics to establish what
happened statistically, and the first-iteration debug log to establish ordered
casts, completions, state changes, and landed effects. Never infer exact action
order from aggregate cast counts alone.

## Mechanic mapping

WoWSims can model target count, distance, execute windows, target stats, static
buff/debuff conditions, and class actions. It generally cannot establish
Trinity route ownership, navmesh reachability, native boss timers/selectors,
threat, wipe recovery, vehicles, gossip, area triggers, or instance state.

For those, map route obligations to Trinity's typed candidate/resource/action
chain and use simulator comparisons only for the class-action envelope that
remains legal inside the mechanic.
