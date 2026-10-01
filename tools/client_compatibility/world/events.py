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
    if name in {'CMSG_DB_QUERY_BULK', 'SMSG_DB_REPLY', 'SMSG_AVAILABLE_HOTFIXES', 'CMSG_HOTFIX_REQUEST', 'SMSG_HOTFIX_MESSAGE', 'SMSG_HOTFIX_CONNECT'}:return True
    if 'NPC_TEXT' in name:return True
    if any(token in name for token in ['TAXI','GOSSIP','TELEPORT','TRANSFER','NEW_WORLD','TOKEN','WORLD_PORT','WORLDPORT','AREA_TRIGGER']):return True
    return name.startswith(("CMSG_MOVE_", "MSG_MOVE_", "SMSG_MOVE_")) or name in {
        "CMSG_GAME_OBJ_USE", "CMSG_GAME_OBJ_REPORT_USE", "CMSG_GAMEOBJ_USE", "CMSG_GAMEOBJ_REPORT_USE",
        "CMSG_LOOT_ITEM", "CMSG_LOOT_CURRENCY", "CMSG_AUTOSTORE_LOOT_ITEM", "CMSG_LOOT_RELEASE",
        "SMSG_LOOT_RESPONSE", "SMSG_LOOT_REMOVED", "SMSG_CURRENCY_LOOT_REMOVED", "SMSG_LOOT_RELEASE",
        "SMSG_SETUP_CURRENCY", "SMSG_SET_CURRENCY",
        "SMSG_AURA_UPDATE", "SMSG_AURA_UPDATE_ALL", "CMSG_CANCEL_AURA", "CMSG_CANCEL_MOUNT_AURA",
        "CMSG_QUERY_GAME_OBJECT", "SMSG_QUERY_GAME_OBJECT_RESPONSE", "CMSG_GAMEOBJECT_QUERY", "SMSG_GAMEOBJECT_QUERY_RESPONSE",
        "CMSG_QUERY_CREATURE", "CMSG_CREATURE_QUERY", "SMSG_CREATURE_QUERY_RESPONSE", "SMSG_QUERY_CREATURE_RESPONSE",
        "SMSG_SEND_KNOWN_SPELLS", "SMSG_UPDATE_ACTION_BUTTONS", "SMSG_SET_PROFICIENCY", "SMSG_SEND_UNLEARN_SPELLS",
        "CMSG_CAST_SPELL", "SMSG_SPELL_PREPARE", "SMSG_SPELL_START", "SMSG_SPELL_GO", "SMSG_CAST_FAILED", "SMSG_SPELL_FAILURE", "SMSG_SPELL_FAILED_OTHER", "CMSG_CANCEL_CAST", "CMSG_SET_ACTION_BUTTON",
        "CMSG_SET_ACTIVE_MOVER", "CMSG_ENUM_CHARACTERS", "SMSG_ENUM_CHARACTERS_RESULT", "CMSG_PLAYER_LOGIN",
        "SMSG_UPDATE_OBJECT", "SMSG_DESTROY_OBJECT", "SMSG_LOGIN_VERIFY_WORLD", "SMSG_BIND_POINT_UPDATE", "SMSG_CONTROL_UPDATE",
        "CMSG_TIME_SYNC_RESP", "CMSG_TIME_SYNC_RESPONSE", "SMSG_TIME_SYNC_REQ", "SMSG_TIME_SYNC_REQUEST",
        "CMSG_LOGOUT_REQUEST", "CMSG_LOGOUT_CANCEL", "SMSG_LOGOUT_RESPONSE", "SMSG_LOGOUT_COMPLETE", "SMSG_LOGOUT_CANCEL_ACK"}


def packet(direction, name, body, session=None):
    if not capture_packet(name): return
    path = ROOT / "evidence/world_packets.jsonl"
    if path.exists() and path.stat().st_size > 16 * 1024 * 1024:
        return
    with LOCK, path.open("a") as handle:
        os.chmod(path, 0o600)
        handle.write(json.dumps({"time": time.time(), "session": session, "direction": direction,
                                 "name": name, "body": body.hex()}) + "\n")
