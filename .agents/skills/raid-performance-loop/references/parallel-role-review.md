# Parallel class and role review

Use this mode for a closed run with several underperforming actors. It is not
a requirement to launch every supported spec on every narrow experiment.

The coordinator supplies one shared context containing clean source and run
identity, exact actor assignments, report/trace paths, frozen loadouts, current
reference lookup, actual Warcraft Logs comparison, previous accepted repairs,
and known telemetry limitations. Give each worker explicit actors and separate
output files using exact absolute paths, not placeholders such as `OUT`.
Reuse available evidence; do not regenerate simulator catalogs.

Use Sol high for causal diagnosis. Group duplicate DPS specs under one reviewer;
assign tank and healer review coverage too. Split a role group further when its
distinct class failures warrant independent work. A worker applies one shared
specialist skill and reads only its relevant class notes.

Each reviewer returns a compact result:

- DPS/HPS and role outcomes for every owned actor, with reference differences.
- Earliest supported mismatch, including timestamp, target, candidate/rejection
  and native outcome; distinguish missing evidence from a diagnosed defect.
- Expected impact and one bounded repair packet with exact files, forbidden
  changes, meaningful fixture, commands and acceptance conditions.
- A short reusable class note for verified semantics or recurring mistakes.
  Keep encounter tactics, pinned artifact paths and run-specific numbers in
  the run evidence; obtain current values from the promoted catalog.

Join all findings before assigning implementation. Give shared movement,
targeting, execution or measurement failures one owner; class workers must not
compensate for the same shared defect. Merge repeated hypotheses. Preserve
unresolved actors rather than declaring overall success after one local fix.

Use Luna max for approved narrow implementations with disjoint ownership.
Batch independent, trace-backed fixes that can each be checked in the same
run. Hold conflicting or causally dependent changes for the next batch.
After workers finish, inspect the combined diff, run affected fixtures once,
obtain independent review, verify assets, then build once and run one bounded
canary. A worker finishing is not a reason to build immediately.
Worker results distinguish the base revision from uncommitted implementation;
only the coordinator's final commit identifies the combined build source.

Keep the shared context and per-owner findings with that run's evidence. The
overall reviewer joins attribution and repair acceptance before DVC publication
and exact payload eviction. No extra status ledger or custom agent framework
is needed for this mode.
