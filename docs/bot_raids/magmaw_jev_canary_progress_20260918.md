# Magmaw JEV canary progress

Branch: `codex/magmaw-jev-canary`<br>
Scope: normal Blackwing Descent 10N Magmaw only<br>
Reference: `experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_dps_reference_v1.json`

## Current conclusion

This branch is not regressing from the earlier 214k DPS clear into wipes. The
“wipe” signal was an acceptance-layer failure: the native route reached
`validation_route_manifest_complete`, Magmaw produced confirmed unit-death
evidence, all ten bots remained active, and the watchdog reported no wipe, death
loop, no-progress, or stuck event. The harness rejected the run because
`incomplete_evidence_identity` was still required by its generic acceptance
contract.

The live report now exposes `native_gameplay_outcome` separately from the
generic stage/certification result. JEV also receives a compact per-actor loss
budget: active-combat versus encounter-window DPS, actor-active cadence,
idle fraction, movement fraction, native actionable-failure ratio, semantic
candidate-gate buckets, and explicit contradictions. Route wall clock remains
a progress metric, not a DPS denominator. Expected wait rows remain in the
deterministic archive but are removed from JEV's action view. This makes a
low-confidence party-level choice an uncertainty signal rather than a reason
to discard the useful actor-level judgments.

The latest evidence boundary adds a target/duty overlay. Full-window target
aggregates distinguish Magmaw/head damage from Lava Parasite work, and native
failure timestamps are intersected with mechanic-target intervals and recent
movement events. The overlay reports `duty_explains_idle` and a separate
`counterfactual_status`; a partial recent ring is never treated as complete
movement evidence. On the shard21 replay, Balance had 132,911 originated
parasite damage (3.893% of its encounter damage) and 3 of 5 native failure
windows overlapped mechanic work or movement. JEV consequently chose
`collect_more_canaries` for Balance at 0.98 confidence and
`insufficient_data` for the party DPS-loss area at 0.82, instead of authorizing
the earlier uptime hypothesis.

The trace-backed runtime repair is safe so far. When every profile candidate is
rejected because a spell is already being cast, the resolver now reports
`Casting` and preserves `already_casting` instead of returning retryable
`no_action` and entering candidate backoff. This is a shared cadence fix, not a
class-specific damage or coefficient change.

The Balance add-duty is now implemented as an encounter-scoped policy: place
three Wild Mushrooms on the platform below the Lava Parasite wave and detonate
immediately after the third placement. Shard25 exposed a second geometry edge:
new parasites are airborne at spawn, so their live Z can still be 221--226
while the platform is about 211--212. Commit `39b7c9eeff` preserves live X/Y
but resolves Z through the native map floor query. Shard27 produced a native
clear with zero `88747` line-of-sight failures, but shard28 reproduced 12
destination-LOS failures in another valid route. Commit `b70eff769c` adds a
native LOS check and a bounded caster-facing fallback point; shard29 then
produced a clear with zero LOS or cast-failed placement outcomes. This
validates the placement path, but it does not yet establish WCL DPS parity.

For this review, WCL Summary DPS is the fight/encounter-window value: damage
divided by the selected combat interval used by the parse. It is not the
route's entrance-to-kill wall clock and it is not actor-only active-uptime DPS.
The analyzer now compares WCL with explicit
`encounter_window_dps`/`encounter_window_party_dps` fields. The legacy
`elapsed_dps`/`elapsed_party_dps` fields retain the same local event-window
arithmetic; `dps`/`party_dps` and `active_dps` remain diagnostics with different
denominators.

The latest full-window replay also makes the required signals explicit. JEV
sees Balance's native mushroom assignment and landed effect, the fixed baiter
identity selected by native roster rules, full-window damage gaps, and separate
normal target-eligibility gates. This removes the previous false target-lease
lead without allowing JEV to submit gameplay actions. The shard35 canary
confirmed a native clear after the Fire ranged-safety profile was read back
from the live test world: all ten bots survived, with no watchdog loop, stall,
or death-loop signal. Its generic certification rejection remains
`incomplete_evidence_identity`, which is separate from the native outcome.

## Canary ledger

All rows below are native Magmaw evidence. “Active-combat DPS” uses originated
damage over active-combat seconds; “encounter-window DPS” uses originated
damage over the selected local encounter event window. Route wall clock is not
shown in this table. The harness acceptance flag is intentionally shown
separately from gameplay outcome.

