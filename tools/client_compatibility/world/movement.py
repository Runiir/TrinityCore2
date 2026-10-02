"""Convert ordinary Classic player movement into native 15595 bit sequences."""
import json
import math
from pathlib import Path
import struct

from .buffer import Reader, Writer, player_high

SEQUENCES = json.loads(Path(__file__).with_name("native_movement.json").read_text())["sequences"]
SUPPORTED = {"CMSG_MOVE_" + name for name in (
    "START_FORWARD", "START_BACKWARD", "STOP", "START_STRAFE_LEFT", "START_STRAFE_RIGHT",
    "STOP_STRAFE", "START_TURN_LEFT", "START_TURN_RIGHT", "STOP_TURN", "JUMP", "FALL_LAND",
    "HEARTBEAT", "SET_FACING", "SET_PITCH", "SET_RUN_MODE", "SET_WALK_MODE", "START_PITCH_UP",
    "START_PITCH_DOWN", "STOP_PITCH", "START_SWIM", "STOP_SWIM",
    "START_ASCEND", "START_DESCEND", "STOP_ASCEND", "SET_FLY")}


def modern_flags2(native):
    return (native & 0x3f) | (0x100 if native & 0x400 else 0)


def parse(body, wanted):
    r = Reader(body)
    if r.guid() != (wanted, player_high()):
        raise ValueError("movement GUID is not the active player")
    flags, flags2, flags3, timestamp = r.unpack("IIII")
    x, y, z, o, pitch, elevation = r.unpack("6f")
    forces, index = r.unpack("II")
    if forces > 16: raise ValueError("excessive movement forces")
    for _ in range(forces): r.guid()
    presence = [r.bits(1) for _ in range(8)]
    # Modern swim/flight transition moved from native bit 10 to bit 8.
    # Terrain-normal and turn-while-falling flags have no native wire field.
    # Whitemane's observed 0x8000 falling hint is accepted only with actual fall
    # data; it cannot grant flight or bypass the server's movement authority.
    allowed_extra = 0x3f | 0x100 | 0x200 | 0x400 | 0x8000
    if any(presence[i] for i in (1, 3, 6, 7)) or flags3 or flags >= 1 << 30 or flags2 & ~allowed_extra:
        raise ValueError("unsupported movement transport/spline/advanced flags")
    if flags2 & 0x8000 and not (flags & 0x800 and presence[2]):
        raise ValueError("falling movement hint without fall state")
    flags2 = (flags2 & 0x3f) | (0x400 if flags2 & 0x100 else 0)
    m = {"flags": flags, "flags2": flags2, "time": timestamp, "position": (x, y, z, o),
         "pitch": pitch, "fall": bool(presence[2]), "fall_direction": False,
         "fall_time": 0, "zspeed": 0, "sin": 0, "cos": 0, "xyspeed": 0,'standing_gameobject':None}
    if presence[0]:
        identity=r.guid()
        if not identity[0] or identity[1]>>58!=11:raise ValueError('standing movement identity is not a game object')
        m['standing_gameobject']=identity
    if presence[2]:
        m["fall_time"], m["zspeed"] = r.unpack("If")
        m["fall_direction"] = bool(r.bits(1))
        if m["fall_direction"]: m["sin"], m["cos"], m["xyspeed"] = r.unpack("3f")
    r.end()
    if not all(math.isfinite(v) for v in (x, y, z, o, pitch, elevation, m["zspeed"], m["xyspeed"])) or max(abs(x), abs(y), abs(z)) > 17067:
        raise ValueError("invalid movement coordinates")
    return m


def validate_standing(owner,state):
    """Consume static-object contact metadata without granting transport motion."""
    identity=state.get('standing_gameobject')
    if identity is None:return
    from .gameobjects import modern_guid
    from .objects import INDEX
    for guid,record in getattr(owner,'visible_gameobjects',{}).items():
        if modern_guid(guid,record['map'])!=identity:continue
        kind=record['fields'][INDEX['GAMEOBJECT_BYTES_1']]>>8&255
        if kind in [11,15]:raise ValueError('standing movement on transports is unsupported')
        return
    raise ValueError('standing game object is not visible to the owned character')


def encode(name, guid, m, *, acknowledgement=False):
    native = "CMSG_MOVE_SET_CAN_FLY" if name == "CMSG_MOVE_SET_FLY" else name if acknowledgement else "MSG_" + name.removeprefix("CMSG_")
    if (not acknowledgement and name not in SUPPORTED) or native not in SEQUENCES:
        raise ValueError("unsupported movement opcode")
    octets = struct.pack("<Q", guid)
    flags, flags2 = m["flags"], m["flags2"]
    pitch = bool(flags & (0x200000 | 0x1000000) or flags2 & 0x10)
    present = {"MovementFlags": bool(flags), "MovementFlags2": bool(flags2),
               "Timestamp": True, "Orientation": abs(m["position"][3]) > 1e-6,
               "Pitch": pitch, "SplineElevation": False}
    values = {"Timestamp": ("I", m["time"]), "Orientation": ("f", m["position"][3]),
              "Pitch": ("f", m["pitch"]), "FallTime": ("I", m["fall_time"]),
              "FallVerticalSpeed": ("f", m["zspeed"]), "FallSinAngle": ("f", m["sin"]),
              "FallCosAngle": ("f", m["cos"]), "FallHorizontalSpeed": ("f", m["xyspeed"])}
    w = Writer()
    for element in SEQUENCES[native]:
        e = element.removeprefix("MSE")
        if e == "End": break
        if e == "FlushBits": w.flush()
        elif e.startswith("HasGuidByte"): w.bits(bool(octets[int(e[-1])]), 1)
        elif e.startswith("GuidByte"):
            value = octets[int(e[-1])]
            if value: w.pack("B", value ^ 1)
        elif e in {"ZeroBit", "HasTransportData", "HasSpline", "HasHeightChangeFailed"}: w.bits(0, 1)
        elif e == "Counter" and acknowledgement: w.pack("I", m["ack_index"])
        elif e == "ExtraElement" and acknowledgement: w.pack("f", m["ack_speed"])
        elif "Transport" in e or e == "HasVehicleId": continue
        elif e == "HasFallData": w.bits(m["fall"], 1)
        elif e == "HasFallDirection":
            if m["fall"]: w.bits(m["fall_direction"], 1)
        elif e.startswith("Has") and e[3:] in present: w.bits(not present[e[3:]], 1)
        elif e == "MovementFlags":
            if flags: w.bits(flags, 30)
        elif e == "MovementFlags2":
            if flags2: w.bits(flags2, 12)
        elif e.startswith("Position"): w.pack("f", m["position"]["XYZ".index(e[-1])])
        elif e == "SplineElevation": continue
        elif e in values:
            if e.startswith("Fall"):
                if not m["fall"] or e in {"FallSinAngle", "FallCosAngle", "FallHorizontalSpeed"} and not m["fall_direction"]: continue
            elif not present[e]: continue
            w.pack(*values[e])
        else: raise ValueError("unsupported movement sequence element: " + e)
    return native, w.finish()
