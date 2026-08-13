---
name: raid-evidence-lifecycle
description: Capture, verify, publish, retain, and safely evict TrinityCore raid-experiment evidence. Use for build receipts, provisioning/readback proof, uncapped live capture, telemetry demultiplexing, DVC artifact publication, compact run summaries, disk minimization, or diagnosing whether a raid result is attributable to the exact source, roster, attempt, and boss shard.
---

# Raid Evidence Lifecycle

Keep evidence independently reconstructible while retaining as little local data as possible.

## Establish admission proof

Before live execution, require:

- an exact clean Git commit and tree;
- a successful gate-bearing build receipt whose request, admission, and completion identities are equal and clean;
- the exact binary hash and generated config hash;
- deterministic provisioning verification against the source manifests/DBC inputs;
- fresh DB readback of the exact roster, account linkage, positions, and zero group/instance/corpse/ghost residue.

Do not reuse a binary or receipt for changed native source. Do not accept stored `passed` booleans when the underlying rows cannot be reconstructed.

## Capture an immutable lifecycle

- Retain raw command/output bytes first; normalize afterward.
- Bind every retained JSON row to scenario, cohort, server epoch, attempt, runtime profile/hash, strategy, assignment generation, exact roster hash, action, and capture sequence.
- Classify every row. Unknown, missing, cross-attempt, cross-roster, stale-profile, or forged wrapper identity fails closed.
- Require successful, fresh status, diagnose, and trace envelopes with exactly the frozen roster when the gate needs per-bot decisions.
- Reconstruct milestones from ordered native observations rather than trusting aggregate completion flags.
- In uncapped mode, use channel-freshness and monotonic semantic-progress clocks. Activity churn, casting toggles, or changing victim GUIDs are not progress.

## Separate evidence scopes

- Label synthetic mechanic smokes `synthetic_test_only_not_boss_fidelity`.
- Label predecessor saves as diagnostic assistance and noncertifying.
- Keep boss-shard, boss-script, native recovery, and canonical full-raid claims separate.
- Never promote engagement/wipe evidence into a kill, tactic, or observable-fidelity claim.

## Diagnose before eviction

Preserve enough raw data to answer:

- what exact decision each bot made and why;
- which native script event, target, aura, summon, geometry, or phase was observed;
- whether the trained damage profile executed or was blocked;
- whether stuck/unstuck, CPU, log, or persistence hot paths distorted the run;
- whether cleanup returned bots, leases, groups, and processes to zero.

Make fixes and complete independent review before discarding diagnostic payloads.

## Publish and minimize disk

1. Write a compact tracked summary containing classification, exact identities, hashes, decisive findings, cleanup facts, and the next action.
2. Add the immutable raw/report/log/receipt/readback bundle through DVC.
3. Run the relevant `pixi run dvc status`, `pixi run dvc push`, and targeted cloud/status verification.
4. Verify the tracked `.dvc` pointer, directory metadata, remote availability, file counts, sizes, and hashes.
5. Evict only the exact published workspace outputs and child cache objects. Keep directory metadata needed for reconstruction.
6. Never use broad `dvc gc`, recursive cache deletion, or unresolved globs to save space.
7. Recheck process state, Git cleanliness, DVC status, and disk usage.

Historical evidence may remain remote-only. Hydrate it only when a new diagnosis or audit genuinely needs the bytes, then evict it again after use.

## Gate publication

A run is gate-bearing only when source/build/config/provisioning/runtime/roster/attempt identity is exact, all retained rows are classified and bound, required native outcomes are independently reconstructed, cleanup is observed, remote publication is verified, and no forbidden assistance or unresolved Critical/High finding remains.
