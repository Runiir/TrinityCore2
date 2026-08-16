from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.bot_ml import batch_evidence_lifecycle
from tools.bot_ml import joined_campaign_evidence
from tools.bot_ml.joined_campaign_evidence import (
    JoinedEvidenceError,
    _recursively_verify_accepted_leaves,
    _verify_leaf,
    build_outer_bootstrap,
    materialize_outer_bootstrap,
    reconstruct_outer_from_bootstrap,
    verify_joined_campaign_bootstrap,
    verify_joined_campaign_closure,
    write_outer_bootstrap,
)
from tools.bot_ml.live_validation_session import canonical_sha256


def document(path: str, payload: dict) -> dict:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return {
        "path": path,
        "size": len(text.encode()),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "document": text,
    }


def text_document(path: str, text: str) -> dict:
    return {
        "path": path,
        "size": len(text.encode()),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "document": text,
    }


def self_hashed(payload: dict, key: str) -> dict:
    payload[key] = canonical_sha256(payload)
    return payload


def pointer_rows(prefix: str) -> list[dict]:
    rows = []
    for name in ("raw", "compact"):
        pointer = f"outs:\n- md5: {name}-object.dir\n  size: 10\n  nfiles: 1\n  path: {name}\n"
        rows.append(
            {
                "path": f"{prefix}/{name}.dvc",
                "pointer_sha256": hashlib.sha256(pointer.encode()).hexdigest(),
                "dvc_md5": f"{name}-object.dir",
                "size": 10,
                "nfiles": 1,
                "pointer_document": pointer,
            }
        )
    return rows


def identity_manifest(schema: str, build: dict, *, artifacts: dict | None = None) -> dict:
    runtime = {
        "server_epoch": 1,
        "server_process_id": 2,
        "session_fingerprint": "synthetic-session",
        "max_active_cohorts": 1,
        "profile_generation": 3,
        "profile_content_hash": build["profile_content_hash"],
    }
    projection = {
        key: build[key]
        for key in (
            "git_commit",
            "source_tree_clean",
            "worldserver_binary_sha256",
            "database_snapshot_sha256",
            "database_schema_sha256",
            "profile_content_hash",
        )
    }
    manifest = {
        "schema": schema,
        "component_hashes": {
            "source_identity_sha256": canonical_sha256(
                {"git_commit": build["git_commit"], "source_tree_clean": True}
            ),
            "worldserver_binary_sha256": build["worldserver_binary_sha256"],
            "database_snapshot_sha256": build["database_snapshot_sha256"],
            "database_schema_sha256": build["database_schema_sha256"],
            "server_epoch_sha256": canonical_sha256(
                {key: runtime[key] for key in ("server_epoch", "server_process_id", "session_fingerprint", "max_active_cohorts")}
            ),
            "profile_generation_sha256": canonical_sha256(
                {key: runtime[key] for key in ("profile_generation", "profile_content_hash")}
            ),
            "build_projection_sha256": canonical_sha256(projection),
        },
        "build_identity": build,
        "runtime_identity": runtime,
    }
    if artifacts is not None:
        manifest["artifact_hashes"] = artifacts
    return self_hashed(manifest, "manifest_sha256")


def leaf(
    lane: str,
    row: dict,
    physical: dict,
    *,
    domain_identity: dict | None = None,
    domain_verification: dict | None = None,
) -> tuple[dict, dict, dict]:
    prefix = f"artifacts/{lane}/{row['attempt_id'].replace('/', '_')}"
    manifest = self_hashed(
        {
            "schema": "bot_immutable_batch_manifest_v1",
            "batch_id": row["attempt_id"],
            "raw": {"bundle_sha256": "1" * 64},
            "compact": {"bundle_sha256": "2" * 64},
        },
        "identity_sha256",
    )
    pointers = pointer_rows(f"{prefix}/batch")
    publication = self_hashed(
        {
            "schema": "bot_immutable_batch_publication_receipt_v1",
            "batch_id": row["attempt_id"],
            "batch_identity_sha256": manifest["identity_sha256"],
            "raw_bundle_sha256": "1" * 64,
            "compact_bundle_sha256": "2" * 64,
            "pointers": pointers,
            "remote_verified": True,
        },
        "receipt_sha256",
    )
    reconstruction = self_hashed(
        {
            "schema": "bot_immutable_batch_reconstruction_receipt_v1",
            "batch_id": row["attempt_id"],
            "batch_identity_sha256": manifest["identity_sha256"],
            "publication_receipt_sha256": publication["receipt_sha256"],
            "remote_reconstructed": True,
            "targeted_eviction_complete": True,
            "domain_verification_id": canonical_sha256(domain_identity or {}),
            "domain_verification": domain_verification or {},
        },
        "receipt_sha256",
    )
    row["receipt_sha256"] = publication["receipt_sha256"]
    row["reconstruction_receipt_sha256"] = reconstruction["receipt_sha256"]
    started = self_hashed(
        {
            "schema": f"{lane}_started_v1",
            "physical_attempt": physical,
        },
        "started_receipt_sha256",
    )
    row["started_receipt_sha256"] = started["started_receipt_sha256"]
    result = self_hashed(
        {
            "schema": f"{lane}_result_v1",
            "started_receipt_sha256": started["started_receipt_sha256"],
            "physical_identity_sha256": physical["physical_identity_sha256"],
            "result": row,
        },
        "result_receipt_sha256",
    )
    row["result_receipt_sha256"] = result["result_receipt_sha256"]
    # The production result receipt is written before its hash is copied into
    # the in-memory ledger, so keep the exact receipt payload without it.
    result["result"] = {key: value for key, value in row.items() if key != "result_receipt_sha256"}
    result["result_receipt_sha256"] = canonical_sha256(
        {key: value for key, value in result.items() if key != "result_receipt_sha256"}
    )
    row["result_receipt_sha256"] = result["result_receipt_sha256"]
    return (
        {
            "lane": lane,
            "attempt_id": row["attempt_id"],
            "attempt_directory": prefix,
            "classification": "accepted",
            "selected_for_gate": True,
            "publication_state": "remote_reconstructed_and_evicted",
            "started_receipt": document(f"{prefix}/started.json", started),
            "result_receipt": document(f"{prefix}/result.json", result),
            "final_manifest": document(f"{prefix}/batch/retained/final_manifest.json", manifest),
            "publication_receipt": document(f"{prefix}/batch/retained/publication_receipt.json", publication),
            "reconstruction_receipt": document(f"{prefix}/batch/retained/reconstruction_receipt.json", reconstruction),
            "dvc_pointers": pointers,
        },
        started,
        result,
    )


