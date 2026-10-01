"""Native-authoritative character entry packets for the movement trial."""
import time

from .buffer import Reader, Writer, player_high
from .events import event
from . import native_objects, objects, initialization, casting, gameobjects, currency, looting, object_queries, player_updates, movement_controls, auras, research_updates, units


async def receive(owner, name, body):
    if name == "SMSG_ENUM_CHARACTERS_RESULT":
        from .characters import enumeration
        owner.send(name, enumeration(owner.account_id))
        return
    if not owner.world or not owner.character:
        return
    send = owner.world.send
    guid = owner.character["guid"]
    if name == "SMSG_SPELL_START":
        acknowledgement = casting.prepare(owner, body)
        if acknowledgement is not None: send("SMSG_SPELL_PREPARE", acknowledgement)
    if name == "SMSG_GAMEOBJECT_QUERY_RESPONSE":
        reply = object_queries.response(owner, body)
        if reply is not None: send("SMSG_QUERY_GAME_OBJECT_RESPONSE", reply)
        return
    if name == "SMSG_DESTROY_OBJECT":
        destroyed = gameobjects.destroy(owner, body)
        if destroyed: send("SMSG_UPDATE_OBJECT", destroyed)
        return
    aura = auras.response(owner, name, body)
    if aura is not None:
        send(*aura)
        return
    translated = initialization.translate(name, body)
    if translated is None: translated = movement_controls.response(owner, name, body)
    if translated is None: translated = casting.response(owner, name, body)
    if translated is None: translated = currency.translate(name, body)
    loot_result = looting.response(owner, name, body)
    if loot_result is not None:
        send(*loot_result)
        return
    if translated is not None:
        if name == "SMSG_UPDATE_ACTION_BUTTONS":
            owner.action_buttons = list(Reader(body).unpack("I" * 144)) + [0] * 36
        send(movement_controls.SERVER_NAMES.get(name, name), translated)
    elif name == "SMSG_LOGIN_VERIFY_WORLD":
        if len(body) != 20: raise ValueError("invalid native login world")
        send(name, body + bytes(4))
        # Native account-data format is different; modern cache starts empty.
        cache = Writer().guid(guid, player_high()).pack("q", int(time.time())).raw(bytes(8 * 8))
        send("SMSG_ACCOUNT_DATA_TIMES", cache.finish())
        send("SMSG_INITIAL_SETUP", b"\x03\x00")
        send("SMSG_WORLD_SERVER_INFO", Writer().pack("I", 0).bits(0, 5).finish())
    elif name == "SMSG_UPDATE_OBJECT" and not owner.created:
        snapshot, items = native_objects.player_bundle(body, guid)
        if snapshot:
            owner.self_snapshot = snapshot
            send(name, objects.create(snapshot, owner.character, items, getattr(owner, "action_buttons", None)))
            send("SMSG_MOVE_SET_ACTIVE_MOVER", Writer().guid(guid, player_high()).finish())
            send("SMSG_CONTROL_UPDATE", Writer().guid(guid, player_high()).bits(1, 1).finish())
            owner.created = True
            event("native_player_created", session=owner.id, guid=guid, map=snapshot["map"], position=snapshot["movement"]["position"])
            visible = gameobjects.updates(owner, body)
            if visible: send(name, visible)
            creatures = units.updates(owner, body)
            if creatures: send(name, creatures)
    elif name == "SMSG_UPDATE_OBJECT":
        player = player_updates.updates(owner, body)
        if player: send(name, player)
        research = research_updates.updates(owner, body)
        if research: send(name, research)
        visible = gameobjects.updates(owner, body)
        if visible: send(name, visible)
        creatures = units.updates(owner, body)
        if creatures: send(name, creatures)
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
