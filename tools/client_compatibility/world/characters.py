"""Translate character discovery using only the linked native account's rows."""
import time

from tools.client_compatibility.lab_runtime import connection
from tools.client_compatibility.auth.realms import ADDRESS
from .buffer import Writer, player_high


def rows(account_id):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT guid,name,race,class,gender,level,map,zone,position_x,position_y,position_z,orientation,characterFlags,at_login,slot,logout_time FROM client442_characters.characters WHERE account=%s ORDER BY slot,guid", (account_id,))
        keys = [field[0] for field in cursor.description]
        return [dict(zip(keys, row)) for row in cursor.fetchall()]


def enumeration(account_id):
    characters = rows(account_id)
    w = Writer()
    for value in [1, 0, 0, 1, 0, 0, 0, 1, 0]:
        w.bits(value, 1)
    w.pack("IIiIIIII", len(characters), 0, 85, 1, 0, 0, 0, 0)
    for c in characters:
        w.guid(c["guid"], player_high()).pack("IBBBBhI", ADDRESS, c["slot"], c["race"], c["gender"], c["class"], 0, 0)
        w.pack("Bii3fQ", c["level"], c["map"], c["zone"], c["position_x"], c["position_y"], c["position_z"], 0).guid()
        w.pack("IIIBIII", 0, 0, 0, 0, 0, 0, 0)
        w.raw(bytes(22 * 19))
        w.pack("iQi5iIIiI", 0, int(c["logout_time"]), 60895, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        w.bits(len(c["name"].encode()), 6).bits(0, 1).raw(c["name"].encode())
        w.bits(0, 3).pack("III", 0, 0, 0)
    w.pack("i", 1).bits(1, 1).bits(1, 1).bits(0, 3)
    return w.finish()


def auth_success():
    w = Writer().pack("I", 0).bits(1, 1).bits(0, 1)
    w.pack("IIIBBIIIIq", ADDRESS, 1, 0, 3, 3, 0, 1, 0, 0, int(time.time()))
    w.pack("BI", 1, 1).pack("BBBB", 1, 0, 0, 0)
    w.bits(0, 6).pack("III", 0, 0, 0).bits(0, 3)
    name = b"Client442 Lab"
    normalized = b"Client442Lab"
    w.pack("I", ADDRESS).bits(1, 1).bits(0, 1).bits(len(name), 8).bits(len(normalized), 8).raw(name + normalized)
    return w.finish()
