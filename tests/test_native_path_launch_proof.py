from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT
    / "experiments/configs/"
    "cata_raid_magmaw_748d63431c_receipt_tagged_progress_replay_summary_v1.json"
)
SUMMARY_SHA256 = "3e3dac61dcd39c6af8c76abe9c17eb505802acf83cec617e67c33f6d6d9fbebd"
RECEIPT_HISTORY_SUMMARY = (
    ROOT
    / "experiments/configs/"
    "cata_raid_magmaw_78e33e6557_receipt_history_fixture_expansion_summary_v1.json"
)
RECEIPT_HISTORY_SUMMARY_SHA256 = (
    "fe58b3e470773d7ea937c8c7d8e9de5c75af9558ac19f5c319d9c3120d159f49"
)


def test_map669_receipt_620_proves_identity_bound_consumed_launch() -> None:
    payload = SUMMARY.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == SUMMARY_SHA256
    summary = json.loads(payload)

    assert summary["schema"] == (
        "cata_raid_magmaw_receipt_tagged_progress_replay_summary_v1"
    )
    assert summary["purpose"] == "fixture_expansion_replay"
    assert summary["source"]["worktree_clean_during_run"] is True
    assert summary["admission"]["gameplay_canary_admitted"] is False
    assert summary["admission"]["gameplay_mutations_allowed"] is False
    assert summary["checkpoint"]["all_ready"] is True
    assert summary["checkpoint"]["release_count"] == 1

    receipt = summary["target_observation"]
    assert receipt["receipt_id"] == 620
    assert receipt["planner_complete"] is True
    assert receipt["planner_path_type"] == 1
    assert receipt["planner_control_fingerprint"] == (
        receipt["second_path_control_fingerprint"]
    )
    assert receipt["direct_two_point_selected"] is False
    assert receipt["direct_two_point_fallback"] is False
    assert receipt["motion_master_generator_type"] == 8
    assert receipt["point_generator_initialized"] is True
    assert receipt["spline_launch_succeeded"] is True
    assert receipt["spline_id"] == 7140
    assert receipt["sample_count"] == 10
    assert receipt["same_receipt_id_in_all_samples"] is True
    assert receipt["same_spline_id_in_all_samples"] is True
    assert receipt["endpoint_distance_start"] > receipt["endpoint_distance_end"]
    assert receipt["endpoint_distance_end"] == 0.0
    assert receipt["terminal_outcome"] == "selected_endpoint_reached"
    assert receipt["selected_platform_compatible_all_samples"] is True
    assert receipt["dropped_sample_count"] == 0

    safety = summary["boss_scope_safety_observation"]
    assert safety["unique_receipt_count"] == 25
    assert safety["planner_floor_conflict_count"] == 0
    assert safety["platform_incompatible_sample_count"] == 0
    assert safety["wrong_floor_drop_observed"] is False
    assert "canary122_exact_floor_conflicting_seq745_mechanism_recurred" in (
        summary["claims"]["unproven"]
    )


def test_map669_receipt_56_closes_only_terminal_or_supersession_boundary() -> None:
    payload = RECEIPT_HISTORY_SUMMARY.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == RECEIPT_HISTORY_SUMMARY_SHA256
    summary = json.loads(payload)

    assert summary["schema"] == (
        "cata_raid_magmaw_receipt_history_fixture_expansion_summary_v1"
    )
    assert summary["purpose"] == "fixture_expansion_replay"
    assert summary["source"] == {
        "commit": "78e33e65571c50d3bc336f49b7ecbc5d900fc0dc",
        "tree": "a040bddd189c671646153ce98ed28e36d534f192",
        "worktree_clean_during_run": True,
        "binary_sha256": (
            "a8fdda50e17cd2ff2fc72db03f37db78e5b1ad6c705f1ed45b154e0aeb7f9d16"
        ),
        "configure_ticket_id": "raid-build-6735db63978946f4985f025ffb88c8c8",
        "configure_receipt_canonical_sha256": (
            "ba35eb72a770257190ad5fb6375c88bb562e102e80dcbb0cf25df587888c5eb2"
        ),
        "worldserver_build_ticket_id": (
            "raid-build-7bceafd9517b4d50b518e34e46f6a9cd"
        ),
        "worldserver_build_receipt_canonical_sha256": (
            "a97b3920c5776184b7f322f24e45f2ba6ed4092aa394c8b4e336b248ba65a6ba"
        ),
        "config_sha256": (
            "452b53dc28577737f226fae3b1fcad7fdd41c2b88ffda40fb39bc4911eac39bc"
        ),
        "route_manifest_sha256": (
            "f549cbb99bb1767f00c8a1697d249d2f4bec52b8df3b411b25adad94d94fc8f8"
        ),
        "canonical_identity_sha256": (
            "3fcc1ac268f1a8cbf151fb161b7772a98f5a456557a5cdc36cb932acff4a11c0"
        ),
        "canonical_roster_sha256": (
            "c76f261c8ca3cd86e1f01e06537191d958c1c72ef3aa03a57afd8e803fe48424"
        ),
    }
    assert summary["admission"]["fixture_expansion_target_ids"] == [
        "native_planner_executor_launch_proof_v1"
    ]
    assert summary["admission"]["requested_revision_transition"] == "2_to_3"
    assert summary["admission"]["gameplay_canary_admitted"] is False
    assert summary["admission"]["gameplay_mutations_allowed"] is False

    boundary = summary["required_production_boundary"]
    assert boundary["met"] is True
    assert boundary["fixture_id"] == "native_planner_executor_launch_proof_v1"
    assert boundary["bot_guid"] == 30009
    assert boundary["receipt_id"] == 56
    assert boundary["scope"] == {
        "attempt_id": 1,
        "wipe_generation": 0,
        "route_generation": 2,
        "map": 669,
        "instance": 2,
    }
    assert boundary["planner_complete"] is True
    assert boundary["second_native_path_calculated"] is True
    assert boundary["motion_master_observed"] is True
    assert boundary["point_generator_initialized"] is True
    assert boundary["spline_launch_succeeded"] is True
    assert boundary["spline_id"] == 667
    assert boundary["progress_sample_count"] == 5
    assert boundary["same_receipt_and_spline_across_samples"] is True
    assert boundary["distance_improved"] is True
    assert boundary["terminal"] is True
    assert boundary["terminal_outcome"] == "superseded_by_native_launch"
    assert boundary["superseded_by_receipt_id"] == 58
    assert boundary["dropped_sample_count"] == 0

    assert summary["receipt_history"]["target_receipt_56_complete"] is True
    assert summary["receipt_history"][
        "target_receipt_56_dropped_sample_count"
    ] == 0
    assert summary["causal_classification"]["status"] == (
        "requested_boundary_closed_but_original_cause_not_reproduced"
    )
    assert summary["causal_classification"][
        "original_canary122_wrong_floor_mechanism_proven"
    ] is False
    assert summary["evidence"]["receipt_56_compact_sha256"] == (
        "d98801fa796b3e7d569473b5e6493edff95febd635b0a53fb7e36da6b9ea967b"
    )
    assert summary["evidence"]["receipt_history_boundary_sha256"] == (
        "868549776777b10c23bc9f00e5294f54dc747676b0689cb577306e80d15f9323"
    )