| Run | Result | Boss damage | Active-combat DPS | Encounter-window DPS | Native safety state | JEV |
| --- | --- | ---: | ---: | ---: | --- | --- |
| shard11 | clear | 28.27M | 200.5k | 177.5k | old runner identity failure; no wipe signal | pre-fix |
| shard13 | clear | 28.35M | 195.5k | 174.7k | old post-kill plateau classification | pre-fix |
| shard14 | clear | 28.46M | 207.7k | 175.3k | native manifest complete; harness identity rejection | aligned |
| shard15 | clear | 28.27M | 222.6k | 177.6k | 10 alive; no stuck/death/no-progress | aligned |
| shard16 | clear | 28.19M | 223.8k | 172.6k | 10 alive; candidate telemetry added | action-rejection signal was noisy |
| shard17 | clear | 28.29M | 221.0k | 185.4k | 10 alive; no watchdog failure | aligned; stuck none; movement |
| shard18 | clear | 28.19M | 216.9k | 198.4k | 10 alive; no watchdog failure | aligned; stuck none; movement |
| shard19 | clear | 28.19M | 222.0k | 210.2k | 10 alive; no watchdog failure | aligned (0.90); stuck none (0.92); movement (0.41) |
| shard20 | clear | 28.27M | 215.8k | 182.4k | 10 alive; no watchdog failure; identity-only certification rejection | aligned (0.91); stuck none (0.98); enhanced movement (0.68) |
| shard21 | clear | 28.19M | 201.4k | 192.0k | 10 alive; no watchdog failure; identity-only certification rejection | aligned (0.90); stuck none (0.98); enhanced movement (0.42), next uptime (0.38) |
| shard21-duty-replay | replay | 28.19M | 201.4k | 192.0k | same native clear; target/duty overlay added | aligned; stuck none; DPS `insufficient_data` (0.82); next `collect_more_canaries` (0.83); Balance `collect_more_canaries` (0.98) |
| shard23 | clear | 28.19M | 218.6k | 200.9k | 10 alive; no watchdog failure; three placements and three detonations | aligned; stuck none; DPS `insufficient_data`; Balance `collect_more_canaries` (0.89) |
| shard24 | clear | 28.27M | 231.7k | 221.0k | 10 alive; no watchdog failure; repeat duty clear | aligned; stuck none; DPS `insufficient_data`; Balance `collect_more_canaries` (0.59) |
| shard25 | clear | 28.19M | 223.8k | 191.9k | 10 alive; no watchdog failure; 18 native `88747` LOS failures | aligned; stuck none; Balance `collect_more_canaries` (0.97) |
| shard26 | clear | 28.19M | 229.2k | 215.9k | 10 alive; no watchdog failure; live-Z fix reduced LOS failures to 6 | aligned; stuck none; Balance `collect_more_canaries` (0.94) |
| shard27 | clear | 28.19M | 229.2k | 187.7k | 10 alive; no watchdog failure; zero `88747` LOS failures | aligned; stuck none; DPS `insufficient_data` (0.85); Balance `collect_more_canaries` (0.95) |
| shard28 | clear | 28.19M | 234.9k | 218.3k | 10 alive; no watchdog failure; repeat exposed 12 destination-LOS failures | aligned; stuck none; DPS `insufficient_data` (0.84); next `collect_more_canaries` (0.74) |
| shard29 | clear | 28.24M | 209.2k | 193.2k | 10 alive; no watchdog failure; 12 placements, 3 detonations, zero LOS/cast-failed placement outcomes | aligned; stuck none; DPS `insufficient_data` (0.85); next `collect_more_canaries` (0.68) |
| shard30 | clear | 28.19M | 233.0k | 213.3k | 10 alive; no watchdog failure; 0 deaths; full-window action evidence retained | native clear; no loop/stall; identity-only certification rejection |
| shard31 | clear | 28.23M | 233.3k | 211.4k | 10 alive; no watchdog failure; 0 deaths; full-window action evidence retained | native clear; no loop/stall; identity-only certification rejection |
| shard32 | clear | 28.19M | 218.6k | 180.7k | native clear; one death; no watchdog loop/stall; event ring dropped 0; Balance 3 detonations and 73.0k landed mushroom damage | v37 aligned (0.83); stuck none (0.49); DPS `uptime` (0.75); next `collect_more_canaries` (0.41) |
| shard33 | clear | 28.19M | 205.8k | 179.3k | native clear; no watchdog loop/stall; scoped Chain Lightning path observed | v38 aligned; stuck none; DPS `uptime`; no patch promotion |
| shard34 | clear | 28.27M | 217.5k | 202.8k | native clear; no watchdog loop/stall; Chain Lightning path direct and attributable | v39/v40 aligned; stuck none; corrected WCL-window contract |
| shard35 | clear | 28.19M | 213.6k | 200.6k | all ten alive; no watchdog loop/stall/death loop; Fire profile `263_v3` read back; Balance 3 detonations | v41/v42 aligned; active stuck set empty; global next fix remains below floor (`collect_more_canaries`/`uptime_cadence`) |

