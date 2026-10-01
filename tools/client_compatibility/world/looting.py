"""Normal game-object use and loot, bounded to the native visible object/session."""
from .buffer import Reader, Writer
from . import gameobjects


def loot_guid(native, map_id):
    return native & 0xFFFFFFFF, (15 << 58) | (1 << 42) | (map_id << 29)


def response(owner, name, body):
    if name == "SMSG_LOOT_RESPONSE":
        r = Reader(body)
        native, reason = r.unpack("QB")
        record = getattr(owner, "visible_gameobjects", {}).get(native)
        if not record: return None
        world_guid = gameobjects.modern_guid(native, record["map"])
        identity = loot_guid(native, record["map"])
        failure = r.unpack("B")[0] if not reason else 17
        coins, items, currencies = r.unpack("IBB") if reason else (0, 0, 0)
        w = Writer().guid(*world_guid).guid(*identity).pack("BBBBIII", failure, reason, 0, 2, coins, items, currencies)
        w.bits(bool(reason), 1).bits(0, 2).flush()
        slots = {}
        for _ in range(items):
            slot, item, quantity, display, seed, prop, ui = r.unpack("BIIiiiB")
            slots[slot] = "CMSG_AUTOSTORE_LOOT_ITEM"
            w.bits(0, 2).bits(ui, 3).bits(0, 1).flush()
            w.pack("iii", item, seed, prop).bits(0, 1).flush().bits(0, 6).flush()
            w.pack("IBB", quantity, 0, slot)
        for _ in range(currencies):
            slot, kind, quantity = r.unpack("BII")
            slots[slot] = "CMSG_LOOT_CURRENCY"
            w.pack("IIB", kind, quantity, slot).bits(0, 3).flush()
        r.end()
        owner.loot = {"native": native, "guid": identity, "owner": world_guid, "slots": slots}
        return "SMSG_LOOT_RESPONSE", w.finish()
    loot = getattr(owner, "loot", None)
    if not loot: return None
    if name in {"SMSG_LOOT_REMOVED", "SMSG_CURRENCY_LOOT_REMOVED"}:
        r = Reader(body); slot, = r.unpack("B"); r.end()
        loot["slots"].pop(slot, None)
        return "SMSG_LOOT_REMOVED", Writer().guid(*loot["owner"]).guid(*loot["guid"]).pack("B", slot).finish()
    if name == "SMSG_LOOT_RELEASE":
        r = Reader(body); native, success = r.unpack("QB"); r.end()
        if native != loot["native"]: raise ValueError("foreign loot release")
        owner.loot = None
        return name, Writer().guid(*loot["guid"]).guid(*loot["owner"]).finish()
    return None


def request(owner, name, body):
    if name in {"CMSG_GAME_OBJ_USE", "CMSG_GAME_OBJ_REPORT_USE"}:
        native = gameobjects.owned_native(owner, body)
        return [(name.replace("GAME_OBJ", "GAMEOBJ"), Writer().pack("Q", native).finish())]
    if name not in {"CMSG_LOOT_ITEM", "CMSG_LOOT_RELEASE", "CMSG_LOOT_MONEY"}: return None
    loot = getattr(owner, "loot", None)
    if not loot: raise ValueError("loot action without a native loot window")
    r, requests = Reader(body), []
    if name == "CMSG_LOOT_ITEM":
        count, = r.unpack("I")
        if count > 100: raise ValueError("loot requests exceed bound")
        seen = set()
        for _ in range(count):
            identity, slot = r.guid(), r.unpack("B")[0]
            if identity != loot["guid"] or slot not in loot["slots"] or slot in seen:
                raise ValueError("foreign/duplicate loot slot")
            seen.add(slot)
            requests.append((loot["slots"][slot], bytes([slot])))
        r.bits(1)
    elif name == "CMSG_LOOT_RELEASE":
        if r.guid() not in {loot["guid"], loot["owner"]}: raise ValueError("foreign loot release")
        requests.append((name, Writer().pack("Q", loot["native"]).finish()))
    else:
        r.bits(1); requests.append((name, b""))
    r.end()
    return requests
