"""Run one Magmaw canary and immediately send its evidence to Jev.

The live runner owns gameplay and watchdog termination.  Jev is invoked only
after the runner closes the output directory, where it receives the compact
native report, combat metrics, combat log, and optional baseline.  Jev never
submits an action or decides whether a code change is promoted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_RUNNER_MODULE = "tools.bot_ml.run_live_bot_validation"
JEV_ANALYZER_MODULE = "tools.bot_ml.analyze_magmaw_trace"
TIMELINE_COMPARATOR_MODULE = "tools.bot_ml.compare_magmaw_timelines"
NATIVE_MUSHROOM_MARKER = "MagmawWildMushroomNative"
DEFAULT_WCL_REFERENCE = Path(
    "experiments/configs/cata_raid_encounters/blackwing_descent/"
    "magmaw_wcl_dps_reference_v1.json"
)
DEFAULT_WCL_TIMELINE_MANIFEST = Path(
    "experiments/configs/cata_raid_encounters/blackwing_descent/"
    "magmaw_wcl_cast_timelines_v1.json"
)
ROUTE_CATALOG_FILES = ("manifest.json", "validation_routes.jsonl")


@dataclass(frozen=True)
class NativeLogSnapshot:
    """Identity and size of a logger file before a live canary starts."""

    device: int
    inode: int
    size: int
    prefix_sha256: str


def _contains_output_dir(arguments: Sequence[str]) -> bool:
    return any(
        argument == "--output-dir" or argument.startswith("--output-dir=")
        for argument in arguments
    )


def build_runner_command(output_dir: Path, runner_args: Sequence[str]) -> list[str]:
    """Build the live-runner command while owning its evidence directory."""
    if _contains_output_dir(runner_args):
        raise ValueError(
            "pass the canary directory as --run-dir; runner arguments must not "
            "override --output-dir"
        )
    return [
        sys.executable,
        "-m",
        LIVE_RUNNER_MODULE,
        "--output-dir",
        str(output_dir),
        *runner_args,
    ]


def build_jev_command(
    *,
    run_dir: Path,
    output: Path,
    ledger: Path | None,
    baseline: Path | None,
    env_file: Path,
    wcl_reference: Path,
    native_log: Path | None,
    run_id: str,
    segment_id: str,
    change_id: str,
    change_note: str,
    scope_route_prefix: str,
    expected_route: Sequence[str],
    timeline_comparison: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        JEV_ANALYZER_MODULE,
        "--input",
        str(run_dir),
        "--output",
        str(output),
        "--env-file",
        str(env_file),
        "--wcl-reference",
        str(wcl_reference),
        "--run-id",
        run_id,
        "--segment-id",
        segment_id,
        "--change-id",
        change_id,
        "--change-note",
        change_note,
        "--scope-route-prefix",
        scope_route_prefix,
    ]
    if ledger is not None:
        command.extend(("--ledger", str(ledger)))
    if baseline is not None:
        command.extend(("--baseline-report", str(baseline)))
    if native_log is not None:
        command.extend(("--native-log", str(native_log)))
    if timeline_comparison is not None:
        command.extend(("--timeline-comparison", str(timeline_comparison)))
    for route_node in expected_route:
        command.extend(("--expected-route-node", route_node))
    return command


def build_timeline_comparison_command(
    *,
    bot_run: Path,
    wcl_manifest: Path,
    output: Path,
) -> list[str]:
    """Build the deterministic all-actor timeline comparison command."""
    return [
        sys.executable,
        "-m",
        TIMELINE_COMPARATOR_MODULE,
        "--bot-run",
        str(bot_run),
        "--wcl-manifest",
        str(wcl_manifest),
        "--output",
        str(output),
    ]


def _runner_argument_value(arguments: Sequence[str], flag: str) -> str | None:
    for index, argument in enumerate(arguments):
        if argument == flag and index + 1 < len(arguments):
            return arguments[index + 1]
        prefix = f"{flag}="
        if argument.startswith(prefix):
            return argument[len(prefix):]
    return None


@contextmanager
def stage_external_route_catalog(arguments: Sequence[str]) -> Iterator[None]:
    """Temporarily align the external validation source with this branch.

    The runtime closure checks the route catalog from the explicit source
    checkout.  A canary may therefore need to stage the branch's two route
    identity files there, but the external checkout is restored byte-for-byte
    after the worldserver exits.
    """
    source_checkout_value = _runner_argument_value(
        arguments, "--runtime-asset-source-checkout"
    )
    scenario_dir_value = _runner_argument_value(
        arguments, "--validation-scenario-dir"
    ) or "dataset/validation_scenarios"
    if not source_checkout_value:
        yield
        return
    source_checkout = Path(source_checkout_value).resolve()
    if source_checkout == REPO_ROOT.resolve():
        yield
        return
    scenario_dir = Path(scenario_dir_value)
    if scenario_dir.is_absolute():
        try:
            relative_scenario_dir = scenario_dir.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            yield
            return
    else:
        relative_scenario_dir = scenario_dir
    branch_route_dir = (REPO_ROOT / relative_scenario_dir).resolve()
    external_route_dir = (source_checkout / relative_scenario_dir).resolve()
    if not branch_route_dir.is_dir() or not external_route_dir.is_dir():
        yield
        return

    originals: dict[Path, tuple[bytes, int] | None] = {}
    staged: list[Path] = []
    try:
        for filename in ROUTE_CATALOG_FILES:
            branch_path = branch_route_dir / filename
            external_path = external_route_dir / filename
            if not branch_path.is_file():
                raise FileNotFoundError(branch_path)
            if external_path.exists():
                originals[external_path] = (
                    external_path.read_bytes(),
                    external_path.stat().st_mode,
                )
            else:
                originals[external_path] = None
            shutil.copyfile(branch_path, external_path)
            os.chmod(
                external_path,
                originals[external_path][1]
                if originals[external_path] is not None
                else branch_path.stat().st_mode,
            )
            staged.append(external_path)
        if staged:
            print(
                "staged branch validation route catalog in external source checkout",
                flush=True,
            )
        yield
    finally:
        for external_path, original in originals.items():
            if original is None:
                try:
                    external_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            contents, mode = original
            external_path.write_bytes(contents)
            os.chmod(external_path, mode)
        if staged:
            print("restored external validation route catalog", flush=True)


def native_log_offset(path: Path) -> int | None:
    """Return the current byte offset before a worldserver starts writing."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def native_log_snapshot(path: Path) -> NativeLogSnapshot | None:
    """Capture enough identity to detect a truncated or rotated logger file."""
    try:
        file_stat = path.stat()
        with path.open("rb") as handle:
            prefix = handle.read(4096)
    except OSError:
        return None
    return NativeLogSnapshot(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        size=file_stat.st_size,
        prefix_sha256=hashlib.sha256(prefix).hexdigest(),
    )