The post-repair canaries therefore show no wipe regression. Active-combat DPS
is within normal run variance while encounter-window DPS moves with both
damage and kill duration. Shard19 shortens the boss window to 134.1 seconds versus shard18's
142.1 seconds and raises active-combat party DPS by 2.4% and
encounter-window party DPS by 6.0%. JEV marks the change effect
`not_comparable` (0.69 confidence), so this
is a positive canary signal, not a promotion claim. Shard18 also retains two
`blocked_no_fallback` and eight
`repeated_decision_loop` diagnostics in the final terminal snapshot; the
snapshot is after Magmaw is dead and JEV classifies the active stuck set as empty.
They remain tracked rather than being counted as a successful gameplay loop.

## DPS comparison

The primary WCL reference is a 111.3-second Magmaw 10N parse with 246.2k raid
DPS and these comparable actor values: Balance 41.0k, Fire 40.2k, Elemental
41.9k, Affliction 40.3k, and Blood 26.2k. It has one Fire Mage and no Hunter,
while the bot roster has two Fire Mages and one Survival Hunter, so it is a
comparison reference, not a controlled floor.

| Bot spec | Shard17 active-combat / encounter-window | Shard18 active-combat / encounter-window | WCL comparable DPS |
| --- | ---: | ---: | ---: |
| Balance | 37.1k / 20.5k | 30.7k / 20.1k | 41.0k |
| Fire A | 46.3k / 29.0k | 38.2k / 24.4k | 40.2k |
| Fire B | 57.6k / 25.6k | 53.4k / 32.4k | 40.2k |
| Affliction | 42.8k / 31.0k | 44.7k / 34.5k | 40.3k |
| Elemental | 45.3k / 28.2k | 46.0k / 33.4k | 41.9k |
| Survival | 45.0k / 33.4k | 42.7k / 35.5k | no matched WCL actor |

Shard19 after the 30/18 bait-envelope repair is: Balance 28.4k / 19.5k,
Fire A 47.7k / 29.1k, Fire B 65.0k / 42.6k, Affliction 48.2k / 37.0k,
Elemental 40.8k / 28.7k, and Survival 41.2k / 34.6k. The two fixed baiters'
average distances fell from 36.15/36.78 yards in shard18 to 34.67/34.10 yards
in shard19, and their movement fractions fell from 0.256/0.280 to
0.141/0.175. This validates the range-envelope hypothesis, but does not yet
close the remaining Balance/uptime gap to WCL.

The repeat canaries are not a wipe regression. Shard20 dealt 28.27M damage in
131 seconds of combat; shard21 dealt 28.19M in 140 seconds. The active-combat
denominator therefore moved from 215.8k to 201.4k while encounter-window party
DPS increased from 182.4k to 192.0k. Per-actor repeat values are:

| Bot spec | Shard20 active-combat / encounter-window | Shard21 active-combat / encounter-window | WCL context |
| --- | ---: | ---: | ---: |
| Balance | 32.7k / 22.9k | 38.3k / 23.2k | 41.0k |
| Fire A | 52.2k / 29.4k | 42.7k / 24.3k | 40.2k |
| Fire B | 49.9k / 28.4k | 48.6k / 26.2k | 40.2k |
| Affliction | 45.4k / 32.0k | 43.1k / 35.6k | 40.3k |
| Elemental | 40.1k / 25.1k | 40.2k / 28.4k | 41.9k |
| Survival | 41.7k / 27.6k | 43.1k / 34.7k | no matched WCL actor |

