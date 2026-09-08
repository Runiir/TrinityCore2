# Dedicated post-run DPS review

Own the DPS diagnosis for one closed run. Read the report and existing combat
aggregates first; request only missing trace/reference payloads from the
coordinator. Work directly, without nested workers. Do not change gameplay,
launch a server, generate new simulator references, or publish/evict evidence.

Bind the review to the report hash, source/binary, server epoch, attempt, cohort,
instance, route node/generation, roster, and promoted reference catalog. State
which comparisons are admitted and which lack setup/stat parity. A valid boss
clear remains valid even when the DPS review identifies inefficiency.

For each DPS actor and spec, report available evidence for:

- Originated damage and DPS using the same encounter denominator for every
  actor; distinguish boss, required adds, incidental targets, and pet damage.
- Landed events and damage per event by spell; call them cast counts only when
  native cast/submission evidence actually supports that measurement.
- Eligible action cadence, idle/backoff episodes, target switches, range/LOS,
  movement, mechanic assignments, and opportunities to cast while moving.
- Cooldowns, profession/racial actions, food/flask/potion outcomes, resource
  gates, and pet cadence/target uptime when captured.
- Exact WoWSims action structure and effective-stat/setup comparison where
  available. The promoted catalog supersedes old embedded DPS figures.

Party damage may include tanks, pets, adds, encounter-attributed effects and
redirected damage. Use the existing originated-damage accounting rather than
summing raw mirrored events. State the denominator and distinguish total
elapsed encounter time from seconds containing originated damage. A spell's
moving-event fraction is not the actor's movement uptime; a DOT ticking while
moving does not prove a lost hard cast. Boss vulnerability phases also prevent
direct damage-per-event comparison with an unmodified dummy reference.

Trace the largest suspicious loss through observation, eligible candidates,
selected candidate, resource claims, native submission, and landed outcome.
Distinguish established defects, plausible leads, and unavailable evidence.
Do not estimate recoverable DPS by subtracting an unmatched simulator total.

Return one compact `dps_review.json` and a short readable summary alongside the
run. Reuse existing rotation-review output for exact spec comparisons. Include
the per-actor findings, reference/measurement limitations, and the highest-value
bounded next work unit with its counterexample, production callers, owned files,
forbidden changes, focused test, and next-run acceptance condition.

Route cadence/priority/resource/pet-policy defects to role implementation;
shared arbitration/movement/target-ownership defects to runtime implementation;
matching setup/stats/cadence with incorrect event damage to native class
mechanics. Missing parity data means request that observation, not guess a
coefficient. Exact dummy calibration lasts 300 seconds; raid runs remain
completion-watchdog driven.

On the next run, compare the repaired edge, per-actor output and clear/survival
outcomes against the prior review. Admit only the improvement actually observed.
Choose one next actionable loss; do not reopen repaired lifecycle failures or
require a new documentation/authorization chain for ordinary tuning iterations.
