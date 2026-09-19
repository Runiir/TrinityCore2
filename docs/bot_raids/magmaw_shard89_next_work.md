# Continue from the best observed canary

Shard89 cleared with no party deaths during the boss and retained 241,249.360 raid
DPS across 116.863 seconds. Composition: 1 Blood tank, 3 healers, 6 DPS. The
denominator is first-to-last originated damage, including pets and excluding
friendly/mirrored damage. Native pull/death boundary equivalence is not proved
by this compact aggregate. Treat this as the best observed clear, not a certified
performance baseline: run identity was incomplete and native script changes
remain under review.

September19 continuation: independent native review rejected this run as a legal
performance baseline. Its Mushroom hook enlarged spell78777 from the native6yd
radius to8yd, ignored vertical separation and appended otherwise rejected targets.
The correction removes that mutation and keeps diagnostics. Focused tests pass;
clean build and live validation are pending. Historical241k remains an observed
clear only. No recovery or WCL-parity claim follows from it.

Evidence:

- Original report and hosted review: `artifacts/cata_raid_program/magmaw_jev_canary_compact_20260919.tar.gz.dvc`, member directory `magmaw-normal-shard-89-balance-ground-radius-repeat-20260919`.
- Prior exact local/hosted replay: `artifacts/cata_raid_program/magmaw_jev_locality_replay_20260919.tar.gz.dvc`.
- Corrected review, local predictions, all-bot table and peer components: `artifacts/cata_raid_program/magmaw_local_jev_shadow_20260919.dvc`.

The latest local replay returned six answers in 0.62–1.30s each. All six chose
`encounter_assignment`; five contradict the recorded assignment state. Balance's
remaining suggestion is advisory and needs native confirmation. All six records
are quarantined. Hosted Jev previously suggested more evidence for Fire A and
cadence work for Affliction/Elemental. Neither model proves those causes.

## Ranked next work

1. **DPS-026, Blood Heart Strike.** 12,567.827 native DPS versus 26,152 WCL
   context, with different gear, phase coverage and tank pressure. No landed
   Heart Strike. Spell55050 has46 area-semantics and47 protected-splash
   rejections. This is an existing unresolved policy edge, not a new coefficient
   diagnosis. First establish the actual protected target and native cleave reach.
2. **DPS-057, Fire burst differences.** Fire30006:31,880.493 DPS;
   Fire30007:44,554.855. Combustion83853 accounts for567,468 damage difference;
   Pyroblast92315 for545,509. Together these are75.1% of the peer difference.
   Fireball differs by only146,528 damage. Join Hot Streak availability/use,
   Ignite/Combustion snapshot, body/head targets and mandatory bait windows.
   Do not interpret6vs36 Pyroblast landed effects as completed casts.
3. **Remaining roster.** Balance37,432; Affliction36,681; Survival35,966;
   Elemental36,295 DPS. Balance add/pincer work is relevant; Affliction and
   Elemental cadence remain leads, not proven causes. Survival has no same-spec
   WCL reference in the retained table. Blood/healer contributions and survival
   stay in the review. WCL values are context, never a40k-per-bot acceptance rule.

## Next Luna work unit

Mode: **bounded diagnosis**, DPS-026. Work directly, without another worker or
live-server control. Code review source: `68621071cc` on the canary branch; do
not assume that reference alone proves shard89's binary identity. Preserve the
ongoing checkout. Read only the three native callers below, their authority
helper and the retained55050 rejection rows in `dps_review.json`.

- `src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp`
- `src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp`
- `src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp`
- `src/server/game/Bots/BotRaidAreaAuthority.h`

Hypothesis: a binary area restriction or broad protected-target neighborhood
rejects a cleave whose actual native secondary targets could all be legal.
Competing explanation: the spell really could hit an inactive/protected target.
Existing evidence proves rejection, not which secondary target made it necessary.

Return the precise predicate, target/phase facts required to distinguish these
cases, and the smallest production-path counterexample. If retained evidence
cannot identify the target, request that exact observation in the next matched
watchdog capture. Do not invent a coefficient or implementation scope.

Forbidden: global AoE/target-protection bypass, class/boss damage changes,
encounter-specific radius/Z exceptions, GM movement, altered scoring, changing
the frozen roster, or importing the entire experimental branch.

When the predicate is proved, the coordinator hands one implementation worker
the exact owned files and regression fixture. Exercise resolver and native
submission: legal cleave must submit and land, a genuinely protected secondary
target must remain excluded, and mitigation/threat must continue. Independent
review precedes the single build/watchdog canary. Compare all actors, deaths,
phase coverage and exact damage accounting. A boss death alone is insufficient.

Offline diagnostic regression command:

```sh
pixi run python -m pytest tests/test_magmaw_jev_trace_analyzer.py tests/test_magmaw_timeline_comparator.py tests/test_combat_log_analysis.py tests/test_jev_shadow.py -q
```

This command checks analysis/capture, not Heart Strike behavior. Native
implementation must add and name its actual production-path fixture.