Repeated enhanced JEV samples on the unchanged shard21 evidence returned the
same actor-level direction even though the single party-level label varied:
Balance `uptime_cadence` at 0.67–0.71 confidence, Survival
`movement_recovery` at 0.72–0.80, and Elemental `collect_more_canaries` at
0.92–0.94. The party-level DPS label moved between `movement` and `uptime` at
0.42–0.51, and the global next fix stayed low at 0.35–0.46. This is the useful
signal boundary: actor actions are attributable and repeatable enough to review,
while a shared action is not authorized.

Shard20 was less stable: its Balance action varied between movement and
`collect_more_canaries` below the 0.60 floor, while the party label stayed
movement at 0.61–0.68 and the global next fix stayed `collect_more_canaries` at
0.57–0.59. These two canaries therefore authorize a targeted Balance
cadence/uptime observation, not a Balance code change or a shared movement
repair.

The stable gap is now mostly duty/uptime and movement, not a proven native
“all casts are rejected” failure. Balance remains the clearest comparable
active-DPS gap; Fire A has the largest movement exposure in the repeat runs.
Those are leads for the next bounded repair, not permission to scale spell
coefficients or tune to an unmatched WCL denominator.

The post-duty shard27 actor snapshot is still mixed against the comparison
context: Balance 33.0k active versus 41.0k WCL, Elemental 34.9k versus 41.9k,
and Blood 13.4k versus 26.2k; both Fire Mages and Affliction are at or above
their matched WCL context, and Survival has no matched WCL actor. JEV labels
the change `not_comparable` at 0.86 and keeps the next action at
`collect_more_canaries` (0.58). That is a request for more attributable
samples, not authorization to change coefficients or discard the floor fix.

Shard29's active-DPS snapshot remains mixed: Balance 27.6k versus 41.0k WCL,
Affliction 33.4k versus 40.3k, and Blood 19.2k versus 26.2k, while both Fire
Mages and Elemental are at or above their matched WCL context and Survival has
no matched WCL actor. This branch fixes the Balance add mechanic without
claiming that every DPS spec is already on the WCL reference.

The newest shard32 encounter-window comparison is:

| Bot spec | Active-combat `dps` | Actor-active `active_dps` | Encounter-window `encounter_window_dps` (legacy `elapsed_dps`) | WCL summary context |
| --- | ---: | ---: | ---: | ---: |
| Balance | 25.1k | 34.3k | 20.8k | 41.0k |
| Fire A | 21.3k | 42.0k | 17.6k | 40.2k |
| Fire B | 38.5k | 58.4k | 31.9k | 40.2k |
| Affliction | 39.2k | 44.3k | 32.4k | 40.3k |
| Elemental | 33.1k | 44.1k | 27.3k | 41.9k |
| Survival | 40.7k | 46.1k | 33.6k | no matched WCL actor |
| Blood | 11.6k | 15.6k | 9.6k | 26.2k |

This is why active DPS alone cannot answer the parity question: Elemental's
active rate is above the WCL context, but its encounter rate is lower because
its damage window is only 86 of 129 combat seconds. The full-window cadence
overlay reports a 5.91-second maximum damage gap, five gaps of at least three
seconds, and 23.0 seconds in those gaps. JEV selects `uptime_cadence` for
Elemental at 0.97, but the global next fix remains low-confidence and selects
`collect_more_canaries`; no Elemental gameplay patch is admitted from this
single run.

The corrected v40–v42 comparison uses the encounter-window field that matches
the WCL Summary denominator:

| Bot spec | Shard34 window DPS | Shard35 window DPS | WCL comparable DPS |
| --- | ---: | ---: | ---: |
| Balance | 19.2k | 26.1k | 41.0k |
| Fire A | 34.7k | 32.5k | 40.2k |
| Fire B | 23.1k | 29.4k | 40.2k |
| Affliction | 36.6k | 32.5k | 40.3k |
| Elemental | 34.7k | 29.6k | 41.9k |
| Survival | 39.8k | 31.6k | no matched WCL actor |
| Party | 202.8k | 200.6k | 246.2k |

