"""Owned native mount speed/flight changes and the actual client's acknowledgements."""
import math
from .buffer import Reader, Writer, player_high
from .movement import SEQUENCES, parse, encode

CONTROLS = {
    "SMSG_MOVE_SET_CAN_FLY": "CMSG_MOVE_SET_CAN_FLY_ACK",
    "SMSG_MOVE_UNSET_CAN_FLY": "CMSG_MOVE_SET_CAN_FLY_ACK",
    "SMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY": "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK",
    "SMSG_MOVE_UNSET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY": "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK",
    **{"SMSG_MOVE_SET_" + name: "CMSG_MOVE_FORCE_" + name + "_CHANGE_ACK"
       for name in ["RUN_SPEED", "RUN_BACK_SPEED", "FLIGHT_SPEED", "FLIGHT_BACK_SPEED", "SWIM_SPEED", "SWIM_BACK_SPEED", "WALK_SPEED"]}}
ACKS = set(CONTROLS.values())
SERVER_NAMES = {"SMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY": "SMSG_MOVE_ENABLE_TRANSITION_BETWEEN_SWIM_AND_FLY",
    "SMSG_MOVE_UNSET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY": "SMSG_MOVE_DISABLE_TRANSITION_BETWEEN_SWIM_AND_FLY"}
ACK_NATIVE = {"CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK": "CMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY_ACK"}


def response(owner, name, body):
    if name not in CONTROLS: return None
    r, octets, present, counter, speed = Reader(body), [0] * 8, {}, None, None
    for item in SEQUENCES[name]:
        e = item.removeprefix("MSE")
        if e == "End": break
        if e.startswith("HasGuidByte"): present[int(e[-1])] = r.bits(1)
        elif e.startswith("GuidByte"):
            i = int(e[-1])
            if present[i]: octets[i] = r.unpack("B")[0] ^ 1
        elif e == "Counter": counter, = r.unpack("I")
        elif e == "ExtraElement": speed, = r.unpack("f")
        elif e == "FlushBits": r.align()
        else: raise ValueError("unsupported native movement control")
    r.end()
    if int.from_bytes(bytes(octets), "little") != owner.character["guid"]: return None
    if counter is None or speed is not None and (not math.isfinite(speed) or not 0 < speed <= 100):
        raise ValueError("invalid native movement control")
    if not hasattr(owner, "pending_movement"): owner.pending_movement = {}
    if len(owner.pending_movement) > 64: raise ValueError("unacknowledged movement controls exceed bound")
    owner.pending_movement[counter] = {"ack": CONTROLS[name], "speed": speed}
    w = Writer().guid(owner.character["guid"], player_high()).pack("I", counter)
    if speed is not None: w.pack("f", speed)
    return w.finish()


def acknowledgement(owner, name, body):
    suffix = 8 if "SPEED" in name else 4
    if len(body) < suffix: raise ValueError("truncated movement acknowledgement")
    r = Reader(body[-suffix:])
    counter, = r.unpack("I")
    speed = r.unpack("f")[0] if suffix == 8 else None
    pending = getattr(owner, "pending_movement", {}).get(counter)
    if not pending or pending["ack"] != name or (speed is not None and (not math.isfinite(speed) or abs(speed-pending["speed"]) > .001)):
        raise ValueError("foreign or mismatched movement acknowledgement")
    state = parse(body[:-suffix], owner.character["guid"])
    from .movement import validate_standing
    validate_standing(owner,state)
    state.update(ack_index=counter, ack_speed=speed)
    result = encode(ACK_NATIVE.get(name, name), owner.character["guid"], state, acknowledgement=True)
    del owner.pending_movement[counter]
    return result