def joined_closure() -> dict:
    build = {
        "git_commit": "a" * 40,
        "source_tree_clean": True,
        "worldserver_binary_sha256": "b" * 64,
        "database_snapshot_sha256": "c" * 64,
        "database_schema_sha256": "d" * 64,
        "profile_content_hash": "e" * 64,
    }
    target_doc = document("experiments/targets.json", {"targets": []})
    pair_doc = document("experiments/pairs.json", {"pairs": []})
    policy_doc = document("experiments/role-policy.json", {"policy": []})
    references_doc = document("experiments/references.json", {"references": []})
    scenarios_doc = document("experiments/scenarios.json", {"scenarios": []})
    route_doc = document("artifacts/route.json", {"route": []})
    pinned = [
        {"composition_id": f"composition-{index}", "ordered_party": [f"member-{index}-{slot}" for slot in range(5)]}
        for index in range(1, 8)
    ]
    matrix = self_hashed(
        {"schema": "stonecore_phase9_pairwise_matrix_v1", "serial_canaries": pinned},
        "matrix_sha256",
    )
    matrix_doc = document("experiments/matrix.json", matrix)
    artifacts = {
        "target_catalog_sha256": target_doc["sha256"],
        "pair_policy_sha256": pair_doc["sha256"],
        "pairwise_matrix_sha256": matrix_doc["sha256"],
        "route_manifest_sha256": route_doc["sha256"],
    }
    dps_identity = identity_manifest("all_spec_phase8_evidence_identity_manifest_v2", build)
    phase9_identity = identity_manifest(
        "all_spec_phase9_evidence_identity_manifest_v2", build, artifacts=artifacts
    )

    targets = [f"dps-{index:02d}" for index in range(1, 17)]
    config = {"dps_targets": targets}
    config_doc = document("experiments/dps-config.json", config)
    dps_attempts = [
        {
            "attempt_id": f"qualification/{target}",
            "spec_target_id": target,
            "runtime_join_key": target,
            "mode": "single_target_300",
            "seed": 1,
            "cohort_id": f"cohort-{index}",
            "attempt_index": index,
        }
        for index, target in enumerate(targets, start=1)
    ]
    dps_plan = self_hashed(
        {
            "schema": "cata_raid_dps_acceptance_campaign_plan_v1",
            "max_tries_per_dps_spec": 2,
            "attempts": dps_attempts,
        },
        "plan_sha256",
    )
    dps_rows: list[dict] = []
    phase9_rows: list[dict] = []
    leaves: list[dict] = []
    phase9_receipts: dict[str, tuple[dict, dict]] = {}
    for index, logical in enumerate(dps_attempts, start=1):
        attempt_id = f"{logical['attempt_id']}/try-1"
        physical = {
            **logical,
            "attempt_id": attempt_id,
            "physical_identity_sha256": f"{index:064x}",
        }
        row = {
            "attempt_id": attempt_id,
            "logical_attempt_id": logical["attempt_id"],
            "physical_try_ordinal": 1,
            "physical_identity_sha256": physical["physical_identity_sha256"],
            "spec_target_id": logical["spec_target_id"],
            "remote_source_report_sha256": f"{200 + index:064x}",
            "remote_evaluation_sha256": f"{300 + index:064x}",
            "remote_compact_binding_sha256": f"{400 + index:064x}",
            "classification": "accepted",
            "accepted": True,
            "child_returncode_observed": True,
            "returncode": 0,
            "report_returncode": 0,
            "timed_out": False,
            "calibration_acceptance_passed": True,
            "acceptable_final_evidence": True,
            "all_passed": True,
            "hard_floor_passed": True,
            "optimization_target_met": True,
            "reference_ratio": 0.86,
            "remote_transport_verified": True,
            "remote_provenance_verified": True,
            "remote_evidence_class": "non_certifying_calibration_fixture",
            "remote_excluded_from_training_corpus": True,
            "remote_runtime_mode": "calibration_fixture",
            "remote_non_certifying_assistance": True,
            "published": True,
            "remote_reconstruction_verified": True,
            "targeted_eviction_complete": True,
            "passed": True,
        }
        dps_domain_identity = {
            "schema": "cata_raid_dps_remote_calibration_reconstruction_v1",
            "attempt": physical,
            "policy_sha256": policy_doc["sha256"],
            "targets_sha256": target_doc["sha256"],
            "references_sha256": references_doc["sha256"],
            "scenarios_sha256": scenarios_doc["sha256"],
            "evidence_identity_manifest_sha256": dps_identity["manifest_sha256"],
            "fixture_provenance": {
                "evidence_class": "non_certifying_calibration_fixture",
                "excluded_from_training_corpus": True,
                "runtime_mode": "calibration_fixture",
                "non_certifying_assistance": True,
            },
        }
        dps_remote = {
            "schema": "cata_raid_dps_remote_calibration_verification_v1",
            "verified": True,
            "attempt_id": attempt_id,
            "source_report_sha256": row["remote_source_report_sha256"],
            "evaluation_sha256": row["remote_evaluation_sha256"],
            "compact_binding_sha256": row["remote_compact_binding_sha256"],
            "source_transport_verified": True,
            "provenance_verified": True,
            "evidence_build_identity_compatible": True,
            "evidence_identity_manifest_sha256": dps_identity["manifest_sha256"],
            "requested_calibration": {
                "target_spec": logical["runtime_join_key"],
                "mode": logical["mode"],
                "seed": 1,
            },
            "role_calibration_identity": {"spec_target_id": logical["spec_target_id"]},
            "session_identity": {
                "cohort_id": logical["cohort_id"],
                "attempt_index": logical["attempt_index"],
            },
            "evaluation": {
                "passed": True,
                "hard_floor_passed": True,
                "optimization_target_met": True,
                "reference_ratio": 0.86,
                "failure_reasons": [],
            },
        }
        batch, _, _ = leaf(
            "dps",
            row,
            physical,
            domain_identity=dps_domain_identity,
            domain_verification=dps_remote,
        )
        leaves.append(batch)
        dps_rows.append(row)

    phase9_attempts = []
    serial = 0
    for composition in pinned:
        for ordinal in (1, 2):
            serial += 1
            logical_id = f"phase9-{serial:02d}"
            logical = {
                "attempt_id": logical_id,
                "serial_index": serial,
                "composition_id": composition["composition_id"],
                "clear_ordinal": ordinal,
                "ordered_party": composition["ordered_party"],
                "execution_policy": "run_to_completion",
                "overall_wall_clock_timeout_sec": None,
                "command": ["phase9-child", "--run-to-completion"],
            }
            phase9_attempts.append(logical)
            attempt_id = f"{logical_id}/try-01"
            physical = {
                **logical,
                "attempt_id": attempt_id,
                "physical_identity_sha256": f"{100 + serial:064x}",
                "composition_sha256": f"{500 + serial:064x}",
                "party_sha256": f"{600 + serial:064x}",
                "success_ordinal": ordinal,
                "physical_try_ordinal": 1,
            }
            row = {
                "attempt_id": attempt_id,
                "logical_attempt_id": logical_id,
                "serial_index": serial,
                "composition_id": composition["composition_id"],
                "success_ordinal": ordinal,
                "physical_try_ordinal": 1,
                "physical_identity_sha256": physical["physical_identity_sha256"],
                "remote_source_report_sha256": f"{700 + serial:064x}",
                "remote_compact_binding_sha256": f"{800 + serial:064x}",
                "remote_acceptance_verification_sha256": f"{900 + serial:064x}",
                "classification": "accepted",
                "passed": True,
                "child_returncode_observed": True,
                "returncode": 0,
                "transport_classification": "child_exited",
                "execution_policy": "run_to_completion",
                "overall_wall_clock_timeout_sec": None,
                "outer_timed_out": False,
                "controller_interrupted": False,
                "process_group_gone": True,
                "report_returncode": 0,
                "timed_out": False,
                "remote_verified": True,
                "remote_reconstruction_verified": True,
                "remote_domain_verified": True,
                "remote_transport_verified": True,
                "targeted_eviction_complete": True,
                "exact_party_verified": True,
                "heroic_admission_verified": True,
                "server_route_start_provisioned": True,
                "identity_matches": True,
                "cleanup_complete": True,
            }
            batch, started, result = leaf("phase9", row, physical)
            leaves.append(batch)
            phase9_rows.append(row)
            phase9_receipts[attempt_id] = (started, result)

    phase9_plan = self_hashed(
        {
            "schema": "all_spec_phase9_serial_run_plan_v1",
            "matrix_file_sha256": matrix_doc["sha256"],
            "dps_acceptance_state_sha256": "pending",
            "execution_policy": "run_to_completion",
            "overall_wall_clock_timeout_sec": None,
            "retry_policy": "unlimited_physical_tries_until_terminal_success",
            "terminal_conditions": list(
                joined_campaign_evidence.PHASE9_TERMINAL_CONDITIONS
            ),
            "attempts": phase9_attempts,
        },
        "plan_sha256",
    )
    events = [
        {
            "event_id": f"campaign:{phase9_plan['plan_sha256']}",
            "event": "campaign_started",
            "run_plan_sha256": phase9_plan["plan_sha256"],
            "identity_manifest_sha256": phase9_identity["manifest_sha256"],
            "logical_success_slot_count": 14,
        }
    ]
    for row in phase9_rows:
        started, result = phase9_receipts[row["attempt_id"]]
        common = {
            "run_plan_sha256": phase9_plan["plan_sha256"],
            "identity_manifest_sha256": phase9_identity["manifest_sha256"],
            "logical_attempt_id": row["logical_attempt_id"],
            "attempt_id": row["attempt_id"],
            "serial_index": row["serial_index"],
            "composition_id": row["composition_id"],
            "success_ordinal": row["success_ordinal"],
            "physical_try_ordinal": 1,
            "physical_identity_sha256": row["physical_identity_sha256"],
            "started_receipt_sha256": started["started_receipt_sha256"],
        }
        events.extend(
            (
                {"event_id": f"started:{row['physical_identity_sha256']}", "event": "physical_try_started", **common},
                {
                    "event_id": f"result:{row['physical_identity_sha256']}",
                    "event": "physical_try_result",
                    **common,
                    "result_receipt_sha256": result["result_receipt_sha256"],
                    "classification": "accepted",
                    "accepted": True,
                    "child_returncode_observed": True,
                    "child_returncode": 0,
                    "timed_out": False,
                    "publication_receipt_sha256": row["receipt_sha256"],
                    "reconstruction_receipt_sha256": row["reconstruction_receipt_sha256"],
                },
            )
        )
    previous = ""
    encoded_events = []
    for sequence, payload in enumerate(events, start=1):
        event = {
            "schema": "phase9_physical_try_ledger_event_v1",
            "sequence": sequence,
            "previous_event_sha256": previous,
            **payload,
        }
        event["event_sha256"] = canonical_sha256(event)
        previous = event["event_sha256"]
        encoded_events.append(event)
    ledger_text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in encoded_events)
    ledger_doc = text_document("artifacts/phase9/phase9_physical_try_ledger.jsonl", ledger_text)

    dps_state = self_hashed(
        {
            "schema": "cata_raid_dps_acceptance_campaign_state_v2",
            "config_sha256": config_doc["sha256"],
            "max_tries_per_dps_spec": 2,
            "physical_try_ledger": dps_rows,
            "passed": True,
            "active_attempt": None,
        },
        "state_sha256",
    )
    dps_state_doc = document("artifacts/dps/campaign_state.json", dps_state)
    phase9_plan["dps_acceptance_state_sha256"] = dps_state_doc["sha256"]
    phase9_plan["plan_sha256"] = canonical_sha256(
        {key: value for key, value in phase9_plan.items() if key != "plan_sha256"}
    )
    for row in phase9_rows:
        batch = next(
            leaf_row
            for leaf_row in leaves
            if leaf_row["lane"] == "phase9"
            and leaf_row["attempt_id"] == row["attempt_id"]
        )
        started = json.loads(batch["started_receipt"]["document"])
        physical = started["physical_attempt"]
        domain_identity = {
            "schema": "phase9_remote_full_clear_reconstruction_v1",
            "attempt_id": physical.get("attempt_id"),
            "composition_sha256": physical.get("composition_sha256"),
            "party_sha256": physical.get("party_sha256"),
            "success_ordinal": physical.get("success_ordinal"),
            "physical_try_ordinal": physical.get("physical_try_ordinal"),
            "physical_identity_sha256": physical.get("physical_identity_sha256"),
            "plan_sha256": phase9_plan["plan_sha256"],
            "identity_manifest_sha256": phase9_identity["manifest_sha256"],
        }
        reconstruction = json.loads(batch["reconstruction_receipt"]["document"])
        reconstruction["domain_verification_id"] = canonical_sha256(domain_identity)
        reconstruction["domain_verification"] = {
            "schema": "phase9_remote_full_clear_verification_v1",
            "verified": True,
            "attempt_id": row["attempt_id"],
            "execution_policy": "run_to_completion",
            "overall_wall_clock_timeout_sec": None,
            "source_report_sha256": row["remote_source_report_sha256"],
            "compact_binding_sha256": row["remote_compact_binding_sha256"],
            "acceptance_verification_sha256": row[
                "remote_acceptance_verification_sha256"
            ],
            "source_transport_verified": True,
            "runtime_identity_valid": True,
            "attempt_identity_valid": True,
            "exact_party_valid": True,
            "server_route_start_provisioned": True,
            "cleanup_complete": True,
            "heroic_admission": {"verified": True},
        }
        reconstruction["receipt_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in reconstruction.items()
                if key != "receipt_sha256"
            }
        )
        row["reconstruction_receipt_sha256"] = reconstruction["receipt_sha256"]
        batch["reconstruction_receipt"] = document(
            batch["reconstruction_receipt"]["path"], reconstruction
        )
        result = json.loads(batch["result_receipt"]["document"])
        result["result"]["reconstruction_receipt_sha256"] = reconstruction[
            "receipt_sha256"
        ]
        result["result_receipt_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in result.items()
                if key != "result_receipt_sha256"
            }
        )
        row["result_receipt_sha256"] = result["result_receipt_sha256"]
        batch["result_receipt"] = document(batch["result_receipt"]["path"], result)
        phase9_receipts[row["attempt_id"]] = (started, result)
    # Rebind the append header/events to the final Phase 9 plan identity.
    old_plan_hash = events[0]["run_plan_sha256"]
    for event in encoded_events:
        if event.get("run_plan_sha256") == old_plan_hash:
            event["run_plan_sha256"] = phase9_plan["plan_sha256"]
        if event.get("event_id") == f"campaign:{old_plan_hash}":
            event["event_id"] = f"campaign:{phase9_plan['plan_sha256']}"
        if event.get("event") == "physical_try_result":
            row = next(
                candidate
                for candidate in phase9_rows
                if candidate["attempt_id"] == event.get("attempt_id")
            )
            event["result_receipt_sha256"] = row["result_receipt_sha256"]
            event["reconstruction_receipt_sha256"] = row[
                "reconstruction_receipt_sha256"
            ]
    previous = ""
    for sequence, event in enumerate(encoded_events, start=1):
        event["sequence"] = sequence
        event["previous_event_sha256"] = previous
        event["event_sha256"] = canonical_sha256(
            {key: value for key, value in event.items() if key != "event_sha256"}
        )
        previous = event["event_sha256"]
    ledger_text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in encoded_events)
    ledger_doc = text_document("artifacts/phase9/phase9_physical_try_ledger.jsonl", ledger_text)
    phase9_state = self_hashed(
        {
            "schema": "phase9_serial_canary_operator_state_v3",
            "execution_policy": "run_to_completion",
            "overall_wall_clock_timeout_sec": None,
            "retry_policy": "unlimited_physical_tries_until_terminal_success",
            "terminal_conditions": list(
                joined_campaign_evidence.PHASE9_TERMINAL_CONDITIONS
            ),
            "physical_try_ledger": phase9_rows,
            "append_ledger": {
                "event_count": len(encoded_events),
                "tail_sha256": previous,
                "file_sha256": ledger_doc["sha256"],
            },
            "status": "passed",
            "promotion_gate_passed": True,
            "active_attempt": None,
        },
        "state_sha256",
    )

    joined_verification = self_hashed(
        {
            "schema": "phase9_joined_campaign_verification_v1",
            "passed": True,
            "verified_phase9_attempt_count": 14,
            "verified_dps_attempt_count": 16,
        },
        "verification_sha256",
    )
    exact = {
        "dps_acceptance_config": config_doc,
        "dps_campaign_plan": document("artifacts/dps/campaign_plan.json", dps_plan),
        "dps_campaign_state": dps_state_doc,
        "dps_evidence_identity": document("artifacts/dps/identity.json", dps_identity),
        "phase9_run_plan": document("artifacts/phase9/run_plan.json", phase9_plan),
        "phase9_operator_state": document("artifacts/phase9/operator_state.json", phase9_state),
        "joined_campaign_verification": document(
            "artifacts/phase9/joined_campaign_verification.json",
            joined_verification,
        ),
        "phase9_evidence_identity": document("artifacts/phase9/identity.json", phase9_identity),
        "phase9_pairwise_matrix": matrix_doc,
        "phase9_append_ledger": ledger_doc,
        "phase8_config_target_catalog": target_doc,
        "phase8_config_stonecore_pair_policy": pair_doc,
        "phase8_config_role_calibration_policy": policy_doc,
        "phase8_config_reference_catalog": references_doc,
        "phase8_calibration_scenarios": scenarios_doc,
        "phase9_route_manifest": route_doc,
    }
    closure = {
        "schema": "joined_16_dps_14_stonecore_evidence_closure_v1",
        "evidence_scope": {},
        "exact_documents": exact,
        "physical_ledgers": {"dps": dps_rows, "phase9": phase9_rows},
        "materialized_try_ids": {
            "dps": [row["attempt_id"] for row in dps_rows],
            "phase9": [row["attempt_id"] for row in phase9_rows],
        },
        "leaf_batches": leaves,
        "joined_verification": joined_verification,
    }
    closure["closure_sha256"] = canonical_sha256(closure)
    return closure