This is a measurement correction, not a claim that the bots already match
WCL. Local party damage is about 28.2M in both runs; the remaining gap is
primarily the longer local encounter window and actor uptime/cadence. JEV v40
and v41 classify the global action as low-confidence collection; the v42 rerun
leans toward `uptime_cadence` at 0.48, still below the 0.60 action floor.
Their actor-level signals are more specific: Balance assignment-controlled
`collect_more_canaries`, Fire B `uptime_cadence`, Affliction
`uptime_cadence`, and Elemental `uptime_cadence`. None of those is a
high-confidence, counterfactual-clean spell-policy patch yet.

## Balance mushroom duty evidence

The native action ledger shows the intended sequence rather than a generic
profile scan:

| Run | Placement `88747` | Detonation `88751` | Native placement issue | Result |
| --- | ---: | ---: | --- | --- |
| shard23 | 12 successful submissions | 3 successful submissions | none | clear |
| shard24 | 6 successful submissions | 2 successful submissions | none | clear |
| shard25 | 12 successful submissions | 3 successful submissions | 18 LOS failures; 15 position-reconcile failures | clear, geometry exposed |
| shard26 | 13 successful submissions | 4 successful submissions | 6 LOS failures | clear, airborne-Z evidence |
| shard27 | 10 successful submissions | 3 successful submissions | 0 LOS failures; one native spell result 49 | clear, floor projection validated |
| shard28 | 11 successful submissions | 3 successful submissions | 12 LOS failures; 8 position-reconcile failures | clear, repeat exposed destination geometry |
| shard29 | 12 successful submissions | 3 successful submissions | 0 LOS failures; 0 cast-failed placement outcomes | clear, LOS-aware fallback validated |
| shard35 | 3 successful submissions | 3 successful submissions | 30 native LOS/cast-failed placement outcomes; 24 position-reconcile waits | clear, assignment executed but geometry still noisy |

Shard27 also recorded the surviving Wild Mushroom at platform Z≈211.66. The
new helper intentionally uses the parasite's live X/Y but samples the floor
with `Map::GetHeight`; it no longer uses `GetHomePosition()` or an airborne
target Z. The normal route remained death-free in every mushroom-duty canary.
In shard35 the assignment produced 295,099 originated Wild Mushroom damage
and three successful detonations, but placement still had 29 LOS and one
cast-failed outcome. JEV therefore correctly marks the assignment as executed
while retaining placement geometry as a follow-up signal rather than treating
the duty as a clean DPS counterfactual.

## Signal correction and JEV contract

The first candidate-rejection report sent large profile-search counts to JEV:

- `already_casting`, GCD, resource, aura, target, and encounter-policy waits;
- conditional profile gates such as movement/aura/item filters; and
- actual native outcomes.

Those categories were not separated, so JEV could call a normal candidate scan
an `action_rejection` DPS loss. Two analyzer defects compounded the problem:
the native action ledger was compacted twice and its `result` fields became
`unknown`, and the prompt did not require material native-failure corroboration.

The current evidence boundary now sends:

- native outcome counts per DPS actor, including actionable-failure ratio;
- expected profile waits separately;
- conditional profile gates separately; and
- only a small actionable candidate-gate list.

The new actor loss packet adds the missing causal context without adding raw
noise. It reports the idle fraction separately from movement, groups candidate
gates by movement/range, targeting, profile policy, and resource/cooldown, and
records contradictions such as low movement despite a movement-gate count. It
also keeps policy hypotheses such as Balance area-spell suppression separate
from native failures. The JEV action view contains only direct native failures;
the complete wait/action ledger remains in the deterministic report for audit.

The target/duty overlay adds the signal that was missing from the original
actor packet: target purpose and temporal overlap. A low uptime number alone is
not enough to select a cadence fix. The analyzer now requires complete enough
counterfactual evidence and no required-duty overlap before treating uptime,
movement, or rotation as an actionable actor repair. Partial or low-confidence
answers remain in the report with their probability maps and are routed to
review/collection rather than discarded.

The v37 post-commit JEV input adds two further safeguards. Balance is classified through a
typed `actor_assignment_30001` question and is marked `assignment_executed`
only because both a native detonation and landed Wild Mushroom damage are
present; placement decision rows are not treated as landed casts. The native
fixed-bait rule marks only the lowest-GUID Fire Mage as the fixed pillar baiter,
so Fire A's low encounter DPS is not mislabelled as a clean movement or
rotation counterfactual. Normal target-aura, target-health, interruptibility,
and purpose gates remain audit data but no longer create a `target_lease`
candidate. In v37 JEV chose `uptime` for the party area (0.75),
`uptime_cadence` for Elemental (0.96), and `collect_more_canaries` for Balance
(0.93) and Fire A (0.95). The post-commit replay preserved the same action
directions as v36 while changing only confidence weights.