def capture_native_mushroom_log(
    source: Path,
    output: Path,
    start_offset: NativeLogSnapshot | int | None,
) -> bool:
    """Retain only this run's bounded native mushroom records."""
    if not source.exists():
        return False
    current = native_log_snapshot(source)
    if current is None:
        return False
    if start_offset is None:
        offset = 0
    elif isinstance(start_offset, NativeLogSnapshot):
        # Server.log is recreated by the worldserver at startup.  A new file
        # can have the same final size as the previous run, so size alone is
        # insufficient; a shrink/equal-size result is treated as truncation.
        if (
            current.device != start_offset.device
            or current.inode != start_offset.inode
            or current.size <= start_offset.size
            or current.prefix_sha256 != start_offset.prefix_sha256
        ):
            offset = 0
        else:
            offset = start_offset.size
    else:
        offset = 0 if current.size < start_offset else start_offset
    try:
        with source.open("rb") as handle:
            handle.seek(offset)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    lines = [
        line
        for line in text.splitlines()
        if NATIVE_MUSHROOM_MARKER in line
    ]
    if not lines:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _load_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _native_outcome(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {
            "status": "missing_report",
            "certification_status": "unknown",
        }
    evidence = report.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    watchdog = report.get("watchdog_state")
    watchdog = watchdog if isinstance(watchdog, dict) else {}
    completion_reason = str(report.get("completion_reason") or "")
    manifest_complete = bool(evidence.get("manifest_completion_evidence"))
    boss_kill = bool(evidence.get("real_boss_kill_evidence"))
    native_clear = (
        completion_reason == "validation_route_manifest_complete"
        and manifest_complete
        and boss_kill
        and not bool(watchdog.get("all_dead_wiped"))
        and not bool(watchdog.get("death_loop"))
        and not bool(watchdog.get("repeated_decision_loop"))
        and not bool(watchdog.get("no_progress"))
    )
    if native_clear:
        status = "clear"
    elif bool(watchdog.get("all_dead_wiped")):
        status = "wipe"
    elif bool(watchdog.get("death_loop")):
        status = "death_loop"
    elif bool(watchdog.get("repeated_decision_loop")) or bool(
        watchdog.get("no_progress")
    ):
        status = "stalled"
    else:
        status = "incomplete"
    accepted = bool(
        report.get("acceptance_verification", {}).get("accepted") is True
        and report.get("acceptable_final_evidence") is True
        and not report.get("final_evidence_rejections")
    )
    return {
        "status": status,
        "native_clear": native_clear,
        "certification_status": "accepted" if accepted else (
            "uncertified" if native_clear else "rejected"
        ),
        "completion_reason": completion_reason,
    }


def write_status(
    path: Path,
    *,
    run_dir: Path,
    run_id: str,
    change_id: str,
    runner_command: Sequence[str] | None,
    runner_returncode: int | None,
    jev_command: Sequence[str],
    jev_returncode: int,
    jev_report: Path,
    live_report: dict[str, Any] | None,
) -> dict[str, Any]:
    native = _native_outcome(live_report)
    status = {
        "schema_version": 1,
        "tool": "magmaw_jev_canary_runner",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "change_id": change_id,
        "run_dir": str(run_dir),
        "runner": {
            "command": list(runner_command) if runner_command else None,
            "returncode": runner_returncode,
        },
        "native_gameplay_outcome": native,
        "jev": {
            "command": list(jev_command),
            "returncode": jev_returncode,
            "report": str(jev_report),
        },
        "promotion": {
            "status": (
                "eligible_for_human_review"
                if native.get("certification_status") == "accepted"
                and jev_returncode == 0
                else "diagnostic_only"
            ),
            "authority": "native_runtime_and_human_review",
            "reason": (
                "certified native clear with a successful typed JEV review"
                if native.get("certification_status") == "accepted"
                and jev_returncode == 0
                else "native clear/certification or typed JEV review is incomplete"
            ),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="closed canary output directory")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--change-note", default="")
    parser.add_argument("--segment-id", default="magmaw_10n")
    parser.add_argument("--scope-route-prefix", default="bwd.magmaw.")
    parser.add_argument("--expected-route-node", action="append", dest="expected_route", default=[])
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--wcl-reference", type=Path, default=DEFAULT_WCL_REFERENCE)
    parser.add_argument(
        "--wcl-timeline-manifest",
        type=Path,
        default=DEFAULT_WCL_TIMELINE_MANIFEST,
        help="WCL cast timeline manifest used for the all-actor comparison",
    )
    parser.add_argument(
        "--timeline-comparison",
        type=Path,
        help="use this precomputed all-actor timeline comparison",
    )
    parser.add_argument(
        "--native-log-source",
        type=Path,
        default=Path("Server.log"),
        help="worldserver logger file to delta-capture after a live run",
    )
    parser.add_argument(
        "--native-log",
        type=Path,
        help="explicit native mushroom log for --analyze-only",
    )
    parser.add_argument("--jev-report", type=Path)
    parser.add_argument("--status", type=Path)
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="do not start the live runner; analyze the existing --run-dir",
    )
    parser.add_argument(
        "runner_args",
        nargs=argparse.REMAINDER,
        help="arguments for run_live_bot_validation after a -- separator",
    )
    args = parser.parse_args(argv)
    if args.runner_args and args.runner_args[0] == "--":
        args.runner_args = args.runner_args[1:]
    if args.analyze_only and args.runner_args:
        parser.error("--analyze-only cannot be combined with runner arguments")
    if not args.analyze_only and not args.runner_args:
        parser.error("provide live-runner arguments after --, or use --analyze-only")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    runner_command: list[str] | None = None
    runner_returncode: int | None = None
    native_source_offset = None
    native_source = args.native_log_source
    if not native_source.is_absolute():
        native_source = REPO_ROOT / native_source
    if not args.analyze_only:
        native_source_offset = native_log_snapshot(native_source)
    if not args.analyze_only:
        try:
            runner_command = build_runner_command(run_dir, args.runner_args)
        except ValueError as exc:
            print(f"magmaw canary setup failed: {exc}", file=sys.stderr)
            return 2
        print("running Magmaw canary:", " ".join(runner_command), flush=True)
        try:
            with stage_external_route_catalog(args.runner_args):
                completed = subprocess.run(runner_command, cwd=REPO_ROOT, check=False)
        except (OSError, ValueError) as exc:
            print(f"magmaw canary route staging failed: {exc}", file=sys.stderr)
            return 2
        runner_returncode = completed.returncode

    native_log = args.native_log
    if native_log is None and not args.analyze_only:
        captured_native_log = run_dir / "native_mushroom.log"
        if capture_native_mushroom_log(
            native_source,
            captured_native_log,
            native_source_offset,
        ):
            native_log = captured_native_log

    timeline_comparison = args.timeline_comparison
    if timeline_comparison is None and args.wcl_timeline_manifest.exists():
        generated_timeline_comparison = run_dir / "timeline_comparison.json"
        timeline_command = build_timeline_comparison_command(
            bot_run=run_dir,
            wcl_manifest=args.wcl_timeline_manifest,
            output=generated_timeline_comparison,
        )
        print("running deterministic all-actor timeline comparison", flush=True)
        timeline_result = subprocess.run(
            timeline_command,
            cwd=REPO_ROOT,
            check=False,
        )
        if timeline_result.returncode == 0:
            timeline_comparison = generated_timeline_comparison
        else:
            print(
                "timeline comparison unavailable for this run; "
                "continuing with native/JEV evidence",
                file=sys.stderr,
            )

    live_report_path = run_dir / "report.json"
    live_report = _load_object(live_report_path)
    if live_report is None:
        print(f"magmaw canary report missing or invalid: {live_report_path}", file=sys.stderr)
        return 2

    jev_report = args.jev_report or run_dir / "jev_report.json"
    ledger = args.ledger
    jev_command = build_jev_command(
        run_dir=run_dir,
        output=jev_report,
        ledger=ledger,
        baseline=args.baseline_report,
        env_file=args.env_file,
        wcl_reference=args.wcl_reference,
        native_log=native_log,
        run_id=args.run_id,
        segment_id=args.segment_id,
        change_id=args.change_id,
        change_note=args.change_note,
        scope_route_prefix=args.scope_route_prefix,
        expected_route=args.expected_route,
        timeline_comparison=timeline_comparison,
    )
    print("running JEV evidence review", flush=True)
    jev_result = subprocess.run(jev_command, cwd=REPO_ROOT, check=False)
    status_path = args.status or run_dir / "canary_status.json"
    status = write_status(
        status_path,
        run_dir=run_dir,
        run_id=args.run_id,
        change_id=args.change_id,
        runner_command=runner_command,
        runner_returncode=runner_returncode,
        jev_command=jev_command,
        jev_returncode=jev_result.returncode,
        jev_report=jev_report,
        live_report=live_report,
    )
    print(
        "Magmaw canary status="
        f"{status['promotion']['status']} native="
        f"{status['native_gameplay_outcome']['status']} jev_rc={jev_result.returncode} "
        f"status={status_path}"
    )
    if jev_result.returncode != 0:
        return jev_result.returncode
    if runner_returncode not in (None, 0):
        return runner_returncode
    return 0 if status["native_gameplay_outcome"].get("native_clear") else 1


if __name__ == "__main__":
    raise SystemExit(main())
