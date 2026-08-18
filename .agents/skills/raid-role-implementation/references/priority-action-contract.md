# Priority/action contract

The local comparison source is `/home/runiir/Games/modplayrbots` (spelled
`modplayrbots` in the current filesystem). Bind its Git revision before using
it. Review these concepts:

- `src/Bot/Engine/Action/Action.h`: action, prerequisite, alternative, continuer;
- `src/Bot/Engine/Engine.cpp`: triggers/defaults enter a relevance queue, useful
  and possible gates run, prerequisites precede execution, and failures expose
  alternatives;
- class `Strategy` files: small triggers and actions rather than one monolith.

Borrow the shape, not AzerothCore/WotLK APIs:

| Playerbots concept | Trinity-Cata contract |
| --- | --- |
| trigger/value | typed observation captured in candidate evidence |
| relevance queue | explicit priority plus utility and stable tie-break |
| `isUseful` | cheap contextual candidate gate |
| `isPossible` | native executable gate: known spell, resource, GCD, range, LOS |
| prerequisite | separate higher-priority candidate or durable state transition |
| alternative | same-tick fallthrough with a typed rejection reason |
| continuer | observed completion schedules the next state, never assumed success |

Use `BotClassSpecActionProfile`, `BotActionArbiter`,
`BotNativeActionIntent`, and `BotMeleeAutoAttackIntent`. Keep movement, GCD,
cast, target, pet, and interaction resources explicit. A retryable rejection
must not block a compatible lower-priority action in the same tick.

Telemetry must distinguish candidate built, valid, selected, blocked,
submitted, finished, landed, and progressed. That distinction is both the
diagnostic signal and the later policy-training label.
