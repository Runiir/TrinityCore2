"""Classic glue-screen initialization for the lab's disabled optional services."""
import time
from .buffer import Reader, Writer
from tools.client_compatibility.auth.realms import ADDRESS


def initialize(session):
    session.send("SMSG_CACHE_VERSION", Writer().pack("I", 60895).finish())
    session.send("SMSG_AVAILABLE_HOTFIXES", Writer().pack("II", ADDRESS, 0).finish())
    zone = Writer().bits(3, 7).bits(3, 7).bits(3, 7).raw(b"UTCUTCUTC")
    session.send("SMSG_SET_TIME_ZONE_INFORMATION", zone.finish())
    features = Writer().bits(0, 32).bits(1, 11).bits(0, 3)
    features.pack("IIqiII", 0, 0, 0, 10, 0, 0)
    features.pack("iiiiiIii", 0, 0, 3, 3, 3, 0, 0, 0)
    features.pack("hhIIII", 100, 0, 0, 0, 0, 0)
    session.send("SMSG_FEATURE_SYSTEM_STATUS_GLUE_SCREEN", features.finish())


def query(session, body):
    r = Reader(body)
    table, = r.unpack("I")
    count = r.bits(13)
    if count > 1024:
        raise ValueError("excessive DB query")
    records = r.unpack("I" * count)
    r.end()
    for record in records:
        # No Classic hotfix records are provisioned. Explicit Invalid allows
        # client-side data to remain authoritative, unlike a fabricated record.
        reply = Writer().pack("III", table, record, int(time.time())).bits(3, 3).pack("I", 0)
        session.send("SMSG_DB_REPLY", reply.finish())
