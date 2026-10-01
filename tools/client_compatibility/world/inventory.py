"""Native-owned inventory identities and create records for Classic."""
import struct
from .buffer import Writer, player_high
from .fields import serialize
from .objects import INDEX


def modern_guid(native):
    if not native: return 0, 0
    high = native >> 48
    if high == 0x4000: return native & 0xFFFFFFFF, (3 << 58) | (1 << 42)
    if high == 0: return native, player_high()
    raise ValueError("unsupported inventory GUID type")


def inventory_slots(fields):
    slots = [(0, 0)] * 146
    start = INDEX["PLAYER_FIELD_INV_SLOT_HEAD"]
    for old in range(86):
        new = old if old < 19 else old + 11 if old < 23 else old + 12 if old < 39 else old + 20
        native = fields.get(start + old * 2, 0) | fields.get(start + old * 2 + 1, 0) << 32
        slots[new] = modern_guid(native)
    return slots


def item_block(snapshot):
    fields = snapshot["fields"]
    value = lambda name, offset=0: fields.get(INDEX[name] + offset, 0)
    pair = lambda name: modern_guid(value(name) | value(name, 1) << 32)
    entry = value("OBJECT_FIELD_ENTRY")
    w = Writer().pack("B", 1).guid(*modern_guid(snapshot["guid"])).pack("B", snapshot["kind"])
    w.bits(0, 19).pack("I", 0)  # inventory items have no position/movement fragment
    data = Writer().pack("B", 1).raw(bytes([0, 1] + ([2] if snapshot["kind"] == 2 else []) + [255, 1]))
    serialize(data, "ObjectData", {"EntryID": entry, "Scale": struct.unpack("<f", struct.pack("<I", value("OBJECT_FIELD_SCALE_X")))[0]}, 1)
    signed = lambda n: n - 2**32 if n >= 2**31 else n
    item = {"Owner": pair("ITEM_FIELD_OWNER"), "ContainedIn": pair("ITEM_FIELD_CONTAINED"),
            "Creator": pair("ITEM_FIELD_CREATOR"), "GiftCreator": pair("ITEM_FIELD_GIFTCREATOR"),
            "StackCount": value("ITEM_FIELD_STACK_COUNT"), "Expiration": value("ITEM_FIELD_DURATION"),
            "DynamicFlags": value("ITEM_FIELD_FLAGS"), "Durability": value("ITEM_FIELD_DURABILITY"),
            "MaxDurability": value("ITEM_FIELD_MAXDURABILITY"), "CreatePlayedTime": value("ITEM_FIELD_CREATE_PLAYED_TIME"),
            "PropertySeed": signed(value("ITEM_FIELD_PROPERTY_SEED")), "RandomPropertiesID": signed(value("ITEM_FIELD_RANDOM_PROPERTIES_ID")),
            "ItemBonusKey": {"ItemID": entry}}
    item["SpellCharges"] = [signed(value("ITEM_FIELD_SPELL_CHARGES", i)) for i in range(5)]
    item["Enchantment"] = [{"ID": value("ITEM_FIELD_ENCHANTMENT_1_1", i * 3),
                            "Duration": value("ITEM_FIELD_ENCHANTMENT_1_1", i * 3 + 1),
                            "Charges": value("ITEM_FIELD_ENCHANTMENT_1_1", i * 3 + 2) & 65535} for i in range(13)]
    serialize(data, "ItemData", item, 1)
    if snapshot["kind"] == 2:
        serialize(data, "ContainerData", {"NumSlots": value("CONTAINER_FIELD_NUM_SLOTS"),
                  "Slots": [modern_guid(value("CONTAINER_FIELD_SLOT_1", i * 2) |
                  value("CONTAINER_FIELD_SLOT_1", i * 2 + 1) << 32) for i in range(36)]}, 1)
    w.pack("I", len(data.finish())).raw(data.finish())
    return w.finish()
