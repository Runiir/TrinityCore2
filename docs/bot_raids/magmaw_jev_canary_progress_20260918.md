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
budget: active versus elapsed DPS, idle fraction, movement fraction, native
actionable-failure ratio, semantic candidate-gate buckets, and explicit
contradictions. Expected wait rows remain in the deterministic archive but are
removed from JEV's action view. This makes a low-confidence party-level choice
an uncertainty signal rather than a reason to discard the useful actor-level
judgments.

The trace-backed runtime repair is safe so far. When every profile candidate is
rejected because a spell is already being cast, the resolver now reports
`Casting` and preserves `already_casting` instead of returning retryable
`no_action` and entering candidate backoff. This is a shared cadence fix, not a
class-specific damage or coefficient change.

## Canary ledger

All rows below are native Magmaw evidence. “Active DPS” uses originated damage
seconds; “elapsed DPS” uses the full wall-clock boss window. The harness
acceptance flag is intentionally shown separately from gameplay outcome.

| Run | Result | Boss damage | Active DPS | Elapsed DPS | Native safety state | JEV |
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

The post-repair canaries therefore show no wipe regression. Active DPS is
within normal run variance while elapsed DPS improves because the fights finish
faster. Shard19 shortens the boss window to 134.1 seconds versus shard18's
142.1 seconds and raises active party DPS by 2.4% and elapsed party DPS by
6.0%. JEV marks the change effect `not_comparable` (0.69 confidence), so this
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

| Bot spec | Shard17 active / elapsed | Shard18 active / elapsed | WCL comparable DPS |
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
131 seconds of combat; shard21 dealt 28.19M in 140 seconds. The active-DPS
denominator therefore moved from 215.8k to 201.4k while elapsed party DPS
increased from 182.4k to 192.0k. Per-actor repeat values are:

| Bot spec | Shard20 active / elapsed | Shard21 active / elapsed | WCL context |
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
| Party-level JEV choice mixed Balance idle time with ranged movement | shard21 actor loss replay | fixed in JEV evidence contract; high-confidence actor actions are retained, low-confidence global actions remain review-only |

## Next bounded action

Do not revert the cast-state or bait-envelope repairs. The next bounded
validation is a Balance cadence/uptime canary with actor-level action evidence;
do not make a shared movement change from the old party-level diagnosis. Keep
the Balance area-policy observation as a separate counterfactual hypothesis,
because policy-gate counts are not native failures. Keep WCL as a normalized
comparison reference, not an unconditional per-actor acceptance threshold.

Compact JEV reports and native combat ledgers for shards16–21 are checkpointed
through DVC in the companion artifact pointer for this branch. Raw live reports
remain in `/tmp/magmaw-normal-shard-{16,17,18,19,20,21}-20260918` during review and
are not committed to Git.