def test_pure_closure_verifier_roundtrip_and_tamper() -> None:
    closure = joined_closure()
    verified = verify_joined_campaign_closure(closure)
    assert verified["passed"] is True
    assert verified["verified_dps_logical_qualifications"] == 16
    assert verified["verified_phase9_player_like_clears"] == 14

    tampered = deepcopy(closure)
    tampered["physical_ledgers"]["phase9"][0]["cleanup_complete"] = False
    assert verify_joined_campaign_closure(tampered)["passed"] is False


def test_accepted_leaf_rejects_domain_or_batch_transplant() -> None:
    closure = joined_closure()
    leaf_row = next(
        row
        for row in closure["leaf_batches"]
        if row["lane"] == "dps" and row["selected_for_gate"] is True
    )
    result = next(
        row
        for row in closure["physical_ledgers"]["dps"]
        if row["attempt_id"] == leaf_row["attempt_id"]
    )
    identity = json.loads(
        closure["exact_documents"]["dps_evidence_identity"]["document"]
    )
    context = {
        "policy_sha256": closure["exact_documents"][
            "phase8_config_role_calibration_policy"
        ]["sha256"],
        "targets_sha256": closure["exact_documents"][
            "phase8_config_target_catalog"
        ]["sha256"],
        "references_sha256": closure["exact_documents"][
            "phase8_config_reference_catalog"
        ]["sha256"],
        "scenarios_sha256": closure["exact_documents"][
            "phase8_calibration_scenarios"
        ]["sha256"],
        "identity_manifest_sha256": identity["manifest_sha256"],
    }
    misplaced = deepcopy(leaf_row)
    misplaced["attempt_directory"] = "artifacts/dps/unrelated"
    with pytest.raises(JoinedEvidenceError, match="publication chain"):
        _verify_leaf(misplaced, result, context)

    tampered = deepcopy(leaf_row)
    reconstruction = json.loads(tampered["reconstruction_receipt"]["document"])
    reconstruction["domain_verification"]["attempt_id"] = "another-attempt"
    reconstruction["receipt_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in reconstruction.items()
            if key != "receipt_sha256"
        }
    )
    tampered["reconstruction_receipt"] = document(
        tampered["reconstruction_receipt"]["path"], reconstruction
    )
    changed_result = deepcopy(result)
    changed_result["reconstruction_receipt_sha256"] = reconstruction[
        "receipt_sha256"
    ]
    result_receipt = json.loads(tampered["result_receipt"]["document"])
    result_receipt["result"]["reconstruction_receipt_sha256"] = reconstruction[
        "receipt_sha256"
    ]
    result_receipt["result_receipt_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in result_receipt.items()
            if key != "result_receipt_sha256"
        }
    )
    changed_result["result_receipt_sha256"] = result_receipt[
        "result_receipt_sha256"
    ]
    tampered["result_receipt"] = document(
        tampered["result_receipt"]["path"], result_receipt
    )
    with pytest.raises(JoinedEvidenceError, match="domain reconstruction"):
        _verify_leaf(tampered, changed_result, context)


