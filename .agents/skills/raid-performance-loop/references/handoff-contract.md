# Specialist handoff contract

Return one compact JSON-compatible record:

```text
work_unit_id
owner_skill
classification            passed | failed | blocked | informational_only
git_commit
input_identities           paths plus SHA-256 or native identity
changed_files
first_broken_edge_before
implemented_hypothesis
validation                 command, result, decisive metrics
gear_identity              simulator and Trinity identities plus comparison
effective_stat_parity      status, tuning_admitted, first_broken_edge
dps_tuning_gate            status, tuning_admitted, first_broken_edge
evidence_paths
dvc_publication            pointer, remote verification, eviction state
remaining_blocker
next_work_unit
```

Rules:

- Record one hypothesis and one first-broken edge.
- For DPS role tuning, require `gear_parity.status=match`,
  `effective_stat_parity.status=match`, and
  `dps_tuning_gate.tuning_admitted=true`. Otherwise
  return the single reference, capture, stat-application, or pet-inheritance
  dependency; do not return another rotation-tuning work unit.
- Use `blocked` only for missing authority or an unavailable external input.
- Use `failed` for a completed work unit whose gate did not pass.
- Missing `scoring_start_stats` in an existing closed runtime report is a
  failed comparison gate, not a blocker. Route exactly one capture-only canary
  to `raid-shard-architecture`; preserve the running worldserver lifecycle.
- Keep simulator, class policy, encounter script, route, native outcome, and
  evidence failures separate.
- Do not pass mutable directories or an unbound “latest” result between owners.
- Copy deterministic `required_*_work_unit` records verbatim; do not narrow an
  atomic cohort to the spec that first exposed its blocker.
- Preserve exact hash field names. Never collapse canonical JSON, file,
  catalog, binary, receipt, or DVC digests into a generic `sha256` comparison.
- The next owner must be able to start from the paths and hashes without
  repeating repository-wide discovery.
- Never return an empty final message. An empty handoff is a missed receipt:
  the coordinator must request status and then interrupt on the second miss.
- Every claimed fix must name the exact test commands it ran with pass/fail
  counts. A fix without executed tests is `failed`, not `passed`.
- Before threading a new field through any gate, prove the field exists in one
  real closed artifact (cite path plus JSON path). If only a derived signal
  exists (for example `buff_basis: self_provided_consumables`), derive from
  that instead of inventing an absent key.
- When a condition class does not apply to the selected reference class, skip
  its predicates entirely; never invert them into absence assertions that can
  false-fail on stray observations.
- When the honest fix requires native changes or a new capture, stop at that
  edge and report it exactly; do not approximate it with a tools-side hack.
