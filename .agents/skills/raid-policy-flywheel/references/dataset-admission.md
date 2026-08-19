# Dataset admission contract

One training example represents a decision boundary, not an arbitrary log line.

## Required batch identity

- Git commit, dirty-state policy, build receipt, binary hash, and config hash.
- Run, shard, instance, boss, mode, route, roster, slot, actor GUID, and attempt identifiers.
- Capture schema/version, manifest, start/stop reason, terminal receipt, and DVC object identity.
- Script-readiness and strategy-contract revisions relevant to the encounter.
- WoWSims request/source/result identities when a simulator-derived feature or label is present.

## Required decision fields

- Monotonic decision timestamp or tick and a stable decision identifier.
- Observation features available at decision time only.
- Full candidate action list with action identifiers and feature values.
- Deterministic legality, safety, authority, resource, movement, and mechanic masks.
- Priority/relevance before learned scoring and final selected action.
- Native submission identity and immediate acceptance/rejection reason.
- Completion, cancel, interrupt, timeout, or replacement event.
- Landed spell/aura/damage/heal/threat/movement outcome where applicable.
- Phase, mechanic, target, role, and encounter outcome labels.

Do not backfill features from future events into the observation. Derived labels must state their time window and derivation version.

## Admission reasons

Admit only when the complete chain is attributable and the behavior is client-valid. A hard negative is valid only when the attempted behavior was legitimate and failed for a gameplay reason the policy should learn.

Quarantine reason codes include:

- `identity_missing_or_mismatch`
- `schema_unknown_or_malformed`
- `capture_incomplete_or_truncated`
- `script_fidelity_blocked`
- `route_or_roster_identity_stale`
- `synthetic_or_assisted_behavior`
- `infrastructure_or_server_fault`
- `decision_outcome_join_missing`
- `wowsims_reference_stale`
- `duplicate_or_cross_split_leakage`

Quarantine is not deletion. Preserve the compact manifest and reason so a repaired pipeline can reconsider the batch.

## Split and promotion invariants

- Split before tuning and group correlated rows by run/attempt/encounter as needed.
- Keep a frozen holdout that was never used to choose features, thresholds, or checkpoints.
- Compare against the exact deterministic baseline on the same observations.
- Deterministic masks always win over learned ranking.
- Shadow evaluation grants no action authority.
- Promotion requires no unexplained regression for any required role or encounter slice.
