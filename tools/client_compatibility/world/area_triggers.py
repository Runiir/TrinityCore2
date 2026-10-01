"""Forward real client enter events; native DBC proximity checks stay authoritative.

The 60895 client inherits WPP's V6_0_2 CMSG_AREA_TRIGGER layout. Legacy
15595 has only an ID, so forwarding modern leave events would teleport twice.
"""
from .buffer import Reader, Writer


def request(body):
    r = Reader(body)
    trigger, = r.unpack('I')
    entered, from_client = r.bits(1), r.bits(1)
    r.end()
    if not trigger:
        raise ValueError('invalid area trigger ID')
    return ('CMSG_AREATRIGGER', Writer().pack('I', trigger).finish()) if entered and from_client else None
