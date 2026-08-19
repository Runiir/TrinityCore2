# Exact reference gate

Advance only in this order:

1. `catalog_current`: all 16 frozen DPS specs, exact fixture hash, no missing
   request field, and the intended provider revision.
2. `build_current`: clean source revision, reproducible CLI/validator binaries,
   successful build receipt, and exact binary hashes.
3. `generated_candidate`: native request accepted by protobuf validation;
   2,000 iterations; exact 300-second duration; no simulator error or forbidden
   external state manufacture; `ComputeStats.finalStats` normalized into the
   receipt; and a bound timestamp-zero debug pet-stat record for every required
   permanent pet.
4. `published`: immutable bundle added and pushed through DVC; pointer and remote
   object verified.
5. `reconstructed`: fresh checkout, targeted DVC hydration, source rebuild,
   request validation, and result re-execution reproduce the recorded identity.
6. `promoted`: all 16 entries bind the same request catalog and DVC bundle.

Fail closed on a missing receipt, mixed catalog hash, changed DVC directory
digest, incomplete cohort, source/binary mismatch, or unclassified simulator
option. Also fail closed for tuning when effective owner stats are absent or a
required pet lacks a debug stat reference. Keep stale numeric values visible
only as `informational_only`.

Hash labels are part of identity. Never compare a request-catalog canonical
JSON SHA-256 with its file SHA-256, a target-catalog SHA-256, or a receipt
SHA-256. Preserve the exact field name in every handoff.

Every promoted result names its reference class. A `self_provided_baseline`
answers: “What does the frozen player produce alone, including its own pet,
class effects, professions, flask, food, pre-pot, and combat potion, with no
external raid buff or pre-applied target debuff?” It is a one-sided minimum:
meeting or exceeding it passes and has no upper rejection bound.

A `controlled_live_parity` result answers: “What does this exact runtime setup
produce in the controlled 300-second single-target fixture?” It is the only
class allowed to supply a like-for-like DPS ratio or exact action comparison.
An `upstream_full_throughput` result preserves the original preset and duration
for capability and UI cross-checks. None of the three claims boss DPS,
movement performance, cleave performance, or raid completion.
