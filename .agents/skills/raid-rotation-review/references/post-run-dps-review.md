# Dedicated post-run DPS review

Own the DPS diagnosis for one closed run. Read the report and existing combat
aggregates first; request only missing trace/reference payloads from the
coordinator. Work directly, without nested workers. Do not change gameplay,
launch a server, generate new simulator references, or publish/evict evidence.

Bind the review to the report hash, source/binary, server epoch, attempt, cohort,
instance, route node/generation, roster, and promoted reference catalog. State
which comparisons are admitted and which lack setup/stat parity. A valid boss
clear remains valid even when the DPS review identifies inefficiency.

Resolve gear through the actual provisioning pipeline, including explicit bot
equipment and WoWSims overlays. Use the run's native `gear_manifest` and bound
inventory readback for comparison. A class name or base profile is not evidence
of equipped items. Item-level limits and name filters do not prove player
obtainability; retain the approved acquisition/preset source. Correct a prior
misattribution with attributable supplemental analysis, preserving the original.

Start with the complete roster, including every tank, healer, DPS, and owned
pet. Record actual and requested tank/healer/DPS counts; never silently compare
a 2/3/5 run with a 2/2/6 target or change the frozen roster to fit a benchmark.
Report DPS and HPS for every bot. Review tanks' offensive uptime alongside
threat/defensives and healers' damage opportunities alongside healing, mana,
and preventable deaths. A low healer DPS number alone is not a defect.

In the bot timeline, `activity.active_seconds` counts absolute one-second
buckets with effective healing or originated hostile damage, including pet/DoT
tails. It is not offensive or cast/GCD uptime. Use
`fresh_attack_active_seconds` for buckets with owner non-pet direct hostile
impacts, and the separately named submission/outage fields for their stated
boundaries. Neither bucket count measures time spent casting. Legacy captures
mislabel the enclosing `metric_scope`; preserve their numbers and correct the
interpretation instead of treating a healing-only actor as actively attacking.

For every DPS actor and spec, report available evidence for:

- Originated damage and DPS using the same encounter denominator for every
  actor; distinguish boss, required adds, incidental targets, and pet damage.
- Landed events and damage per event by spell; call them cast counts only when
  native cast/submission evidence actually supports that measurement.
- Eligible action cadence, idle/backoff episodes, target switches, range/LOS,
  movement, mechanic assignments, and opportunities to cast while moving.
- Cooldowns, profession/racial actions, food/flask/potion outcomes, resource
  gates, and pet cadence/target uptime when captured.
- Exact promoted WoWSims APL, result action mix/cadence, pet contribution,
  cooldowns, resources, and effective-stat/setup comparison. Do not stop at
  quoting a simulator DPS total. Record missing inputs per actor rather than
  omitting the actor. The promoted catalog supersedes embedded DPS figures.
- Warcraft Logs comparison to identified Cataclysm kills. Retain report URL/code,
  fight and actor IDs, date/patch, difficulty, raid size/composition, gear tier,
  kill duration, buffs, target filters, head/vulnerability phases, and the DPS
  denominator. Use several comparable strong kills when available, avoiding
  a single padded/outlier parse. Normalize observed spell mix, casts per minute,
  active casting, pets, cooldown/potion timings and target damage into the
  compact review; retain observations separately from inferred recommendations.
  Check retained report URLs and previous research/browser history before
  declaring an access blocker. Direct report pages may work when rankings or
  API access do not. If login/API/report access is unavailable, record the attempted source and
  exact blocker. Do not call the Warcraft Logs comparison complete or invent
  a benchmark from snippets. Continue comparisons supported by local evidence.

Party damage may include tanks, pets, adds, encounter-attributed effects and
redirected damage. Use the existing originated-damage accounting rather than
summing raw mirrored events. Use complete fight elapsed time for comparisons
with Warcraft Logs when its
DPS uses that denominator. Preserve the existing scored/active-second number
as a separately named metric; never compare it directly to elapsed-time DPS.
State whether transfers between linked targets are deduplicated and whether
pets and adds are included. A spell's moving-event fraction is not the actor's
movement uptime; a DOT ticking while
moving does not prove a lost hard cast. Boss vulnerability phases also prevent
direct damage-per-event comparison with an unmodified dummy reference.

For missing actions, inspect full diagnose snapshots before declaring candidate
telemetry absent. `snapshot.policy.valid_action_mask_json.actions` retains each
spell's eligibility, rejection reason and score; `chosen_action_json` retains the
resolver choice. Join them with `snapshot.combat_attempt`, native outcomes and
matching attempt/route/decision timestamps. Check evaluation purpose and
selector filters: passive range previews in older builds can overwrite the
execution mask with a different, never-submitted choice. A melee fallback can overwrite the
failed spell in the compact attempt summary. Compact trace rows alone do not
establish that a spell was never selected or that a new observer is needed.

Trace the largest suspicious loss through observation, eligible candidates,
selected candidate, resource claims, native submission, and landed outcome.
Distinguish established defects, plausible leads, and unavailable evidence.
Give each actor an explicit finding: proven defect, plausible loss requiring
one observation, no defect found in inspected evidence, or not yet reviewed.
Rank improvements across the roster before selecting one bounded implementation;
"one repair per iteration" does not mean "review only one bot."
Do not estimate recoverable DPS by subtracting an unmatched simulator total.

Return one compact `dps_review.json` and a short readable summary alongside the
run. Reuse existing rotation-review output for exact spec comparisons. Include
the per-actor findings, reference/measurement limitations, and the highest-value
bounded next work unit with its counterexample, production callers, owned files,
forbidden changes, focused test, and next-run acceptance condition.

Close the review once the all-bot table, repaired-edge verdict, available
reference comparisons and one bounded next task are recorded. Reuse retained
normalized references and existing report aggregates. Do not delay a proven
canary's publication to build a bespoke analyzer, expand a dossier or solve
the next repair. If causality is unresolved, return a diagnosis task with the
exact trace and missing join; do not invent implementation files or a fix.
The coordinator may package a compact reviewer response into the run's evidence.

Route cadence/priority/resource/pet-policy defects to role implementation;
shared arbitration/movement/target-ownership defects to runtime implementation;
matching setup/stats/cadence with incorrect event damage to native class
mechanics. Missing parity data means request that observation, not guess a
coefficient. Exact dummy calibration lasts 300 seconds; raid runs remain
completion-watchdog driven.

Keep three conclusions separate: encounter clear, acceptance of this repair,
and overall roster performance. A kill or one improved actor does not establish
that all bots meet their performance targets. State which actors and external
comparisons remain unresolved, and derive any aggregate target from the actual
composition and matched evidence rather than installing an arbitrary DPS gate.

On the next run, compare the repaired edge, per-actor output and clear/survival
outcomes against the prior review. Admit only the improvement actually observed.
Choose one next actionable loss; do not reopen repaired lifecycle failures or
require a new documentation/authorization chain for ordinary tuning iterations.
