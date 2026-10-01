"""Checkpoint the isolated world-entry and native-authoritative movement trial."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET

from dvclive import Live

from .lab_runtime import REPO, ROOT, owned_process, sha256
from .world.events import capture_packet


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    world = [json.loads(line) for line in (ROOT / "logs/modern_world.jsonl").read_text().splitlines()]
    auth = [json.loads(line) for line in (ROOT / "logs/modern_auth.jsonl").read_text().splitlines()]
    modes = {}
    for entry in [e for e in world if e["event"] == "native_player_created"]:
        authenticated = next(e for e in world if e["event"] == "world_authenticated" and e["session"] == entry["session"])
        logins = [e for e in auth if e["event"] == "login_complete" and e["account_id"] == authenticated["account_id"]
                  and authenticated["time"] - 600 < e["time"] <= authenticated["time"]]
        if logins:
            login = max(logins, key=lambda e: e["time"])
            modes[login["mode"]] = {"auth_session": login["session"], "world_session": entry["session"],
                                    "account_id": authenticated["account_id"], "guid": entry["guid"], "time": entry["time"]}
    if set(modes) != {"direct", "launcher"}:
        raise RuntimeError("both authentication modes have not entered the native world")
    trial = json.loads((ROOT / "evidence/movement_trial.json").read_text())
    records = {r["label"]: r for r in trial["records"]}
    before, turned, forward, landed, stopped = [records[k] for k in ["before", "turn", "forward", "jump_landed", "stopped"]]
    distance = math.dist(turned["native"]["position"][:2], forward["native"]["position"][:2])
    rotation = abs(turned["native"]["orientation"] - before["native"]["orientation"])
    if distance < 1 or rotation < .1 or math.dist(landed["native"]["position"], stopped["native"]["position"]) > .01:
        raise RuntimeError("native forward/turn/stop acceptance failed")
    for r in trial["records"]:
        if not r["addon"]["in_world"] or r["addon"]["dead"] or r["addon"]["speed"] != 0:
            raise RuntimeError("addon stopped/alive observation failed")
        if abs(r["addon"]["facing_radians"] - r["native"]["orientation"]) > .002:
            raise RuntimeError("addon and native facing differ")
    actions = [e for e in world if e["event"] == "movement_forwarded" and before["time"] <= e["time"] <= stopped["time"]]
    if not {"CMSG_MOVE_JUMP", "CMSG_MOVE_HEARTBEAT", "CMSG_MOVE_FALL_LAND"} <= {e["name"] for e in actions}:
        raise RuntimeError("jump/heartbeat/land were not captured")
    direct = json.loads((ROOT / "evidence/direct_movement.json").read_text())
    if direct["native_before"] == direct["native_after"]:
        raise RuntimeError("direct login did not move the native character")
    tests = ET.parse(ROOT / "evidence/world_protocol_tests.xml").getroot().findall("testsuite")
    if not tests or any(int(t.attrib.get("errors", 0)) + int(t.attrib.get("failures", 0)) for t in tests):
        raise RuntimeError("world regression tests are absent or failing")
    monitor = json.loads((ROOT / "evidence/client_monitor.json").read_text())
    current = owned_process("client")
    if not current or current["pid"] != monitor["pid"] or not monitor["second_monitor_verified"]:
        raise RuntimeError("current second-monitor placement is unverified")
    roots = [REPO / "tools/client_compatibility/world", REPO / "tools/client_compatibility/observation",
             REPO / "tools/client_compatibility/auth"]
    hashes = {str(path.relative_to(REPO)): sha256(path) for root in roots for path in root.rglob("*")
              if path.is_file() and not {".pixi", "__pycache__", ".pytest_cache"} & set(path.parts)}
    for name in ["lab_runtime.py", "capture_world.py"]:
        hashes[f"tools/client_compatibility/{name}"] = sha256(REPO / "tools/client_compatibility" / name)
    receipt = {"schema": "client442_world_movement_validation_v1", "client_build": 60895,
        "native_build": 15595, "worktree": str(REPO), "branch": "codex/442-compatibility-audit",
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "validated_modes": modes, "world_entry_verified": True, "native_movement_verified": True,
        "addon_observation_verified": True, "forward_distance": distance, "turn_radians": rotation,
        "stop_displacement": math.dist(landed["native"]["position"], stopped["native"]["position"]),
        "jump_packets_verified": True, "protocol_tests_passed": sum(int(t.attrib["tests"]) for t in tests),
        "code_sha256": hashes, "native_worldserver_sha256": sha256(ROOT / "bin/worldserver"),
        "processes": {name: owned_process(name) for name in ["worldserver", "modern_world", "modern_auth", "client"]},
        "full_gameplay_compatibility": False, "archaeology_verified": False,
        "known_missing": ["NPC/items/gameobjects and ongoing value updates", "spell/action bars and combat", "archaeology", "transport/vehicle/spline translation"],
        "repaired_intermediate_failures": ["native auth column and initializer", "WoW versus WoWC build proof",
            "native character flag column", "unanswered DB queries", "missing race/class unlock declaration",
            "missing native active mover acknowledgement", "pytest module-name collision", "persisted US portal after SSO"]}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    for name in ["movement_trial.json", "direct_movement.json", "world_protocol_tests.xml", "client_monitor.json",
                 "movement_before.png", "movement_turn.png", "movement_forward.png", "movement_jump_air.png",
                 "movement_jump_landed.png", "movement_stopped.png", "direct_movement.png", "logout_trial.png"]:
        shutil.copy2(ROOT / "evidence" / name, out / name)
    with (out / "world_packets.jsonl").open("w") as safe:
        for line in (ROOT / "evidence/world_packets.jsonl").open():
            if capture_packet(json.loads(line)["name"]): safe.write(line)
    (out / "modern_world.jsonl").write_text("\n".join(json.dumps(e) for e in world) + "\n")
    # The auth logger records safe metadata only. Never capture client logs,
    # database rows containing verifiers/keys, TLS keys, tickets or registries.
    (out / "modern_auth.jsonl").write_text("\n".join(json.dumps(e) for e in auth) + "\n")
    with Live(dir=str(out / "dvclive"), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        for key, value in {"world_entry/direct": 1, "world_entry/launcher": 1, "movement/native_forward_distance": distance,
                           "movement/native_turn_radians": rotation, "movement/stop_displacement": 0,
                           "movement/jump_packets": 1, "observation/addon": 1, "monitor/second": 1,
                           "validation/protocol_tests_passed": receipt["protocol_tests_passed"]}.items():
            live.log_metric(key, value)
        live.next_step()
    needles = [json.loads((ROOT / f"secrets/{name}").read_text())["password"].encode()
               for name in ["runtime.json", "game_account.json"]]
    needles.append((ROOT / "secrets/root_password").read_text().strip().encode())
    for path in out.rglob("*"):
        if path.is_file() and any(needle in path.read_bytes() for needle in needles):
            raise RuntimeError("private credential matched evidence")
    archive = REPO / "artifacts/client_harness/442_world_movement_20261001.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(out, arcname="442_world_movement_20261001")
    print(json.dumps({"archive": str(archive), "world_entry_modes": list(modes), "forward_distance": distance,
                      "protocol_tests_passed": receipt["protocol_tests_passed"]}, indent=2))


if __name__ == "__main__":
    main()
