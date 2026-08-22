from __future__ import annotations

from pathlib import Path

import pytest

from tools.raid_program import raid_workloop
from tools.raid_program import wowsims_reference_workspace as workspace


def test_workspace_status_matches_control_plane() -> None:
    receipt = workspace.status(workspace.ROOT)
    control = raid_workloop.wowsims_status(workspace.ROOT)

    assert receipt["schema"] == "wowsims_reference_workspace_receipt_v1"
    assert receipt["observation"]["promotion_states"] == control[
        "promotion_states"
    ]
    assert receipt["observation"]["reference_count"] == control[
        "accepted_reference_count"
    ]
    assert receipt["state"] in {
        "locally_verified",
        "remote_requires_hydration",
    }


def test_workspace_hydration_unit_matches_local_state() -> None:
    status = raid_workloop.wowsims_status()
    if status["workspace_state"] == "locally_verified":
        assert status["required_hydration_work_unit"] is None
        return

    work_unit = status["required_hydration_work_unit"]
    assert work_unit["work_unit"] == (
        "wowsims:hydrate:current_promoted_reference_cohort"
    )
    assert work_unit["target_count"] == 16
    assert work_unit["commands"]["hydrate_and_verify"].endswith(
        "wowsims_reference_workspace hydrate"
    )
    assert work_unit["commands"]["evict_after_use"].endswith(
        "wowsims_reference_workspace evict"
    )


def test_pointer_metadata_is_derived_from_the_tracked_dvc_pointer() -> None:
    pointer, _ = workspace._safe_paths(workspace.ROOT)
    metadata = workspace._pointer_metadata(pointer)

    assert metadata["digest"] == raid_workloop.wowsims_status()[
        "dvc_bundle_digest"
    ]
    assert metadata["nfiles"] > 0
    assert metadata["size"] > 0


def test_safe_paths_rejects_a_symlinked_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = Path("artifacts/reference.dvc")
    bundle = Path("artifacts/reference")
    (tmp_path / pointer).parent.mkdir(parents=True)
    (tmp_path / pointer).write_text("outs: []\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / bundle).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(workspace, "POINTER", pointer)
    monkeypatch.setattr(workspace, "BUNDLE", bundle)

    with pytest.raises(
        workspace.WorkspaceError, match="bundle_symlink_forbidden"
    ):
        workspace._safe_paths(tmp_path)


def test_hydration_rejects_unbounded_dvc_parallelism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workspace, "_safe_paths", lambda root: (root, root))

    with pytest.raises(workspace.WorkspaceError, match="dvc_jobs_out_of_range"):
        workspace.hydrate(workspace.ROOT, jobs=9)
