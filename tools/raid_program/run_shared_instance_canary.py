"""Run one reviewed two-instance isolation canary on one owned worldserver."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from tools.bot_ml.run_live_bot_validation import CohortCommandExecutor, parse_json_objects
from tools.raid_program.shared_instance_console import owned_console, verify_process_binary
from tools.raid_program.shared_instance_fixture import BASE_CONFIG, load_fixture, sha256
from tools.raid_program.shared_instance_preparation import git, provision_pair, verify_launch
from tools.raid_program.shared_instance_validation import run_shared_instance_validation
from tools.raid_program.tracked_runtime_config_derivation import derive_runtime_config


def write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", default="experiments/configs/cata_shared_instance_fixture_v1.json")
    parser.add_argument("--policy", default="experiments/configs/cata_raid_build_resource_policy_fast4_v2.json")
    args = parser.parse_args()
    source, repository, output = args.source.resolve(), args.repository.resolve(), args.output.resolve()
    if Path(__file__).resolve().parents[2] != source:
        raise ValueError("run the coordinator module from its frozen source checkout")
    common_repository = Path(git(source, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    if repository != common_repository:
        raise ValueError("all shared launches must use the Git common repository lifecycle lock")
    # Generated evidence never dirties source or replaces a prior closed run.
    if output.is_relative_to(source):
        raise ValueError("output must be outside frozen source")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "cata_shared_instance_canary_v1", "run_id": uuid.uuid4().hex,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "live_run_started": False, "isolation_passed": False,
              "boss_completion_eligible": False, "training_eligible": False,
              "terminal_reason": "infrastructure_loss", "cleanup": {"server_started": False}}
    transport = None
    try:
        fixture_path, policy_path = source / args.fixture, source / args.policy
        pair = load_fixture(source, fixture_path)
        commit, tree = git(source, "rev-parse", "HEAD"), git(source, "rev-parse", "HEAD^{tree}")
        config_receipt = derive_runtime_config(
            worktree=source, contract_relative_path=BASE_CONFIG,
            expected_source_commit=commit, expected_source_tree=tree,
            external_run_root=output, destination_name="shared-worldserver.conf",
        )
        config = Path(config_receipt["destination"]["path"])

        def prepare() -> None:
            preflight = verify_launch(
                source=source, fixture_path=fixture_path, config=config,
                config_receipt=Path(config_receipt["receipt_path"]),
                config_receipt_sha256=config_receipt["receipt_sha256"],
                build_receipt=args.build_receipt.resolve(), build_policy=policy_path,
                coordinator_repository=repository, output_dir=output,
            )
            write(output / "launch_preflight.json", preflight)
            report["launch_preflight"] = {"path": "launch_preflight.json",
                                          "sha256": sha256(output / "launch_preflight.json")}
            report["source_commit"] = commit
            report["source_tree"] = tree
            report["binary_sha256"] = preflight["binary_sha256"]
            report["config_sha256"] = preflight["config_sha256"]
            report["provisioning"] = provision_pair(source=source, config=config,
                coordinator_repository=repository, output_dir=output, pair=pair)
            write(output / "canary.json", report)

        # verify_launch checks this artifact path/hash before the child starts.
        build = json.loads(args.build_receipt.read_text())
        binaries = [row for row in build.get("output_artifacts", []) if row.get("kind") == "worldserver_elf"]
        if len(binaries) != 1:
            raise ValueError("one built worldserver required")
        with owned_console(repository=repository, source=source,
                           binary=Path(binaries[0]["path"]), config=config,
                           output_dir=output, before_launch=prepare,
                           lifecycle=report["cleanup"]) as transport:
            report["live_run_started"] = True
            report["server_pid"] = transport.process.pid
            report["runtime_binary_sha256"] = verify_process_binary(
                transport.process, report["binary_sha256"])
            raw, code, timed_out = transport(".botauto cohorts", 30)
            rows = [row for row in parse_json_objects(raw) if row.get("action") == "botauto_cohorts"]
            if (code or timed_out or len(rows) != 1 or rows[0].get("ok") is not True
                    or type(rows[0].get("server_process_id")) is not int
                    or rows[0]["server_process_id"] != transport.process.pid):
                raise ValueError("native responder does not match owned worldserver")
            session = {"server_epoch": rows[0].get("server_epoch"),
                       "server_process_id": transport.process.pid,
                       "server_process_identity_verified": True}
            report["session"] = session
            fixture = pair["fixture"]
            executors = {role: CohortCommandExecutor(transport, pair[role]["expected"].cohort_id,
                         fixture["watchdog"]["transition_timeout_sec"], exclusive=False)
                         for role in ("subject", "witness")}
            result = run_shared_instance_validation(
                fixture=fixture, session=session, coordinator_command=transport,
                executors=executors,
                expectations={role: pair[role]["expected"] for role in executors},
                profile_ids={role: pair[role]["profile"] for role in executors},
                output_path=output / "isolation.json",
            )
            report["isolation"] = result
            report["isolation_passed"] = result.get("isolation_passed") is True
            report["terminal_reason"] = result.get("terminal_reason", "infrastructure_loss")
    except KeyboardInterrupt:
        report["terminal_reason"] = "interruption"
        report["error"] = "operator interruption"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if report["cleanup"].get("server_started"):
            report["live_run_started"] = True
            if report["cleanup"].get("process_return_code") != 0:
                report["isolation_passed"] = False
        report["closed_utc"] = datetime.now(timezone.utc).isoformat()
        write(output / "canary.json", report)
    print(json.dumps({"report": str(output / "canary.json"),
                      "isolation_passed": report["isolation_passed"],
                      "terminal_reason": report["terminal_reason"]}))
    return 0 if report["isolation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
