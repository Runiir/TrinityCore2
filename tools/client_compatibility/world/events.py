"""Bounded world diagnostics; authentication bodies and secret keys are excluded."""
import json
import os
import threading
import time

from tools.client_compatibility.lab_runtime import ROOT

LOCK = threading.Lock()


def event(kind, **fields):
    allowed = {"session", "opcode", "name", "bytes", "status", "account_id", "error", "port", "direction", "guid", "map", "position"}
    if not set(fields) <= allowed:
        raise ValueError("unreviewed world diagnostic fields")
    record = {"time": time.time(), "event": kind, **fields}
    path = ROOT / "logs/modern_world.jsonl"
    with LOCK:
        if not path.exists() or path.stat().st_size < 16 * 1024 * 1024:
            with path.open("a") as handle:
                os.chmod(handle.name, 0o600)
                handle.write(json.dumps(record) + "\n")
    if kind not in {"modern_packet", "native_packet"}:
        print(json.dumps(record), flush=True)


def capture_packet(name):
    return name.startswith(("CMSG_MOVE_", "MSG_MOVE_", "SMSG_MOVE_")) or name in {
        "CMSG_SET_ACTIVE_MOVER", "CMSG_ENUM_CHARACTERS", "SMSG_ENUM_CHARACTERS_RESULT", "CMSG_PLAYER_LOGIN",
        "SMSG_UPDATE_OBJECT", "SMSG_LOGIN_VERIFY_WORLD", "SMSG_BIND_POINT_UPDATE", "SMSG_CONTROL_UPDATE",
        "CMSG_TIME_SYNC_RESP", "CMSG_TIME_SYNC_RESPONSE", "SMSG_TIME_SYNC_REQ", "SMSG_TIME_SYNC_REQUEST",
        "CMSG_LOGOUT_REQUEST", "CMSG_LOGOUT_CANCEL", "SMSG_LOGOUT_RESPONSE", "SMSG_LOGOUT_COMPLETE", "SMSG_LOGOUT_CANCEL_ACK"}


def packet(direction, name, body):
    if not capture_packet(name): return
    path = ROOT / "evidence/world_packets.jsonl"
    if path.exists() and path.stat().st_size > 16 * 1024 * 1024:
        return
    with LOCK, path.open("a") as handle:
        os.chmod(path, 0o600)
        handle.write(json.dumps({"time": time.time(), "direction": direction,
                                 "name": name, "body": body.hex()}) + "\n")
