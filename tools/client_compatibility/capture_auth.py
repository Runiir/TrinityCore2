"""Checkpoint credential-free modern login evidence with DVCLive and DVC."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import xml.etree.ElementTree as ET

from dvclive import Live

from .lab_runtime import REPO, ROOT, connection, owned_process, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--launcher-screenshot", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    events = [json.loads(line) for line in (ROOT / "logs/modern_auth.jsonl").read_text().splitlines()]
    validated = {}
    for login in [item for item in events if item["event"] == "login_complete"]:
        same = [item for item in events if item.get("session") == login["session"] and item["time"] >= login["time"]]
        realm = next((item for item in same if item["event"] == "realm_request"
            and item.get("command") == "Command_RealmListRequest_v1"), None)
        if realm and any(item["event"] == "rpc_response" and item.get("service") == "utilities"
            and item.get("method") == 1 and item.get("status") == 0 and item["time"] >= realm["time"] for item in same):
            validated[login["mode"]] = {"session": login["session"], "build": login["build"],
                "account_id": login["account_id"], "realm_list_response_success": True}
    if set(validated) != {"launcher", "direct"}:
        raise RuntimeError("both live client login modes have not reached realm discovery")
    client = owned_process("client")
    monitor = json.loads((ROOT / "evidence/client_monitor.json").read_text())
    if not client or client["pid"] != monitor["pid"] or not monitor["second_monitor_verified"]:
        raise RuntimeError("current client monitor receipt does not match the owned process")
    tests = ET.parse(ROOT / "evidence/modern_auth_tests.xml").getroot()
    suites = tests.findall("testsuite")
    test_count = sum(int(suite.attrib["tests"]) for suite in suites)
    if any(int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0)) for suite in suites):
        raise RuntimeError("protocol tests have failures")
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM client442_auth.lab_login_accounts")
        account_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM client442_characters.characters")
        character_count = cursor.fetchone()[0]
        cursor.execute("SELECT gamebuild,port FROM client442_auth.realmlist WHERE id=1")
        world_build, world_port = cursor.fetchone()
    hashes = {str(path.relative_to(REPO)): sha256(path) for path in sorted((REPO / "tools/client_compatibility/auth").rglob("*"))
        if path.is_file() and ".pixi" not in path.parts and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts}
    hashes["tools/client_compatibility/lab_runtime.py"] = sha256(REPO / "tools/client_compatibility/lab_runtime.py")
    hashes["tools/client_compatibility/capture_auth.py"] = sha256(Path(__file__))
    receipt = {"schema": "client442_modern_auth_validation_v1", "client_build": 60895,
        "validated_modes": validated, "protocol_tests_passed": test_count, "native_account_count": account_count,
        "character_count": character_count, "world_build": world_build, "world_port": world_port,
        "world_entry_verified": False, "movement_verified": False, "launcher_url": "http://127.0.0.1:18081/launcher",
        "code_sha256": hashes, "processes": {kind: owned_process(kind) for kind in ["modern_auth", "authserver", "worldserver", "client"]}}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    (out / "modern_auth.jsonl").write_text("\n".join(json.dumps(item) for item in events)+"\n")
    for name in ["modern_auth_setup.json", "auth_negative_checks.json", "launcher_api_check.json", "modern_auth_tests.xml",
                 "direct_login.png", "direct_login_monitor.json", "launcher_login.png", "launcher_login_monitor.json",
                 "web_direct_login.png", "client_monitor.json", "client.png"]:
        shutil.copy2(ROOT / "evidence" / name, out / name)
    shutil.copy2(args.launcher_screenshot, out / "light_launcher.png")
    with Live(dir=str(out / "dvclive"), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        live.log_metric("authentication/direct_realm_list", 1)
        live.log_metric("authentication/launcher_realm_list", 1)
        live.log_metric("validation/protocol_tests_passed", test_count)
        live.log_metric("validation/second_monitor", 1)
        live.log_metric("world/entry_verified", 0)
        live.next_step()
    # Never include prefixes, databases, credentials, registry or ticket payloads.
    secrets = json.loads((ROOT / "secrets/game_account.json").read_text())
    needles = [secrets["password"].encode()]
    runtime = json.loads((ROOT / "secrets/runtime.json").read_text())
    needles.append(runtime["password"].encode())
    for path in out.rglob("*"):
        if path.is_file() and any(needle in path.read_bytes() for needle in needles):
            raise RuntimeError("private credential matched an evidence file")
    archive = REPO / "artifacts/client_harness/442_modern_auth_20261001.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(out, arcname="442_modern_auth_20261001")
    print(json.dumps({"archive": str(archive), "sha256": sha256(archive), "validated_modes": list(validated),
                      "protocol_tests_passed": test_count}, indent=2))


if __name__ == "__main__":
    main()
