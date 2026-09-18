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

The two post-repair canaries therefore show no wipe regression. Active DPS is
within normal run variance while elapsed DPS improves because the fights finish
faster. Shard18 also retains two `blocked_no_fallback` and eight
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

Shard17 native outcomes contain 113 actionable failures out of 4,867 outcomes
(2.32%); shard18 contains 87 out of 5,119 (1.70%). All six DPS actors stay below
5% in both reports, and both JEV reviews now choose `movement`, never
`action_rejection`.

Final mandatory JEV judgments:

- shard17: path `aligned` (0.97), stuck `none` (0.96), DPS loss `movement`
  (0.68), next fix `movement_recovery` (0.61);
- shard18: path `aligned` (0.87), stuck `none` (0.96), DPS loss `movement`
  (0.56), next fix `movement_recovery` (0.37).

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

## Next bounded action

Do not revert the cast-state repair. The next repair candidate is movement/uptime
for Balance and the far-position Fire actor, but it needs a trace-backed change
that preserves the Magmaw formation and mechanic assignments. Compare movement
windows with successful casts and native range/LOS outcomes before changing the
formation or a class profile. Keep WCL as a normalized comparison reference,
not an unconditional per-actor acceptance threshold.

Compact JEV reports and native combat ledgers for shards16–18 are checkpointed
through DVC in the companion artifact pointer for this branch. Raw live reports
remain in `/tmp/magmaw-normal-shard-{16,17,18}-20260918` during review and are
not committed to Git.