The corrected v40–v42 packets make the WCL boundary explicit. JEV receives
`wcl_window_dps`, derived from originated damage over `duration_sec`, while
`dps`, `active_dps`, and route wall clock are labeled diagnostics. On shard35
the actor loss packets show low native failure rates and low movement for Fire
B, Affliction, and Elemental, so their `uptime_cadence` labels are review
signals rather than direct spell changes. Balance is explicitly marked as a
required assignment; its three detonations and landed effect prevent the
assignment from being mistaken for a free rotation sample. The global
`next_fix` remains below the action floor: v41 chose
`collect_more_canaries` at 0.35, while the v42 rerun chose
`uptime_cadence` at 0.48. The native clear remains authoritative.

Shard17 native outcomes contain 113 actionable failures out of 4,867 outcomes
(2.32%); shard18 contains 87 out of 5,119 (1.70%). All six DPS actors stay below
5% in both reports, and both JEV reviews now choose `movement`, never
`action_rejection`.

Final mandatory JEV judgments:

- shard17: path `aligned` (0.97), stuck `none` (0.96), DPS loss `movement`
  (0.68), next fix `movement_recovery` (0.61);
- shard18: path `aligned` (0.87), stuck `none` (0.96), DPS loss `movement`
  (0.56), next fix `movement_recovery` (0.37).

The first shard21 replay used the old party-only question and returned DPS loss
`movement` (0.46) and next fix `movement_recovery` (0.46). Enhanced replays
used the actor loss packet and direct-failure-only action view; their party DPS
labels varied between `movement` and `uptime`, but the actor-level actions above
were the stable, attributable results. The remaining low confidence is honest
ambiguity between actor-specific losses, not a reason to manufacture a shared
fix.

JEV remains shadow analysis only; native TrinityCore telemetry is the gameplay
authority.

The duty-aware replay supersedes the earlier Balance `uptime_cadence` hint for
this evidence. It is an analyzer replay, not a second gameplay run, and it
does not authorize a Balance or shared-arbitration patch. The next fresh
canary must test whether the target/duty relationship repeats with a new
combat-log capture.

## Fixed-behavior ledger

| Behavior | Evidence | Status |
| --- | --- | --- |
| Partial-death target churn / repeated retreat publication | shard12 Drudge trace | fixed in route recovery; later runs clear |
| Boss-death tail misclassified as stuck | shard13 trace | fixed in analyzer terminal-tail handling |
| Duplicate boss GUID death did not advance the route | shard14 lifecycle trace | fixed by advancing the manifest after terminal death |
| In-flight profile casts entered retryable candidate backoff | shard16 full-window native outcomes | fixed by preserving `Casting`/`already_casting`; validated in shards17–18 |
| Candidate-search waits misclassified as native DPS rejection | shard17 JEV payload audit | fixed in JEV input contract and idempotent outcome normalization |
| Terminal-tail `blocked_no_fallback` diagnostics | shard18 post-kill snapshot | open telemetry cleanup; not active during the boss window |
| Fixed bait endpoints exceeded the native 35-yard ranged envelope | shard18 geometry/position trace | repaired to 30/18 in strategy and shadow lane planner; shard19 canary moved both baiters inside the envelope |
| Generic acceptance/stage failure looked like a gameplay wipe | shards20–21 native clear plus identity-only rejection | fixed in live report with `native_gameplay_outcome_v1`; certification remains separate |
| Party-level JEV choice mixed Balance idle time with ranged movement | shard21 actor loss replay plus target/duty overlay | fixed in JEV evidence contract; duty-correlated losses now block premature cadence/movement patches and low-confidence answers remain review-only |
| Balance mushrooms were projected to the elevated parasite home/spawn Z | shard25: 18 native LOS failures and airborne add coordinates; shard26: 6 LOS failures | fixed in `39b7c9eeff` with native platform-floor projection; shard27 confirmed one clean sample |
| Exact platform points could still fail native destination LOS | shard28 repeat: 12 `88747` LOS failures and 8 position-reconcile failures | fixed in `b70eff769c` with a bounded caster-facing LOS fallback; shard29 has zero LOS/cast-failed placement outcomes |
| Required Balance add duty and fixed pillar-bait identity were absent from the JEV causal packet | shard32 assignment/action evidence and native baiter resolver | fixed in analyzer evidence contract; Balance is assignment-aware and Fire A is not granted a clean movement counterfactual |
| Normal target eligibility gates looked like target-lease loss | shard32 Elemental candidate counts | fixed in `target-signal-v1`; v37 retains the gates for audit but removes them from target-lease attribution |
| WCL comparison used ambiguous local field names | shard34 replay plus v40 contract audit | fixed with explicit `encounter_window_dps`/`encounter_window_party_dps`; `dps` and `active_dps` remain diagnostics, route wall clock remains progress-only |
| Committed Fire safety SQL was absent from the persistent validation world | shard34/shard35 profile readback | fixed for this canary by applying the existing migration and verifying profile `263_v3`; future canaries must read back world-profile identity before execution |
| Balance mushroom assignment still has intermittent placement geometry noise | shard35: 3 detonations, 295,099 Wild Mushroom damage, 30 native placement failures | open follow-up; preserve the three-placement contract and collect a geometry-focused counterfactual before changing Balance rotation |

