# Magmaw optimization consistency audit

Read-only gameplay/workflow audit at `ed678babbd`, 2026-09-10. No new server
run, gameplay change, database mutation, or simulator reference generation.

The measured performance decline is real. The workflow preserves evidence and
accepts individual repairs, but has no enforced raid-performance comparison
before continuing. Existing targeting and movement contracts can collectively
leave a living DPS bot unable to attack or reposition. A quick kill can end
before that failure becomes costly.

## Comparable results

These rates use originated hostile party damage divided by first hostile event
to native boss death. They exclude friendly damage and mirrored spell 79010
callbacks, include owned pets and parasites, and retain the same 2-tank,
3-healer, 5-DPS composition. They are encounter results, not controlled estimates
of a patch's effect. Complete setup equivalence and repeat-run variance were
not newly established by this audit.

| Source | Fight seconds | Hostile damage | Exact party DPS |
| --- | ---: | ---: | ---: |
| `4b24d7242f` | 140.359 | 28,193,124 | 200,864.383 |
| `a152fb20ef` | 186.544 | 29,303,759 | 157,087.652 |
| `ff34bce50a` | 212.621 | 29,179,044 | 137,235.005 |
| `41266a508c` | 151.420 | 28,270,614 | 186,703.302 |
| `6882d0c204` | 209.211 | 28,935,523 | 138,307.847 |

Latest is 31.144% below the 200k kill and 25.921% below its immediate predecessor.
The latest review also reports 137,135.180 on 211 damage-bearing calendar seconds.
That is a different denominator. The user's approximate 136k number was not
located as an exact metric. Changing denominators does not explain this decline.

Every DPS actor loses elapsed-time throughput against the 200k kill:

| Actor | 4b24 exact DPS | 6882 exact DPS | Change |
| --- | ---: | ---: | ---: |
| Fire bait 30006 | 33,821.5 | 20,322.7 | -39.91% |
| Fire hook 30007 | 30,986.4 | 20,284.6 | -34.54% |
| Affliction 30008 | 34,206.6 | 24,365.4 | -28.77% |
| Marksmanship 30009 | 29,700.2 | 20,997.7 | -29.30% |
| Elemental 30010 | 25,829.1 | 18,070.2 | -30.04% |

These losses do not establish five independent rotation regressions. The shared
longer fight denominator and changed phase/target opportunities affect them all.

The 200k kill ended 31.728 seconds into the first exposed-head window. It never
exercised a return to a living covered body. The latest kill needed a second
exposure. Relative to 41266, boss-entry damage differs by only one point; the
additional 664,909 total damage is explained within one point by parasites.
Much of the rate loss is time spent producing the required damage, not missing
damage transport. Phase duration is partly an outcome of bot performance and
must not be used to dismiss the decline.

## Proven runtime mismatch

The user's manual spectator run on `21c640739d` is a separate unresolved
target-return occurrence (DPS-023), not disproved by later valid target samples.
Its retained diagnosis reports zero ordinary direct attacks from the five DPS
on the body during a 57.769-second inferred head-hide interval. Ordinary attacks
resume on parasites after 16.648s for Hunter, 29.217s for Affliction, 29.693s for
Elemental and 32.395s for Fire hook. Fire bait has no ordinary direct body/add
event before the second head. Existing dots, pets and effects can keep damage
totals increasing while fresh body attacks have stopped.

The decisive first-hide decisions had been evicted from the 128-row per-actor
trace before the post-kill request. This prevents reconstruction of the exact
selector branch. Later target-return instrumentation records body/head validity,
proposed target and before/after binding, but as a latest snapshot, not a durable
every-transition event history. A later successful return is run-specific evidence,
not acceptance of a fix for the manual occurrence. The source also has a transient
targetless plan when both body/head exist only in Interactables; retained evidence
does not show that this explains the prolonged outage.

Evidence: `manual-client-20260909/restart/dps-review/manual-dps-diagnosis.md`
and `magmaw-head-return-target-diagnosis.md` under the retained validation root.
The manual diagnosis's hide time is inferred from damage, not a typed phase event.

The actual chain is:

1. `BotAdaptiveMagmawStrategySupport.h::ObserveMagmawActors` chooses the nearest
   living parasite by 2D distance. `BindParasiteDamageTargets` admits optional
   ranged support by spec, role, head absence and distance. Neither supplies
   actor-target native LOS or executable-action eligibility.
2. `SelectDamageTarget` can choose that support target over the boss.
3. `BotWorldPopulationMgrUpdateBotKernelFallback.cpp` checks the selected target's
   range/LOS. `MagmawParasiteCombatContract::ShouldDeferCombatRange` defers offense
   when support is selected and maximum range or LOS fails. It returns
   `magmaw_hazard_movement_retry` even if no hazard movement is progressing.
