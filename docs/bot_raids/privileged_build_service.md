# Privileged raid build service contract

Phase 1 gate-bearing configure/build receipts require an authority boundary that the
capture user cannot rewrite. The service is external to this repository. It may be a
separate OS service account, a remote builder, or a hardware-backed signer, provided
all of these properties hold:

- only the service can read or use the Ed25519 private key;
- only the service can append to the authoritative ledger;
- the repository/capture user can submit requests and read receipts, attestations,
  the public key, and ledger inclusion results, but cannot alter authoritative state;
- the service executes the admitted configure/build rather than signing a caller's
  unsupported success claim;
- the signed receipt covers source, policy, command, configure lineage, complete
  CMake cache, generated build graph, positive environment, declared toolchain, and
  resulting worldserver ELF identities.

The tracked service contract is
`experiments/configs/cata_raid_privileged_build_service_v1.json`. It deliberately
remains `unprovisioned_external_authority_required` until an administrator supplies:

1. a stable `service_id` and `key_id`;
2. an Ed25519 public key and its SHA-256 identity;
3. the request submission endpoint;
4. the append-only ledger verification endpoint and initial accepted sequence;
5. read-only access to the canonical coordinator receipts and signed attestations.

The service signs the canonical JSON payload reconstructed by
`tools.raid_program.privileged_build_attestation.signed_payload`. The envelope contains
`schema_version`, `service_id`, `key_id`, positive `ledger_sequence`, stable
`ledger_record_id`, `signed_at_utc`, the exact reconstructed `payload`, its SHA-256,
and a base64 Ed25519 signature. It also carries `attestation_sha256`, calculated over
the full envelope except that field.

Verification is fail-closed:

```bash
pixi run raid-build-attestation-verify \
  --attestation /path/from/service/attestation.json \
  --receipt /read-only/service/receipt.json \
  --policy experiments/configs/cata_raid_build_resource_policy_degraded_v8.json \
  --service-config experiments/configs/cata_raid_privileged_build_service_v1.json
```

Canonical Phase 1 capture additionally requires `--build-attestation`; the capture
cannot begin while the tracked service state is unprovisioned, the public key identity
differs, local receipt reconstruction fails, or the external signature is invalid.
Ephemeral test keys are allowed only under the coordinator's explicit test mode and
never satisfy a production gate.
