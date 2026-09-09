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
    monkeypatch.setattr(raid_workloop, "current_reference_cohort",
                        lambda root: {"pointer": pointer, "bundle": bundle})

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


@pytest.fixture
def promoted_workspace(tmp_path, monkeypatch):
    import json
    import hashlib

    bundle = Path("artifacts/reference/current_cohort")
    pointer = bundle.with_suffix(".dvc")
    def write(path, document):
        path = tmp_path / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))
        return {"path": path.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "byte_count": path.stat().st_size}
    catalog = {"reference_class": "self_provided_baseline", "requests": [
        {"target_spec": f"spec_{i}", "request_sha256": str(i)} for i in range(16)]}
    pending = raid_workloop._canonical_sha256(raid_workloop.pending_catalog_projection(catalog))
    domain = {"bundle_root": bundle.as_posix(), "dvc_pointer_path": pointer.as_posix(),
              "pending_request_catalog_sha256": pending,
              "repository_url": "test", "repository_revision": "b"*40,
              "control_plane_policy": "commit_a_pointer_then_commit_b_reconstruction_receipt_and_promotion"}
    entries = []
    for row in catalog["requests"]:
        generation = {"target_spec": row["target_spec"], "request_catalog_sha256": pending,
                      "result_observation": {"dps": 123}}
        digest = hashlib.sha256(json.dumps(generation).encode()).hexdigest()
        descriptor = write(bundle / "generation_receipts" / f"{digest}.json", generation)
        entries.append({"target_spec": row["target_spec"], **descriptor})
        row["result"] = {"status": "generated_verified", "publication_domain": dict(domain),
                         "artifacts": {"generation_receipt": descriptor}}
    files = list((tmp_path / bundle).rglob("*.json"))
    (tmp_path / pointer).write_text(f"outs:\n- md5: {'a'*32}.dir\n  size: {sum(p.stat().st_size for p in files)}\n  nfiles: 16\n  path: {bundle.name}\n")
    reconstruction = write(Path("artifacts/control/rebuilt.json"), {
        "schema": "wowsims_dvc_reconstruction_receipt_v1", "status": "published_and_freshly_reconstructed",
        "dvc_target": pointer.as_posix(),
        "bundle_root": bundle.as_posix(), "repository_url": "test", "repository_revision": "b"*40,
        "dvc_pointer": {"path": pointer.as_posix(), "bundle_root": bundle.as_posix(),
                        "sha256": raid_workloop._file_sha256(tmp_path / pointer),
                        "out": {"digest": "a"*32 + ".dir"}},
        "generation_receipts": entries})
    old_rebuilt = tmp_path / reconstruction["path"]
    named_rebuilt = old_rebuilt.with_name(reconstruction["sha256"] + ".json")
    old_rebuilt.rename(named_rebuilt)
    reconstruction["path"] = named_rebuilt.relative_to(tmp_path).as_posix()
    for row in catalog["requests"]:
        row["result"]["artifacts"]["dvc_reconstruction_receipt"] = reconstruction
    write(raid_workloop.WOWSIMS_REQUESTS_PATH, catalog)
    # A plausible old pointer and index must never become fallback authority.
    (tmp_path / "artifacts/reference/old.dvc").write_text("outs: []")
    monkeypatch.setattr(raid_workloop, "roster_status", lambda root: {
        "dps_targets": [row["target_spec"] for row in catalog["requests"]]})
    return tmp_path, bundle, pointer, catalog, write


def test_current_cohort_drives_status_candidates_and_workspace_operations(promoted_workspace, monkeypatch):
    import subprocess

    root, bundle, pointer, _, _ = promoted_workspace
    status = raid_workloop.wowsims_status(root)
    assert status["accepted_reference_count"] == status["current_candidate_count"] == 16
    assert workspace.status(root)["bundle"] == bundle.as_posix()
    calls = []
    monkeypatch.setattr(workspace, "_dvc_command", lambda root, *args:
                        calls.append(args) or subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(workspace, "_run", lambda *args, **kwargs: None)
    assert workspace.hydrate(root, jobs=2)["dvc_pointer"] == pointer.as_posix()
    assert calls[0] == ("pull", "--jobs", "2", pointer.as_posix())
    assert calls[1] == ("status", "--cloud", pointer.as_posix())
    receipt = workspace.evict(root)  # Only the synthetic temporary bundle.
    assert receipt["bundle"] == bundle.as_posix()
    assert not (root / bundle).exists()
    assert (root / "artifacts/reference/old.dvc").exists()
    assert raid_workloop.wowsims_status(root)["required_hydration_work_unit"]["dvc_pointer"] == pointer.as_posix()


@pytest.mark.parametrize("damage", ["mixed", "missing", "pending_hash", "traversal", "duplicate", "pointer_missing", "all_pending", "pointer_symlink", "reconstruction_missing", "generation_outside"])
def test_invalid_current_cohort_never_falls_back_or_runs_dvc(promoted_workspace, monkeypatch, damage):
    root, bundle, pointer, catalog, write = promoted_workspace
    row = catalog["requests"][0]
    if damage == "mixed": row["result"]["publication_domain"]["repository_revision"] = "old"
    if damage == "missing": del row["result"]["artifacts"]["generation_receipt"]
    if damage == "pending_hash": row["result"]["publication_domain"]["pending_request_catalog_sha256"] = "old"
    if damage == "traversal": row["result"]["publication_domain"]["bundle_root"] = "artifacts/../outside"
    if damage == "duplicate": row["target_spec"] = catalog["requests"][1]["target_spec"]
    if damage == "pointer_missing": (root / pointer).unlink()
    if damage == "all_pending": catalog = raid_workloop.pending_catalog_projection(catalog)
    if damage == "pointer_symlink":
        moved = (root / pointer).with_suffix(".saved")
        (root / pointer).rename(moved)
        (root / pointer).symlink_to(moved)
    if damage == "reconstruction_missing":
        (root / row["result"]["artifacts"]["dvc_reconstruction_receipt"]["path"]).unlink()
    if damage == "generation_outside":
        row["result"]["artifacts"]["generation_receipt"]["path"] = "artifacts/old/" + row["result"]["artifacts"]["generation_receipt"]["sha256"] + ".json"
    write(raid_workloop.WOWSIMS_REQUESTS_PATH, catalog)
    status = raid_workloop.wowsims_status(root)
    assert status["accepted_reference_count"] == 0
    assert status["required_hydration_work_unit"] is None
    monkeypatch.setattr(workspace, "_dvc_command", lambda *a, **k: pytest.fail("DVC must not run"))
    with pytest.raises(workspace.WorkspaceError, match="current_reference_cohort"):
        workspace.hydrate(root, jobs=2)
