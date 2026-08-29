# Magmaw parasite-control architecture stop

## Decision

`magmaw_parasite_control_allows_player_infection` reached ten unique
current-standard occurrences. No new Magmaw canary is admitted until the
movement transition and its deterministic replay preserve this invariant:

> Once a fixed baiter admits a Magmaw lane transition, the transition identity,
> direction, and destination remain immutable until native arrival or a typed
> lethal-safety preemption. Observation churn, parasite GUID/position changes,
> and generic arbitration-lease expiry cannot select a new destination.

After a lethal-safety preemption, the same transition resumes. Only native
arrival, a new Pillar/parasite-release generation after arrival, or an exact
attempt reset may retire it. Local parasite evasion by a non-baiter cannot
mutate the cohort transition.

## Counted runs

1. `magmaw-canary91-af1ff054dc`
2. `trinity-magmaw-821a455-widewatch.IAOFuG`
3. `trinity-magmaw-7d9e313-autonomous.3h53mE`
4. `trinity-magmaw-e290121-autonomous.yRarrl`
5. `trinity-magmaw-c4dff8b7-autonomous.KYV6xM`
6. `trinity-magmaw-202994c78e-autonomous.bo3kSY`
7. `trinity-magmaw-5b67a352ec-canary95.ExM0XG`
8. `trinity-magmaw-a1fff71538-canary104.G772RN`
9. `trinity-magmaw-902ff5545e-canary105.N6HWpF`
10. `trinity-magmaw-d111136523-canary109.5GqLp7`
11. `trinity-magmaw-3eadfc6b0e-canary110.hz84YE`
12. `trinity-magmaw-ae9761adb3-canary116.n0L5tX`

Intervening runs that did not reach Magmaw are `not_exercised`; they do not
reset the counter. Canary109 directly records infection on both fixed baiters
and at least four other players, followed by Infectious Vomit into the raid.

## Canary116 missing boundary

Canary116 narrowed the first broken edge further. At capture sequences 306,
310, and 314, mage 30006 proposed three different local escape destinations:
`(-348.981, -35.6553)`, `(-348.057, -33.065)`, then
`(-361.603, -35.1834)`. The selected parasite also changed between entries
42321 and 41806 while native movement was retrying. Hunter 30009 retained its
lane destination during the same interval and accumulated 2.122, 7.259,
12.387, then 23.661 seconds without progress.

The baiter endpoint-preemption branch in
`BotAdaptiveMagmawParasitePolicy.h` did not pass the per-bot
`MagmawParasiteHazardState` to `BuildMoveAway`. Two adjoining state semantics
were consequently untested: `ObserveNativeProgress` retired the escape when
the original danger GUID disappeared even if another parasite remained
unsafe, and `BuildMoveAway` recomputed coordinates while an intent was active.
The revision-1 fixture supplied no hazard state at this branch and changed a
GUID without also changing position, so it could remain green without
exercising the live failure.

Revision 2 makes a baiter unsafe at its retained endpoint, records one local
escape, changes both parasite GUID and position before native arrival, and
requires identical destination and intent identity on retry. The repair passes
state through the baiter branch, retains it while any living parasite remains
within clearance, and makes the movement builder return the retained
destination. This reviews occurrences 11 and 12; it does not itself close the
live recurrence family.

## Why prior repairs did not hold

- `44871a5146` constrained kite assignment but did not own a transition.
- `62a36fcb5e` removed one override/recomputation path but left other writers.
- `47dd2815cf` added a stable pack identity and lease key, not immutable
  destination state.
- `7a57fa8df2` extracted a policy/stable point but continued to use the generic
  movement lease as state.
- `81ab0b47e8` introduced opposite-lane endpoints, but recalculated the
  opposite side from the baiter's current position on later ticks.
- `f7581b572e` bounded native path retries; it did not change lane ownership.

The apparent fixes moved the same invariant between helpers. The generic lease
can expire while the native path is active, `OppositeLaneEndpoint` can reverse
after the baiter crosses the midpoint, parasite observations can invalidate a
retained destination, and Pillar movement can replace that destination. This
is a missing state boundary, not proof that cyclomatic complexity alone caused
the failure.

## Counterexample the old fixture missed

The existing replay supplied a synthetic retained lease and expected a lane
switch when a parasite approached the old endpoint. It did not execute owner
selection, semantic transition retention, native submission, path progress,
lease expiry, hard-safety preemption, or arrival over multiple ticks. It
therefore passed while live baiters oscillated.

The replacement replay must cover one full sequence:

1. a new mechanic generation assigns only the fixed mage and hunter;
2. each baiter commits a transition identity and destination;
3. parasite GUIDs and positions change before and after midpoint crossing;
4. the generic movement lease expires while the native path remains active;
5. identity, direction, and destination remain unchanged;
6. a typed lethal hazard preempts, then the same transition resumes;
7. rejected native submission retries the same identity and destination;
8. native arrival retires the transition;
9. only a later mechanic generation may select the opposite lane;
10. attempt/wipe reset clears the state; and
11. the entire traversed corridor, not only its endpoints, clears the support
    stack and boss geometry.

Changing or deleting an earlier expected behavior requires this review to be
updated with the old case and the reason it was invalid. A helper-level or
source-shape test cannot admit the next canary.

## Smallest repair boundary

Add one typed, encounter-scoped Magmaw lane-transition state with baiter
assignment, attempt/mechanic generation, transition identity, direction,
destination, and committed/arrived state. Keep it separate from the generic
short movement lease. Route Pillar bait and parasite avoidance through this
single owner; non-baiters retain only local safety movement. Use fixed
max-range lane geometry or deterministic waypoints whose full corridor passes
the clearance predicate.

The implementation unit may touch only that typed state, Magmaw strategy and
movement arbitration needed to consume it, and the focused replay. It may not
tune class rotations, damage, encounter spells, provisioning, or live shard
control. A coordinator-owned exact build and one matched completion-watchdog
canary follow only after the replay passes.

## Evidence classification

Direct evidence is the ten retained run identities, Canary109 infection/vomit
events, bait coordinates, and repeated native movement receipts. The corridor
clearance calculation and missing-state diagnosis are inferences from those
events plus the source paths. The compact Canary109 handoff and its artifact
hashes remain the source boundary; the failed raw run is not promotion
evidence.