4. `BotProfileCombatRangeCandidate.h::Evaluate` admits ordinary movement only
   for positive minimum-range violations. LOS/max-range failures can return
   `profile_min_range_satisfied` without invoking movement.
5. `BotWorldPopulationMgrCombatMovement.cpp::MoveBotToProfileRange` explicitly
   forbids support-target LOS repair, forced repositioning and max-range chasing.

Each restriction can be locally intentional; their combination leaves neither
offense nor corrective movement available. The safety restriction should remain.
Optional target admission must establish an actual attack opportunity instead.
This defect predates the last patch: support selection/containment appears in
`bdf57a2fa3`. It is not evidence that reverting 6882 removes the underlying bug.

The closed 6882 diagnosis binds this chain to Fire hook 30007 and Hunter 30009.
Fire deals only 244 hostile damage in the final 57.689 seconds; 38 of 46 late
diagnoses report the retry. Hunter has 23 deduplicated Serpent Sting LOS failures.
The Fire displayed spell mask belongs to an earlier head target, so it cannot
explain current parasite eligibility. The exact Fire range-versus-LOS disjunction,
obstruction geometry and a legal alternative target are not retained. Do not
claim all 57.689 seconds have one proven cause or assign a recovered DPS value.

Other retained losses remain real: Elemental Lightning Bolt's configured 12-yard
minimum also gates cast legality; Heart Strike and Shadowflame encounter the
shared area restriction; moving Scorch can survive the interruption boundary
yet still fail at native completion. These require separate bounded repairs.

## Why the optimization workflow does not reliably improve results

- `capture_finalization.py::development_run_claim` proves native boss death and
  identity. Its caller's success combines capture/cleanup/integrity conditions
  and that death claim. It takes no prior DPS baseline or per-actor regression
  result. This is appropriate for capture success but insufficient to promote
  an optimization.
- `cata_raid_active_work_unit_v1.json::acceptance_conditions` requires a causal
  fixture, independent review and one native validation. It has no explicit
  comparison against a matched performance baseline. Reviews record declines,
  but continuation does not require their attribution or resolution.
- The latest Scorch specialist rejects full Hazard-path finish/landing acceptance.
  The current status correctly narrows acceptance to preserving the cast through
  early movement interruption. That narrower result is useful, but is not the
  original end-to-end benefit. Acceptance scope must remain machine-distinct.
- Existing parasite policy fixtures assert support-target deferral for LOS and
  max-range failure. They test containment without proving eventual legal offense
  through selection, arbitration and the native movement caller together.
- `BotWorldPopulationMgrSemantic.cpp` publishes native finish success but marks
  cast-instance correlation unavailable and lacks terminal `SpellCastResult`.
  Repeated investigation therefore reaches an observation limit after submission.
- Fast first-head kills leave later transitions unexercised. One clear does not
  establish stable phase behavior or the repeatability of its DPS.

## Recommended next work

First repair ENC-003 optional-support admission through native actor-target
LOS/range facts. Test a blocked nearest parasite, a genuinely legal alternative,
an eligible boss fallback, and no legal alternative. Preserve personal threats,
fixed bait obligations and hazard ownership. Exercise the production caller,
not only the pure selector.

Add a separate performance decision to the existing post-run review and active
work-unit progression. Keep clear, requested repair outcome and performance
acceptance separate. Compare exact elapsed DPS, per-actor originated damage,
boss/add allocation, idle/rejection intervals, survival and phase coverage with
an explicitly identified baseline. A material unexplained loss should block a
performance-improvement claim and route diagnosis. Do not erase valid clears or
automatically revert survival fixes based on an aggregate number.

For causal patch attribution, use matched setup and sufficient phase coverage;
if retained evidence cannot distinguish patch effects from encounter variation,
use a bounded paired validation under the completion watchdog. Do not install
200k as an arbitrary universal threshold or tune spell coefficients to recover it.

## Verification and evidence

Fourteen focused tests passed with:

`pixi run python -m pytest -q tests/test_magmaw_support_cast_range.py tests/test_magmaw_tank_swap_contract.py tests/test_bot_world_population_mgr_movement_module.py`

This confirms those existing contracts, not absent integration coverage or a fix.
The retained `dps-review/dps_review.{md,json}` for 4b24, 41266 and 6882 each
matched its publication manifest SHA-256. No large payload hydration was needed.
Their immutable archive pointers are under `artifacts/cata_raid_program/` as
`magmaw_development_<source>_20260908.tar.gz.dvc`; member directories are
`magmaw-development-<source>/dps-review/`. The latest
`late-dps-6882-shared-diagnosis.md` and `fire-pair-performance.md` supply the causal
and acceptance limits above. Intermediate run values are also retained in
`docs/bot_raids/shared_worldserver_workflow_20260907.md` at commit 6882d0c204.

This audit is supplemental analysis. Original accepted reports remain unchanged.
