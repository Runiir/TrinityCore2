"""Captured native mount fields, authoritative speed ACKs and owned aura updates."""
from types import SimpleNamespace
import struct
import pytest
from tools.client_compatibility.world import player_updates, movement_controls, auras, casting, movement
from tools.client_compatibility.world.buffer import Reader, Writer, player_high


def owner():
    return SimpleNamespace(character={"guid": 1, "map": 0, "name": "Harnessone", "gender": 0}, self_snapshot={"fields": {}})


def test_actual_mount_display_update_has_the_unit_mask_and_native_display():
    o = owner()
    native = bytes.fromhex("0000010000000001010300000000000020a0002200000800000831000000214500000000000000000000")
    r = Reader(player_updates.updates(o, native))
    assert r.unpack("HI") == (0, 1)
    assert (r.bits(1), r.bits(1)) == (1, 0)
    size, = r.unpack("I")
    assert size == len(r.data) - r.pos
    assert r.unpack("B") == (0,)
    assert r.guid() == (1, player_high())
    size, = r.unpack("I")
    assert size == len(r.data) - r.pos
    assert r.unpack("BBBI") == (1, 0, 3, 1 << 5)
    assert r.bits(8) == 3  # blocks 0 and 1
    masks = [r.bits(32) for _ in range(2)]
    assert masks[1] & (1 << (52 - 32))
    assert r.unpack("iIi")[2] == 17697
    r.end()
    foreign = owner(); foreign.character["guid"] = 2
    assert player_updates.updates(foreign, native) is None


def status():
    return (Writer().guid(1, player_high()).pack("IIII6fII", 0, 0, 0, 123,
            -10400, -450, 46, 1, 0, 0, 0, 0).bits(0, 8).finish())


def test_actual_mount_run_speed_requires_matching_owned_client_ack():
    o = owner()
    r = Reader(movement_controls.response(o, "SMSG_MOVE_SET_RUN_SPEED", bytes.fromhex("04010000000000604100")))
    assert r.guid() == (1, player_high())
    assert r.unpack("If") == (1, 14)
    r.end()
    name = "CMSG_MOVE_FORCE_RUN_SPEED_CHANGE_ACK"
    with pytest.raises(ValueError): movement_controls.acknowledgement(o, name, status() + struct.pack("If", 1, 100))
    native_name, body = movement_controls.acknowledgement(o, name, status() + struct.pack("If", 1, 14))
    assert native_name == name
    assert body and not o.pending_movement
    with pytest.raises(ValueError): movement_controls.acknowledgement(o, name, status() + struct.pack("If", 1, 14))


def test_owned_mount_aura_uses_cata_single_visual_and_can_be_cancelled():
    o = owner()
    native = casting.packed(Writer(), 1).pack("BiHBB", 0, 32235, 0x19, 85, 0).finish()
    name, body = auras.response(o, "SMSG_AURA_UPDATE", native)
    assert name == "SMSG_AURA_UPDATE"
    r = Reader(body)
    assert (r.bits(1), r.bits(9)) == (0, 1)
    assert r.unpack("B") == (0,)
    assert r.bits(1) == 1
    assert r.guid()[1] >> 58 == 47
    assert r.unpack("iiHIHBi") == (32235, 0, 0x103, 1, 85, 0, 0)
    assert r.bits(17) == 0
    assert r.guid() == (1, player_high())
    r.end()
    assert auras.cancel(o, Writer().pack("I", 32235).guid(1, player_high()).finish()) == struct.pack("I", 32235)
    with pytest.raises(ValueError): auras.cancel(o, Writer().pack("I", 32235).guid(2, player_high()).finish())
    auras.response(o, "SMSG_AURA_UPDATE", casting.packed(Writer(), 1).pack("Bi", 0, 0).finish())
    with pytest.raises(ValueError): auras.cancel(o, Writer().pack("I", 32235).guid().finish())


def test_actual_flight_permission_ack_and_takeoff_status_are_owned():
    o = owner()
    r = Reader(movement_controls.response(o, "SMSG_MOVE_SET_CAN_FLY", bytes.fromhex("100400000000")))
    assert r.guid() == (1, player_high())
    assert r.unpack("I") == (4,)
    r.end()
    ack = bytes.fromhex("01a0010408000080000002000000000000679a3e0056a824c63e01cfc315a249424ed88740000000000000000000000000000000000004000000")
    name, body = movement_controls.acknowledgement(o, "CMSG_MOVE_SET_CAN_FLY_ACK", ack)
    assert name == "CMSG_MOVE_SET_CAN_FLY_ACK" and body
    takeoff = bytes.fromhex("01a00104080000a0010002000000000000c9a53e0056a824c63e01cfc315a249424ed887400000000000000000000000000000000000")
    state = movement.parse(takeoff, 1)
    assert state['flags'] & 0x1000000
    assert movement.encode("CMSG_MOVE_SET_FLY", 1, state)[0] == "CMSG_MOVE_SET_CAN_FLY"
    with pytest.raises(ValueError): movement.parse(takeoff, 2)


def test_flight_water_transition_maps_both_control_and_ack_names():
    o = owner()
    native_name = "SMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY"
    r = Reader(movement_controls.response(o, native_name, bytes.fromhex("100003000000")))
    assert r.guid() == (1, player_high())
    assert r.unpack("I") == (3,)
    r.end()
    assert movement_controls.SERVER_NAMES[native_name] == "SMSG_MOVE_ENABLE_TRANSITION_BETWEEN_SWIM_AND_FLY"
    name, body = movement_controls.acknowledgement(o, "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK", status() + struct.pack("I", 3))
    assert name == "CMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY_ACK" and body


def test_actual_airborne_dismount_ack_preserves_fall_and_maps_extra_flags():
    o = owner()
    movement_controls.response(o, "SMSG_MOVE_UNSET_CAN_FLY", bytes.fromhex("080b00000000"))
    ack = bytes.fromhex("01a0010408000800000081000000000000896c410056a824c63e01cfc30b3a6c424ed8874000000000000000000000000000000000200000000000000080804d9de6beac8f64bf000000000b000000")
    state = movement.parse(ack[:-4], 1)
    assert state['flags'] == 0x800 and state['flags2'] == 0x400
    assert state['fall'] and state['fall_direction']
    name, body = movement_controls.acknowledgement(o, "CMSG_MOVE_SET_CAN_FLY_ACK", ack)
    assert name == "CMSG_MOVE_SET_CAN_FLY_ACK" and body
    wrong = bytearray(ack[:-4]); struct.pack_into('<I', wrong, 5, 0)
    with pytest.raises(ValueError): movement.parse(wrong, 1)