## Next bounded action

Do not revert the cast-state, bait-envelope, floor-projection, LOS-fallback, or
Fire ranged-safety repairs. Shard35 is a native clear with no active stuck
behavior, but it does not establish WCL parity: the corrected party
encounter-window rate is 200.6k versus the 246.2k reference, and the Balance
assignment still has placement failures. Mandatory JEV review keeps the global
next fix below the action floor (`collect_more_canaries` in v41,
`uptime_cadence` at 0.48 in v42); no additional Balance rotation, shared
movement, target-lease, or native-mechanics patch is
authorized from this evidence alone. The next canary should isolate Balance
placement geometry or provide a matched role counterfactual, while preserving
the three-mushroom duty contract. Keep WCL as a normalized encounter-window
comparison reference, not an unconditional per-actor floor.

Compact JEV reports and native combat ledgers for shards16–32 are checkpointed
through DVC in the companion artifact pointers for this branch; the corrected
shard33–35 summaries are checkpointed in the new WCL-contract artifact. Raw
live reports remain in `/tmp/magmaw-normal-shard-{16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35}-20260918`
during review and are not committed to Git.

## Measurement repair and current-code repeats (shards49–52b, 2026-09-19)

The mandatory JEV loop was run again on the clean control, the scoped Balance
Starfall canary, and two same-code repeats after commit `d49921c96f`. The
analyzer now bounds `duration_sec` by the first and last positive hostile
`damage_done` aggregate and retains the complete telemetry lifetime as
`capture_duration_sec`. This repaired a real signal failure: shard52b had a
236.549-second capture lifetime but only a 133.436-second hostile damage
window, so its party rate is 211.6k rather than the old tail-diluted 119.4k.

| Run | Fight window | Capture lifetime | Encounter-window party DPS | Active party DPS | Native result |
| --- | ---: | ---: | ---: | ---: | --- |
| shard49 clean control | 127.347s | 138.533s | 222.8k | 238.4k | clear, 0 deaths, 0 active stuck |
| shard50 scoped Starfall | 129.339s | 131.934s | 218.0k | 229.2k | clear, 0 deaths, 0 active stuck |
| shard51 same-code repeat | 146.273s | 150.820s | 193.4k | 203.5k | clear, 0 deaths, 0 active stuck |
| shard52b same-code repeat | 133.436s | 236.549s | 211.6k | 212.3k | clear, 0 deaths, 0 active stuck |

The corrected party mean is 211.4k versus the 246.2k WCL Summary context. The
latest JEV judgment is path `aligned` (0.77), stuck `none` (0.50), DPS area
`movement` (0.36), and next fix `movement_recovery` (0.44); promotion remains
unsafe (0.04). Balance's simple three-mushroom assignment landed 222,197
damage in shard52b, but it is not a clean rotation counterfactual. Fire A is
the fixed pillar-bait identity with execution unobserved. Fire B is eligible
and reached 41.9k in shard52b, while Elemental reached 25.1k with an
attributable movement candidate (0.83) only in that repeat. Affliction also
has a movement candidate (0.64). Those actor signals are not repeated enough
to justify a shared movement patch yet.