def test_recursive_clean_audit_pulls_all_accepted_leaves_and_cleans_scaffold(
    tmp_path: Path, monkeypatch
) -> None:
    closure = joined_closure()
    calls: list[Path] = []

    def fake_leaf_reconstruction(_repository, batch_root, **kwargs):
        assert kwargs["force_reconstruct"] is True
        reconstruction = json.loads(
            (batch_root / "retained/reconstruction_receipt.json").read_text(
                encoding="utf-8"
            )
        )
        assert kwargs["domain_verification_id"] == reconstruction[
            "domain_verification_id"
        ]
        calls.append(batch_root)
        return {
            "remote_reconstructed": True,
            "targeted_eviction_complete": True,
            "domain_verification": reconstruction["domain_verification"],
        }

    monkeypatch.setattr(
        batch_evidence_lifecycle,
        "verify_remote_reconstruction_and_evict",
        fake_leaf_reconstruction,
    )
    result = _recursively_verify_accepted_leaves(tmp_path, closure)
    assert result == {
        "verified": True,
        "accepted_leaf_count": 30,
        "targeted_eviction_complete": True,
    }
    assert len(calls) == 30
    assert not (tmp_path / "artifacts").exists()
    assert not (tmp_path / "experiments").exists()


def test_closure_keeps_failed_retry_with_unsuccessful_batch_documents() -> None:
    closure = joined_closure()
    accepted = closure["physical_ledgers"]["dps"][0]
    logical_id = accepted["logical_attempt_id"]
    old_attempt_id = accepted["attempt_id"]
    for key in (
        "receipt_sha256",
        "reconstruction_receipt_sha256",
        "started_receipt_sha256",
        "result_receipt_sha256",
    ):
        accepted.pop(key, None)
    accepted["attempt_id"] = f"{logical_id}/try-2"
    accepted["physical_try_ordinal"] = 2
    accepted["physical_identity_sha256"] = "9" * 64
    dps_plan = json.loads(closure["exact_documents"]["dps_campaign_plan"]["document"])
    logical = next(row for row in dps_plan["attempts"] if row["attempt_id"] == logical_id)
    retry_physical = {
        **logical,
        "attempt_id": accepted["attempt_id"],
        "physical_identity_sha256": accepted["physical_identity_sha256"],
    }
    dps_identity = json.loads(
        closure["exact_documents"]["dps_evidence_identity"]["document"]
    )
    retry_domain = {
        "schema": "cata_raid_dps_remote_calibration_reconstruction_v1",
        "attempt": retry_physical,
        "policy_sha256": closure["exact_documents"][
            "phase8_config_role_calibration_policy"
        ]["sha256"],
        "targets_sha256": closure["exact_documents"][
            "phase8_config_target_catalog"
        ]["sha256"],
        "references_sha256": closure["exact_documents"][
            "phase8_config_reference_catalog"
        ]["sha256"],
        "scenarios_sha256": closure["exact_documents"][
            "phase8_calibration_scenarios"
        ]["sha256"],
        "evidence_identity_manifest_sha256": dps_identity["manifest_sha256"],
        "fixture_provenance": {
            "evidence_class": "non_certifying_calibration_fixture",
            "excluded_from_training_corpus": True,
            "runtime_mode": "calibration_fixture",
            "non_certifying_assistance": True,
        },
    }
    retry_remote = {
        "schema": "cata_raid_dps_remote_calibration_verification_v1",
        "verified": True,
        "attempt_id": accepted["attempt_id"],
        "source_report_sha256": accepted["remote_source_report_sha256"],
        "evaluation_sha256": accepted["remote_evaluation_sha256"],
        "compact_binding_sha256": accepted["remote_compact_binding_sha256"],
        "source_transport_verified": True,
        "provenance_verified": True,
        "evidence_build_identity_compatible": True,
        "evidence_identity_manifest_sha256": dps_identity["manifest_sha256"],
        "requested_calibration": {
            "target_spec": logical["runtime_join_key"],
            "mode": logical["mode"],
            "seed": logical["seed"],
        },
        "role_calibration_identity": {"spec_target_id": logical["spec_target_id"]},
        "session_identity": {
            "cohort_id": logical["cohort_id"],
            "attempt_index": logical["attempt_index"],
        },
        "evaluation": {
            "passed": True,
            "hard_floor_passed": True,
            "optimization_target_met": True,
            "reference_ratio": 0.86,
            "failure_reasons": [],
        },
    }
    replacement, _, _ = leaf(
        "dps",
        accepted,
        retry_physical,
        domain_identity=retry_domain,
        domain_verification=retry_remote,
    )
    closure["leaf_batches"] = [
        replacement if row["attempt_id"] == old_attempt_id else row
        for row in closure["leaf_batches"]
    ]
    failure = {
        "attempt_id": f"{logical_id}/try-1",
        "logical_attempt_id": logical_id,
        "physical_try_ordinal": 1,
        "physical_identity_sha256": "8" * 64,
        "spec_target_id": accepted["spec_target_id"],
        "classification": "infrastructure_failure",
        "accepted": False,
        "child_returncode_observed": False,
        "returncode": None,
        "timed_out": None,
        "passed": False,
    }
    started = self_hashed(
        {
            "schema": "dps_started_v1",
            "physical_attempt": {
                "attempt_id": failure["attempt_id"],
                "physical_identity_sha256": failure["physical_identity_sha256"],
            },
        },
        "started_receipt_sha256",
    )
    failure["started_receipt_sha256"] = started["started_receipt_sha256"]
    result = self_hashed(
        {
            "schema": "dps_result_v1",
            "started_receipt_sha256": started["started_receipt_sha256"],
            "physical_identity_sha256": failure["physical_identity_sha256"],
            "result": dict(failure),
        },
        "result_receipt_sha256",
    )
    failure["result_receipt_sha256"] = result["result_receipt_sha256"]
    failed_batch_documents = {
        "final_manifest": document(
            "artifacts/dps/failure/batch/retained/final_manifest.json",
            self_hashed(
                {
                    "schema": "bot_immutable_batch_manifest_v1",
                    "batch_id": failure["attempt_id"],
                },
                "identity_sha256",
            ),
        ),
        "publication_receipt": document(
            "artifacts/dps/failure/batch/retained/publication_receipt.json",
            self_hashed(
                {
                    "schema": "bot_immutable_batch_publication_receipt_v1",
                    "batch_id": failure["attempt_id"],
                    "remote_verified": False,
                },
                "receipt_sha256",
            ),
        ),
        "reconstruction_receipt": document(
            "artifacts/dps/failure/batch/retained/reconstruction_receipt.json",
            self_hashed(
                {
                    "schema": "bot_immutable_batch_reconstruction_receipt_v1",
                    "batch_id": failure["attempt_id"],
                    "remote_reconstructed": False,
                    "targeted_eviction_complete": True,
                },
                "receipt_sha256",
            ),
        ),
    }
    failure_leaf = {
        "lane": "dps",
        "attempt_id": failure["attempt_id"],
        "attempt_directory": "artifacts/dps/failure",
        "classification": "infrastructure_failure",
        "selected_for_gate": False,
        "publication_state": "failure_batch_documents_not_gate_bearing",
        "dvc_pointers": [],
        "failure_evidence": [],
        "failure_batch_documents": failed_batch_documents,
        "started_receipt": document("artifacts/dps/failure/started.json", started),
        "result_receipt": document("artifacts/dps/failure/result.json", result),
    }
    closure["physical_ledgers"]["dps"].insert(0, failure)
    closure["materialized_try_ids"]["dps"] = [
        row["attempt_id"] for row in closure["physical_ledgers"]["dps"]
    ]
    closure["leaf_batches"].append(failure_leaf)
    state = json.loads(
        closure["exact_documents"]["dps_campaign_state"]["document"]
    )
    state["physical_try_ledger"] = closure["physical_ledgers"]["dps"]
    state["state_sha256"] = canonical_sha256(
        {key: value for key, value in state.items() if key != "state_sha256"}
    )
    closure["exact_documents"]["dps_campaign_state"] = document(
        "artifacts/dps/campaign_state.json", state
    )
    phase9_plan = json.loads(
        closure["exact_documents"]["phase9_run_plan"]["document"]
    )
    phase9_plan["dps_acceptance_state_sha256"] = closure["exact_documents"][
        "dps_campaign_state"
    ]["sha256"]
    phase9_plan["plan_sha256"] = canonical_sha256(
        {key: value for key, value in phase9_plan.items() if key != "plan_sha256"}
    )
    old_plan_sha = json.loads(
        closure["exact_documents"]["phase9_run_plan"]["document"]
    )["plan_sha256"]
    closure["exact_documents"]["phase9_run_plan"] = document(
        "artifacts/phase9/run_plan.json", phase9_plan
    )
    phase9_identity = json.loads(
        closure["exact_documents"]["phase9_evidence_identity"]["document"]
    )
    for row in closure["physical_ledgers"]["phase9"]:
        batch = next(
            leaf_row
            for leaf_row in closure["leaf_batches"]
            if leaf_row["lane"] == "phase9"
            and leaf_row["attempt_id"] == row["attempt_id"]
        )
        started_receipt = json.loads(batch["started_receipt"]["document"])
        physical = started_receipt["physical_attempt"]
        domain_identity = {
            "schema": "phase9_remote_full_clear_reconstruction_v1",
            "attempt_id": physical.get("attempt_id"),
            "composition_sha256": physical.get("composition_sha256"),
            "party_sha256": physical.get("party_sha256"),
            "success_ordinal": physical.get("success_ordinal"),
            "physical_try_ordinal": physical.get("physical_try_ordinal"),
            "physical_identity_sha256": physical.get("physical_identity_sha256"),
            "plan_sha256": phase9_plan["plan_sha256"],
            "identity_manifest_sha256": phase9_identity["manifest_sha256"],
        }
        reconstruction = json.loads(batch["reconstruction_receipt"]["document"])
        reconstruction["domain_verification_id"] = canonical_sha256(domain_identity)
        reconstruction["receipt_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in reconstruction.items()
                if key != "receipt_sha256"
            }
        )
        row["reconstruction_receipt_sha256"] = reconstruction["receipt_sha256"]
        batch["reconstruction_receipt"] = document(
            batch["reconstruction_receipt"]["path"], reconstruction
        )
        result_receipt = json.loads(batch["result_receipt"]["document"])
        result_receipt["result"]["reconstruction_receipt_sha256"] = reconstruction[
            "receipt_sha256"
        ]
        result_receipt["result_receipt_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in result_receipt.items()
                if key != "result_receipt_sha256"
            }
        )
        row["result_receipt_sha256"] = result_receipt["result_receipt_sha256"]
        batch["result_receipt"] = document(
            batch["result_receipt"]["path"], result_receipt
        )
    ledger_events = [
        json.loads(line)
        for line in closure["exact_documents"]["phase9_append_ledger"][
            "document"
        ].splitlines()
    ]
    previous = ""
    for sequence, event in enumerate(ledger_events, start=1):
        if event.get("run_plan_sha256") == old_plan_sha:
            event["run_plan_sha256"] = phase9_plan["plan_sha256"]
        if event.get("event_id") == f"campaign:{old_plan_sha}":
            event["event_id"] = f"campaign:{phase9_plan['plan_sha256']}"
        if event.get("event") == "physical_try_result":
            result_row = next(
                row
                for row in closure["physical_ledgers"]["phase9"]
                if row["attempt_id"] == event["attempt_id"]
            )
            event["result_receipt_sha256"] = result_row[
                "result_receipt_sha256"
            ]
            event["reconstruction_receipt_sha256"] = result_row[
                "reconstruction_receipt_sha256"
            ]
        event["sequence"] = sequence
        event["previous_event_sha256"] = previous
        event["event_sha256"] = canonical_sha256(
            {key: value for key, value in event.items() if key != "event_sha256"}
        )
        previous = event["event_sha256"]
    ledger_text = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in ledger_events
    )
    ledger_record = text_document(
        "artifacts/phase9/phase9_physical_try_ledger.jsonl", ledger_text
    )
    closure["exact_documents"]["phase9_append_ledger"] = ledger_record
    phase9_state = json.loads(
        closure["exact_documents"]["phase9_operator_state"]["document"]
    )
    phase9_state["physical_try_ledger"] = closure["physical_ledgers"]["phase9"]
    phase9_state["append_ledger"] = {
        "event_count": len(ledger_events),
        "tail_sha256": previous,
        "file_sha256": ledger_record["sha256"],
    }
    phase9_state["state_sha256"] = canonical_sha256(
        {key: value for key, value in phase9_state.items() if key != "state_sha256"}
    )
    closure["exact_documents"]["phase9_operator_state"] = document(
        "artifacts/phase9/operator_state.json", phase9_state
    )
    closure["closure_sha256"] = canonical_sha256(
        {key: value for key, value in closure.items() if key != "closure_sha256"}
    )
    verification = verify_joined_campaign_closure(closure)
    assert verification["passed"] is True, verification["failure_reasons"]
    closure["leaf_batches"].remove(failure_leaf)
    closure["closure_sha256"] = canonical_sha256(
        {key: value for key, value in closure.items() if key != "closure_sha256"}
    )
    assert verify_joined_campaign_closure(closure)["passed"] is False


