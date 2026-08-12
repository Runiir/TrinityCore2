# Privileged raid build service contract

This protocol is an optional external hardening path. On 2026-08-12 the user explicitly
authorized the `explicit_trusted_local_operator` model for build receipts produced and
verified by local user `runiir`; policy v8 therefore does not require this service for
Phase 1. All non-build gameplay, fidelity, live-evidence, DVC, and review gates remain
unchanged and fail closed.

If enabled again, the service supplies an authority boundary that the capture user
cannot rewrite. It may be a separate OS service account, a remote builder, or a
hardware-backed signer, provided all of these properties hold:

- only the service can read or use the Ed25519 private key;
- only the service can append to the authoritative ledger;
- the repository/capture user can submit requests and read receipts, attestations,
  the public key, and ledger inclusion results, but cannot alter authoritative state;
- the service executes the admitted configure/build rather than signing a caller's
  unsupported success claim;
- the signed receipt covers source, policy, command, configure lineage, complete
  CMake cache, generated build graph, positive environment, declared toolchain, and
  resulting worldserver ELF identities.

The tracked optional service contract is
`experiments/configs/cata_raid_privileged_build_service_v1.json`. It deliberately
remains `unprovisioned_external_authority_required` until an administrator supplies:

1. a stable `service_id` and `key_id`;
2. an Ed25519 public key and its SHA-256 identity;
3. the request submission endpoint;
4. the append-only ledger verification endpoint and initial accepted sequence;
5. read-only access to the canonical coordinator receipts and signed attestations.

Provisioning is a reviewed policy change, not a runtime option. The build policy pins
the exact service-config SHA-256, service/protocol/key identities, public-key hashes,
and HTTPS endpoints. Canonical capture does not accept a service-config override.

The service signs the canonical JSON payload reconstructed by
`tools.raid_program.privileged_build_attestation.signed_payload`. The envelope contains
`schema_version`, `service_id`, `key_id`, positive `ledger_sequence`, stable
`ledger_record_id`, `signed_at_utc`, the exact reconstructed `payload`, its SHA-256,
and a base64 Ed25519 signature. It also carries `attestation_sha256`, calculated over
the full envelope except that field.

The verifier then fetches the record from the policy-pinned HTTPS ledger endpoint.
The independently signed, fresh record assertion must report unique, non-revoked
inclusion and bind
the ledger head/sequence, record ID, attestation-record hash, attestation payload hash,
and receipt hash. Its signing key and public-key hash must be distinct from the build
signer and are separately pinned by policy. This v1 protocol trusts the separately
privileged ledger service's append-only operation; it does not claim a Merkle inclusion
or cross-checkpoint consistency proof.

Verification is fail-closed:

```bash
pixi run raid-build-attestation-verify \
  --attestation /path/from/service/attestation.json \
  --receipt /read-only/service/receipt.json \
  --policy experiments/configs/cata_raid_build_resource_policy_degraded_v8.json
```

Standalone `raid-build verify` proves only local receipt semantics when the policy
requires privileged attestation; its JSON explicitly reports `gate_bearing: false`.
Canonical Phase 1 capture requires `--build-attestation` only when the active policy
sets `privileged_receipt_signature_required=true`. Under the authorized local model,
the coordinator receipt must instead bind UID/eUID `1000`, username `runiir`, a success
classification, zero exit status, and every existing source/configuration/graph/tool/
command/output invariant. Test and failed receipts are never gate-bearing.
Ephemeral test keys are allowed only when both the verifier flag and the underlying
coordinator receipt are explicitly test mode. Such verification reports
`gate_bearing: false` and never satisfies a production gate.
