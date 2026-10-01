"""Checkpoint sanitized startup evidence and frozen binaries, excluding live storage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import time

from dvclive import Live

from .lab_runtime import ROOT, REPO, SOURCE, owned_process, sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.archive.exists():
        raise RuntimeError("capture output already exists")
    processes = {name: owned_process(name) for name in ["authserver", "worldserver", "client"]}
    if not all(processes.values()):
        raise RuntimeError("an owned runtime process has stopped")
    monitor = json.loads((ROOT / "evidence/client_monitor.json").read_text())
    if not monitor["second_monitor_verified"] or monitor["pid"] != processes["client"]["pid"]:
        raise RuntimeError("current client placement on the second monitor is unverified")
    for port in [13306, 13724, 18085, 18086]:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            pass
    # The diagnostic probe must not remain as a pretend login service.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 1119))
    args.output.mkdir(parents=True, mode=0o700)
    passwords = [json.loads((ROOT / "secrets/runtime.json").read_text())["password"],
                 json.loads((ROOT / "secrets/game_account.json").read_text())["password"],
                 (ROOT / "secrets/root_password").read_text().strip()]

    def redacted_copy(source: Path, destination: Path):
        content = source.read_text(errors="replace")
        for password in passwords:
            content = content.replace(password, "<REDACTED>")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    for source in (ROOT / "evidence").iterdir():
        if source.suffix == ".json" or source.name == "client.png":
            shutil.copy2(source, args.output / source.name)
    for directory in ["config", "logs"]:
        for source in (ROOT / directory).rglob("*"):
            if source.is_file():
                redacted_copy(source, args.output / directory / source.relative_to(ROOT / directory))
    client = ROOT / "client/_whitemane-60895_"
    for source in client.glob("launcher-game*log"):
        redacted_copy(source, args.output / "logs/client-launcher" / source.name)
    redacted_copy(client / "WTF/Config.wtf", args.output / "config/client_Config.wtf")
    for name in ["authserver", "worldserver", "launcher-game.exe"]:
        (args.output / "bin").mkdir(exist_ok=True)
        shutil.copy2(ROOT / "bin" / name, args.output / "bin" / name)
    counts = json.loads((ROOT / "evidence/database_runtime_counts.json").read_text())
    transport = json.loads((ROOT / "evidence/login_transport_probe.json").read_text())
    receipt = {
        "schema": "client442_runtime_launch_receipt_v1", "timestamp_unix": time.time(),
        "source_commit_before_runtime_tool_commit": subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "experiment_code_sha256": {str(path.relative_to(REPO)): sha256(path)
            for path in (REPO / "tools/client_compatibility").glob("*.py")},
        "monitor_placement_code_sha256": sha256(REPO / "tools/second_client/place_window.py"),
        "runtime_processes": processes, "loopback_listener_probes_passed": True,
        "client_source_sha256": sha256(SOURCE / "WowClassic.exe"),
        "private_client_sha256": sha256(client / "WowClassic.exe"),
        "native_servers_ready": True, "client_login_screen_verified": True,
        "keyboard_mouse_input_verified": True, "client_authenticated": False,
        "second_monitor_verified": True, "client_monitor": monitor,
        "character_world_entry_verified": False, "character_movement_verified": False,
        "initial_login_error": "BLZ51901016", "modern_login_service_running": False,
        "modern_tls_endpoint_observed": transport["accepted"] and transport["tls_client_hello_record"],
        "startup_repairs": ["clear_desktop_bundled_library_overrides", "host_NVIDIA_Vulkan_ICD",
            "devices_and_proc_in_client_namespace", "Gamescope_outside_client_namespace",
            "direct_pinned_Proton_instead_of_nested_UMU", "private_CASC_write_overlay",
            "IP_only_local_portal", "remove_unnecessary_copied_addons"],
        "failed_intermediate_checks": ["software_GPU_Gamescope_launch", "namespace_GPU_enumeration",
            "namespace_X_socket_ownership", "nested_UMU_launch", "strict_read_only_CASC_startup",
            "legacy_endpoint_client_login", "initial_empty_connect_traces"],
        "boss_database_connected": False, "existing_client_SSO_imported": False,
        "private_credentials_included": False, "live_database_Wine_CASC_storage_included": False,
        "native_schema_baseline": "4.3.4 build 15595", "modern_login_transport_probe": transport,
        "database_counts": counts,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    for file in args.output.rglob("*"):
        if file.is_file() and file.parent.name != "bin" and file.suffix != ".png":
            data = file.read_bytes()
            if any(password.encode() in data for password in passwords):
                raise RuntimeError(f"credential leaked into sanitized evidence: {file.name}")
    with Live(dir=str(args.output / "dvclive"), save_dvc_exp=False, dvcyaml=False) as live:
        for key, value in {"native_servers_ready": 1, "client_login_screen": 1, "local_TLS_connection": 1,
                           "second_monitor_verified": 1, "client_authenticated": 0,
                           "world_entry": 0, "movement_verified": 0}.items():
            live.log_metric(key, value)
        for schema, value in counts.items():
            if isinstance(value, dict) and "tables" in value:
                live.log_metric(f"table_counts/{schema}", value["tables"])
        live.next_step()
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz", compresslevel=3) as archive:
        archive.add(args.output, arcname="442_runtime_launch_20261001")
    print(json.dumps({"archive": str(args.archive), "bytes": args.archive.stat().st_size,
                      "native_servers_ready": True, "client_authenticated": False}, indent=2))


if __name__ == "__main__":
    main()
