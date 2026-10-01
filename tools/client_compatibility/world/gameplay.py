"""Native-authoritative character entry packets for the movement trial."""
import time

from .buffer import Reader, Writer, player_high
from .events import event
from . import native_objects, objects


async def receive(owner, name, body):
    if name == "SMSG_ENUM_CHARACTERS_RESULT":
        from .characters import enumeration
        owner.send(name, enumeration(owner.account_id))
        return
    if not owner.world or not owner.character:
        return
    send = owner.world.send
    guid = owner.character["guid"]
    if name == "SMSG_LOGIN_VERIFY_WORLD":
        if len(body) != 20: raise ValueError("invalid native login world")
        send(name, body + bytes(4))
        # Native account-data format is different; modern cache starts empty.
        cache = Writer().guid(guid, player_high()).pack("q", int(time.time())).raw(bytes(8 * 8))
        send("SMSG_ACCOUNT_DATA_TIMES", cache.finish())
        send("SMSG_INITIAL_SETUP", b"\x03\x00")
        send("SMSG_WORLD_SERVER_INFO", Writer().pack("I", 0).bits(0, 5).finish())
    elif name == "SMSG_UPDATE_OBJECT" and not owner.created:
        snapshot = native_objects.find_self(body, guid)
        if snapshot:
            send(name, objects.create(snapshot, owner.character))
            send("SMSG_MOVE_SET_ACTIVE_MOVER", Writer().guid(guid, player_high()).finish())
            send("SMSG_CONTROL_UPDATE", Writer().guid(guid, player_high()).bits(1, 1).finish())
            owner.created = True
            event("native_player_created", session=owner.id, guid=guid, map=snapshot["map"], position=snapshot["movement"]["position"])
    elif name == "SMSG_BIND_POINT_UPDATE":
        if len(body) == 20: send(name, body)
    elif name == "SMSG_TIME_SYNC_REQ":
        send("SMSG_TIME_SYNC_REQUEST", body)
    elif name == "SMSG_LOGIN_SETTIMESPEED":
        r = Reader(body)
        speed, game_time, _, _ = r.unpack("fIII")
        send("SMSG_LOGIN_SET_TIME_SPEED", Writer().pack("IIfII", game_time, game_time, speed, 0, 0).finish())
    elif name == "SMSG_LOGOUT_COMPLETE":
        owner.send(name, b"\x00")
        owner.character, owner.created = None, False
        owner.world = None
    elif name == "SMSG_LOGOUT_RESPONSE":
        if len(body) != 5: raise ValueError("invalid native logout response")
        result, instant = Reader(body).unpack("IB")
        owner.send(name, Writer().pack("i", result).bits(bool(instant), 1).finish())
    elif name == "SMSG_LOGOUT_CANCEL_ACK":
        send(name)
