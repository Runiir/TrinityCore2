"""Ordinary owned-session selection and melee attack control."""
from .buffer import Reader, Writer
from .native_objects import guid as native_guid
from .gameobjects import modern_guid

CLIENT_NAMES = {'CMSG_SET_SELECTION', 'CMSG_ATTACK_SWING', 'CMSG_ATTACK_STOP'}


def request(owner, name, body):
    r = Reader(body)
    if name == 'CMSG_ATTACK_STOP':
        r.end()
        return name, b''
    identity = r.guid(); r.end()
    if identity == (0, 0) and name == 'CMSG_SET_SELECTION':
        return name, Writer().pack('Q', 0).finish()
    for guid, record in getattr(owner, 'visible_units', {}).items():
        if modern_guid(guid, record['map']) == identity:
            return name, Writer().pack('Q', guid).finish()
    # Tab selection may race an ordinary creature removal. Reject that target
    # without closing the authenticated world connection.
    return None


def response(owner, name, body):
    if name not in {'SMSG_ATTACK_START', 'SMSG_ATTACK_STOP'}: return None
    r = Reader(body)
    if name == 'SMSG_ATTACK_START':
        attacker, victim = r.unpack('QQ'); dead = None
    else:
        attacker, victim = native_guid(r), native_guid(r)
        dead, = r.unpack('I')
    r.end()
    w = Writer().guid(*modern_guid(attacker, owner.character['map'])).guid(*modern_guid(victim, owner.character['map']))
    if dead is not None: w.bits(bool(dead), 1)
    return name, w.finish()
