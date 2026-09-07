"""Authenticate shared-server launch inputs before any database or server mutation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from tools.raid_program.queued_build import verify_receipt
from tools.raid_program.runtime_asset_closure import require_runtime_asset_closure
from tools.raid_program.shared_instance_fixture import (
    BASE_CONFIG, load_fixture, sha256, validate_shared_config,
)
from tools.raid_program.tracked_runtime_config_derivation import verify_runtime_config_derivation


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def verify_launch(*, source: Path, fixture_path: Path, config: Path,
                  config_receipt: Path, config_receipt_sha256: str,
                  build_receipt: Path, build_policy: Path,
                  coordinator_repository: Path, output_dir: Path) -> dict[str, Any]:
    """Receipts prove the current bytes, not merely a previous successful build."""
    if git(source, "status", "--porcelain=v1"):
        raise ValueError("shared validation requires clean source")
    if output_dir.resolve().is_relative_to(source.resolve()):
        raise ValueError("run evidence must remain outside frozen source")
    commit, tree = git(source, "rev-parse", "HEAD"), git(source, "rev-parse", "HEAD^{tree}")
    for path in (fixture_path, build_policy):
        relative = path.resolve().relative_to(source.resolve()).as_posix()
        tracked = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{relative}"])
        if tracked != path.read_bytes():
            raise ValueError("launch contract is not the tracked source version")
    pair = load_fixture(source, fixture_path)
    config_proof = verify_runtime_config_derivation(
        worktree=source, receipt_path=config_receipt,
        expected_receipt_sha256=config_receipt_sha256,
        contract_relative_path=BASE_CONFIG, expected_source_commit=commit,
        expected_source_tree=tree,
    )
    receipt_config = Path(json.loads(config_receipt.read_text())["destination"]["path"])
    if config.resolve() != receipt_config or config.is_symlink():
        raise ValueError("launch config differs from derived config")
    validate_shared_config(config)
    policy = json.loads(build_policy.read_text())
    verified = verify_receipt(build_receipt, policy)
    if verified.get("gate_bearing") is not True:
        raise ValueError("build receipt cannot admit a live run")
    build = json.loads(build_receipt.read_text())
    if (build.get("commit") != commit or Path(build["worktree"]).resolve() != source.resolve()
            or build.get("classification") != "success"
            or build.get("resource_class") != "worldserver_build"):
        raise ValueError("build receipt does not cover this source and worldserver")
    binaries = [row for row in build.get("output_artifacts", []) if row.get("kind") == "worldserver_elf"]
    if len(binaries) != 1:
        raise ValueError("one built worldserver required")
    binary = Path(binaries[0]["path"])
    if not binary.resolve().is_relative_to(source.resolve()):
        raise ValueError("built binary outside frozen source")
    manifest = source / "experiments/configs/runtime_asset_input_closure_manifest_v1.json"
    data_dir = Path(json.loads((source / BASE_CONFIG).read_text())["typed_inputs"]["data_dir"])
    maps = {pair[role]["expected"].map_id for role in ("subject", "witness")}
    assets = [require_runtime_asset_closure(
        manifest_path=manifest, source_checkout=source, configured_data_dir=data_dir,
        dvc_workspace=coordinator_repository, sealed_bundle=output_dir,
        worldserver_config=config, scenario_map_id=map_id,
    ) for map_id in sorted(maps)]
    return {"schema": "cata_shared_instance_launch_preflight_v1",
            "source_commit": commit, "source_tree": tree,
            "fixture_sha256": pair["fixture_sha256"],
            "config_sha256": sha256(config), "config_derivation": config_proof,
            "build_receipt_sha256": sha256(build_receipt), "build_verification": verified,
            "binary": str(binary), "binary_sha256": sha256(binary),
            "runtime_assets": assets, "live_run_started": False}


def provision_pair(*, source: Path, config: Path, coordinator_repository: Path,
                   output_dir: Path, pair: dict[str, Any]) -> dict[str, Any]:
    """Run only while the coordinator holds its empty-server lifecycle lock."""
    from tools.bot_ml.run_live_bot_validation import prepare_validation_provisioning

    provision = prepare_validation_provisioning(
        output_dir, source / "experiments/configs/validation_provisioning_cata_001.json",
        source / "dataset/validation_gear_profiles/profiles.json", config,
        source / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json", apply=True,
        scenario_ids=[pair[role]["shard"]["scenario_id"] for role in ("subject", "witness")],
    )
    (output_dir / "provisioning.json").write_text(json.dumps(provision, indent=2) + "\n")
    data_dir = json.loads((source / BASE_CONFIG).read_text())["typed_inputs"]["data_dir"]
    readbacks = {}
    for role in ("subject", "witness"):
        selected = pair[role]
        destination = output_dir / f"{role}.database_readback.json"
        command = [sys.executable, "-m", "tools.raid_program.capture_phase1_provisioning_readback",
                   "--worldserver-conf", str(config), "--scenario-id", selected["shard"]["scenario_id"],
                   "--output", str(destination),
                   "--runtime-asset-closure-manifest", str(source / "experiments/configs/runtime_asset_input_closure_manifest_v1.json"),
                   "--runtime-asset-source-checkout", str(source),
                   "--runtime-asset-dvc-workspace", str(coordinator_repository),
                   "--runtime-asset-bundle", str(output_dir),
                   "--runtime-asset-data-dir", str(data_dir),
                   "--runtime-asset-map-id", str(selected["expected"].map_id)]
        with (output_dir / f"{role}.readback.log").open("xb") as log:
            result = subprocess.run(command, cwd=source, stdout=log, stderr=log, timeout=180)
        if result.returncode or not destination.is_file():
            raise ValueError(f"{role} database readback failed")
        readback = json.loads(destination.read_text())
        if readback.get("passed") is not True:
            raise ValueError(f"{role} database readback rejected")
        readbacks[role] = {"path": str(destination), "sha256": sha256(destination),
                           "scenario_id": readback["scenario_id"], "passed": True}
    return {"provisioning": provision, "database_readbacks": readbacks}