def test_clean_directory_bootstrap_restores_only_outer_graph(
    tmp_path: Path, monkeypatch
) -> None:
    closure = joined_closure()
    closure_sha = closure["closure_sha256"]
    source = tmp_path / "source"
    batch = source / "ignored/campaign/outer"
    retained = batch / "retained"
    retained.mkdir(parents=True)
    manifest = self_hashed(
        {
            "schema": "bot_immutable_batch_manifest_v1",
            "batch_id": "campaign-1",
            "raw": {"bundle_sha256": "1" * 64},
            "compact": {"bundle_sha256": "2" * 64},
        },
        "identity_sha256",
    )
    pointers = pointer_rows("ignored/campaign/outer")
    publication = self_hashed(
        {
            "schema": "bot_immutable_batch_publication_receipt_v1",
            "batch_id": "campaign-1",
            "batch_identity_sha256": manifest["identity_sha256"],
            "raw_bundle_sha256": "1" * 64,
            "compact_bundle_sha256": "2" * 64,
            "pointers": pointers,
            "remote_verified": True,
        },
        "receipt_sha256",
    )
    domain_identity = {
        "schema": "phase9_joined_campaign_remote_reconstruction_v1",
        "state_sha256": "d" * 64,
        "verification_sha256": "e" * 64,
        "closure_sha256": closure_sha,
    }
    reconstruction = self_hashed(
        {
            "schema": "bot_immutable_batch_reconstruction_receipt_v1",
            "batch_id": "campaign-1",
            "batch_identity_sha256": manifest["identity_sha256"],
            "publication_receipt_sha256": publication["receipt_sha256"],
            "remote_reconstructed": True,
            "targeted_eviction_complete": True,
            "domain_verification_id": canonical_sha256(domain_identity),
            "domain_verification": {
                "verified": True,
                "closure_sha256": closure_sha,
                "verified_dps_logical_qualifications": 16,
                "verified_phase9_player_like_clears": 14,
                "verified_dps_physical_tries": 16,
                "verified_phase9_physical_tries": 14,
                "accepted_leaf_remote_reconstructions": 30,
                "accepted_leaf_targeted_eviction_complete": True,
            },
        },
        "receipt_sha256",
    )
    for name, payload in (
        ("final_manifest.json", manifest),
        ("publication_receipt.json", publication),
        ("reconstruction_receipt.json", reconstruction),
    ):
        (retained / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    bootstrap = build_outer_bootstrap(
        source, batch, closure_sha, domain_identity
    )
    tracked = write_outer_bootstrap(source, bootstrap)
    assert tracked == source / "experiments/evidence_indexes/campaign-1/bootstrap.json"
    assert verify_joined_campaign_bootstrap(bootstrap)["passed"] is True

    clean = tmp_path / "clean"
    clean.mkdir()
    restored = materialize_outer_bootstrap(clean, bootstrap)
    assert restored == clean / "ignored/campaign/outer"
    assert (restored / "raw.dvc").is_file()
    assert (restored / "compact.dvc").is_file()
    assert (restored / "retained/reconstruction_receipt.json").is_file()
    assert not (restored / "raw").exists()
    assert not (restored / "compact").exists()

    bootstrap_copy = clean / "bootstrap.json"
    bootstrap_copy.write_text(
        json.dumps(bootstrap, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    def fake_reconstruct(_repository, batch_root, **kwargs):
        assert kwargs["force_reconstruct"] is True
        raw = batch_root / "raw"
        raw.mkdir(parents=True)
        (raw / "acceptance_source_report.json").write_text(
            json.dumps({"joined_campaign_closure": closure}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        domain = kwargs["verify_hydrated"](batch_root)
        assert domain["verified"] is True
        (raw / "acceptance_source_report.json").unlink()
        raw.rmdir()
        return {
            "remote_reconstructed": True,
            "targeted_eviction_complete": True,
            "domain_verification": domain,
        }

    monkeypatch.setattr(
        batch_evidence_lifecycle,
        "verify_remote_reconstruction_and_evict",
        fake_reconstruct,
    )
    monkeypatch.setattr(
        joined_campaign_evidence,
        "_recursively_verify_accepted_leaves",
        lambda _repository, _closure: {
            "verified": True,
            "accepted_leaf_count": 30,
            "targeted_eviction_complete": True,
        },
    )
    roundtrip = reconstruct_outer_from_bootstrap(clean, bootstrap_copy)
    roundtrip_domain = roundtrip["domain_verification"]
    assert roundtrip_domain["closure_sha256"] == closure_sha
    assert roundtrip_domain["verified_dps_physical_tries"] == 16
    assert roundtrip_domain["verified_phase9_physical_tries"] == 14
    assert roundtrip_domain["accepted_leaf_remote_reconstructions"] == 30
    assert not (restored / "raw").exists()

    tampered = deepcopy(bootstrap)
    tampered["outer_dvc_pointers"][0]["pointer_document"] += "# tamper\n"
    try:
        verify_joined_campaign_bootstrap(tampered)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered bootstrap unexpectedly verified")

    rehashed_claim = deepcopy(bootstrap)
    rehashed_claim["closure_sha256"] = "0" * 64
    rehashed_claim["bootstrap_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in rehashed_claim.items()
            if key != "bootstrap_sha256"
        }
    )
    try:
        verify_joined_campaign_bootstrap(rehashed_claim)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "rehashed arbitrary closure claim unexpectedly verified"
        )
