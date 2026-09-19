"""Run isolated exact-300-second class measurements, two at a time on one server."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

from tools.bot_ml.run_live_bot_validation import (
    parse_json_objects, preflight_calibration_reference_binding,
    prepare_bot_pool_reset, prepare_calibration_consumables,
    prepare_calibration_known_spells, prepare_validation_provisioning,
    upsert_trinity_config, write_validation_config,
)
from tools.raid_program.dummy_calibration_batch import run_batch, write
from tools.raid_program.queued_build import verify_receipt
from tools.raid_program.runtime_asset_closure import verify_runtime_asset_closure
from tools.raid_program.shared_instance_console import owned_console, verify_process_binary
from tools.raid_program.shared_instance_fixture import BASE_CONFIG, sha256, validate_shared_config
from tools.raid_program.shared_instance_preparation import git
from tools.raid_program.tracked_runtime_config_derivation import derive_runtime_config

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECS = ["survival_hunter", "fire_mage", "affliction_warlock", "elemental_shaman", "balance_druid"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", action="append", dest="specs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=ROOT / "experiments/configs/cata_raid_build_resource_policy_fast4_v2.json")
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--heartbeat", type=float, default=5)
    parser.add_argument("--attempt-timeout", type=float, default=600)
    args = parser.parse_args()
    specs = args.specs or DEFAULT_SPECS
    if len(specs) != len(set(specs)) or args.seed < 1:
        raise ValueError("unique specs and positive seed required")
    if git(ROOT, "status", "--porcelain=v1"):
        raise ValueError("dummy batch requires clean committed source")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("capture output must be outside source")
    for spec in specs:
        preflight_calibration_reference_binding(calibration_only=True, calibration_mode="single_target_300", target_spec=spec)
    build = json.loads(args.build_receipt.read_text())
    verification = verify_receipt(args.build_receipt, json.loads(args.policy.read_text()))
    commit, tree = git(ROOT, "rev-parse", "HEAD"), git(ROOT, "rev-parse", "HEAD^{tree}")
    if (verification.get("gate_bearing") is not True or build.get("commit") != commit
            or Path(build["worktree"]).resolve() != ROOT or build.get("classification") != "success"):
        raise ValueError("build receipt does not cover current clean source")
    binaries = [r for r in build["output_artifacts"] if r.get("kind") == "worldserver_elf"]
    if len(binaries) != 1:
        raise ValueError("one worldserver artifact required")
    binary = Path(binaries[0]["path"])
    output.mkdir(parents=True, exist_ok=False)
    derivation = derive_runtime_config(worktree=ROOT, contract_relative_path=BASE_CONFIG,
        expected_source_commit=commit, expected_source_tree=tree,
        external_run_root=output, destination_name="base-worldserver.conf")
    config = write_validation_config(Path(derivation["destination"]["path"]), output,
        pool_tag="all_spec_candidate_pool", calibration_only=True,
        calibration_self_provided_baseline=True, autostart=False, console_enabled=True)
    text = config.read_text()
    for key, value in {"MapUpdate.Threads": "1", "BotPolicyModel.Enable": "0",
                       "BotLearning.Enable": "0", "BotLearning.AllowGlobalMemoryFallback": "0",
                       "BotSemantic.UpdateOutcomeStats": "0"}.items():
        text = upsert_trinity_config(text, key, value)
    config.write_text(text)
    validate_shared_config(config)
    catalog = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    report = {"schema": "dummy_calibration_batch_v1", "source_commit": commit, "source_tree": tree,
              "build_receipt": str(args.build_receipt.resolve()), "build_receipt_sha256": sha256(args.build_receipt),
              "binary_sha256": sha256(binary), "config_sha256": sha256(config), "config_derivation": derivation,
              "specs": specs, "seed": args.seed, "concurrency": args.concurrency,
              "cleanup": {}, "performance_accepted": False, "training_eligible": False}

    def prepare() -> None:
        data_dir = Path(json.loads((ROOT / BASE_CONFIG).read_text())["typed_inputs"]["data_dir"])
        assets = verify_runtime_asset_closure(
            manifest_path=ROOT / "experiments/configs/runtime_asset_input_closure_manifest_v1.json",
            source_checkout=ROOT, configured_data_dir=data_dir, dvc_workspace=ROOT,
            sealed_bundle=output, worldserver_config=config, scenario_map_id=0)
        write(output / "runtime-assets.json", assets)
        if not assets["complete"]:
            raise RuntimeError("runtime_asset_closure_incomplete:" + ",".join(sorted(assets["issue_counts"])))
        # Preparation is a barrier before any cohort is started. The canonical
        # candidate pool owns disjoint GUID/item ranges from the raid pools.
        provision = prepare_validation_provisioning(output,
            ROOT / "experiments/configs/validation_provisioning_cata_001.json",
            ROOT / "dataset/validation_gear_profiles/profiles.json", config,
            ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
            apply=True, scenario_ids=["all_spec_candidate_pool"])
        write(output / "provisioning.json", provision)
        write(output / "pool-reset.json", prepare_bot_pool_reset(output, config,
              ["all_spec_candidate_pool"], apply=True))
        for spec in specs:
            folder = output / "preparation" / spec
            folder.mkdir(parents=True)
            prepare_calibration_known_spells(folder, config, spec, catalog,
                                             apply=True, pool_tag="all_spec_candidate_pool")
            prepare_calibration_consumables(folder, config, spec, catalog, apply=True)
        write(output / "batch.json", report)

    try:
        with owned_console(repository=ROOT, source=ROOT, binary=binary, config=config,
                           output_dir=output, before_launch=prepare, lifecycle=report["cleanup"]) as console:
            console.max_response_bytes = 256 * 1024 * 1024
            verify_process_binary(console.process, report["binary_sha256"])
            raw, code, expired = console(".botauto cohorts", 30)
            rows = [r for r in parse_json_objects(raw) if r.get("action") == "botauto_cohorts"]
            if (code or expired or len(rows) != 1 or rows[0].get("ok") is not True
                    or rows[0].get("server_process_id") != console.process.pid
                    or rows[0].get("active_cohort_count") != 0
                    or rows[0].get("max_active_cohorts", 0) < args.concurrency):
                raise RuntimeError("owned native server identity or capacity invalid")
            report["server_epoch"] = rows[0]["server_epoch"]
            report["results"] = run_batch(execute=console, specs=specs, output=output,
                epoch=rows[0]["server_epoch"], run_id="dummy-" + uuid.uuid4().hex[:12],
                seed=args.seed, concurrency=args.concurrency, heartbeat=args.heartbeat,
                timeout=args.attempt_timeout,
                policy_path=ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json")
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write(output / "batch.json", report)
        from dvclive import Live
        with Live(dir=str(output / "dvclive"), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
            live.log_param("source_commit", commit)
            live.log_param("binary_sha256", report["binary_sha256"])
            live.log_param("concurrency", args.concurrency)
            live.log_param("seed", args.seed)
            live.log_metric("performance_accepted", 0)
            live.log_metric("training_eligible", 0)
            for actor in (report.get("results") or {}).get("actors", []):
                for key in ("dps", "hps", "scored_seconds", "capture_accepted",
                            "measurement_completed", "reference_comparable", "diagnostics_complete"):
                    if actor.get(key) is not None:
                        live.log_metric(f"{actor['spec']}/{key}", float(actor[key]))
    return 0 if report["results"]["batch_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