The prior 119.4k result was therefore an analyzer regression, not a gameplay
wipe. Native completion-watchdog evidence remains authoritative: all four
replays cleared Magmaw with no deaths, no active stuck behaviors, no death
loops, and no repeated-decision watchdog stop. Corrected compact summaries and
JEV judgments are checkpointed in the DVC artifact
`magmaw_jev_canary_20260918`; raw reports remain under `/tmp`.

## Next bounded action after the measurement repair

Do not edit Balance, Fire A, or shared movement from the current aggregate.
The next gameplay canary should be a matched, assignment-aware counterfactual
for one eligible ranged actor—preferably Elemental movement—so JEV can compare
the same duty and fight-window boundaries before and after one narrow change.
Run the full sequence after that change: build/tests, completion-watchdog
Magmaw clear, corrected combat analysis, JEV, and ledger update. A low-
confidence JEV recommendation remains collection evidence, not an action.

## Per-actor timeline requests and assignment context (shard87, 2026-09-19)

The analyzer now uses the WCL-vs-native timeline as the primary DPS signal and
decomposes the mandatory Jev review into small requests:

1. one group request for route/path, stuck behavior, promotion safety, DPS-loss
   area, and group coherence;
2. one `actor_action_*` request for each local DPS actor; and
3. one final `next_fix` request that receives the typed group and actor
   judgments.

The local roster is not collapsed to only the WCL actors. Shard87 compared all
10 local actors, with six same-spec WCL references available (Balance, both
Fire Mage actors using an explicitly marked duplicate reference, Affliction,
and Elemental plus the Blood tank) and four actors explicitly marked
`missing_wcl_reference` (the Survival Hunter and three healers). A missing
reference is diagnostic-only; it is never treated as a pass or a failure.
WCL completed casts and native landed-damage observations remain separate event
types because periodic ticks and multi-target rows can outnumber originating
casts.

Balance's mushroom assignment is now context inside the Balance actor packet.
The run emitted `actor_action_30001`, but no `actor_assignment_30001` request;
`progress.actor_assignment_judgments` is empty by design. Native assignment
evidence remains available for interpreting the actor timeline, matching the
existing Mage and Hunter treatment.

Shard87 was a native Magmaw clear with completion reason
`validation_route_manifest_complete`, but certification was incomplete, so the
wrapper correctly classified it as `diagnostic_only`. There was one death, no
active stuck behavior, and no death-loop or no-progress watchdog stop. The
native encounter-window party rate was 211.9k. The per-actor comparison was:

| Actor | Bot encounter-window DPS | WCL reference DPS | Jev actor direction |
| --- | ---: | ---: | --- |
| Balance | 18.5k | 41.0k | collect more canaries (0.58) |
| Fire A | 27.9k | 40.2k | collect more canaries (0.63) |
| Fire B | 31.1k | 40.2k | movement recovery (0.64) |
| Affliction | 40.7k | 40.3k | collect more canaries (0.60) |
| Survival Hunter | 38.0k | no reference | collect more canaries (0.61) |
| Elemental | 37.8k | 41.9k | movement recovery (0.53) |

These values are a diagnostic comparison, not a claim of WCL parity or an
automatic acceptance floor. Group Jev classified the run as actor-divergent
(0.84), with no active stuck behavior (0.86), and selected
`collect_more_canaries` as the next fix (0.76). The low-confidence actor
directions therefore remain review evidence; no rotation, assignment, or
shared-arbitration patch is authorized from shard87 alone.

Runs84–86 were route-closure preflight failures rather than DPS canaries. The
wrapper now stages the repository's exact route manifest and route JSONL into
the external validation source only for preflight, preserves the external
bytes/modes, and restores them after the run. Shard87 passed that preflight;
the external route files were restored afterward.

| Behavior | Evidence | Status |
| --- | --- | --- |
| Separate Balance Jev assignment request duplicated actor review | shard87 request-stage manifest | fixed: assignment context stays in the Balance actor packet; no separate assignment question is emitted |

## Next bounded action after the request split

Keep the per-actor/group request topology. Do not patch Balance, Fire, or
shared movement based on shard87's low-confidence actor directions. The next
canary should repeat the same normalized timeline comparison with a matched
baseline and use the actor-specific cadence/gap evidence to select one narrow
repair only after it repeats. Native completion-watchdog outcome remains the
gameplay authority; Jev remains review-only.
