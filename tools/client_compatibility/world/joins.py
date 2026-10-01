"""Short-lived world-join secrets confined to the owned authentication schema."""
import hashlib
import json
import secrets
import time

from tools.client_compatibility import lab_runtime as lab
from .buffer import Reader

PORT = 18087


def migrate():
    with lab.connection() as conn, conn.cursor() as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS client442_auth.lab_world_joins (
            ticket_hash BINARY(32) PRIMARY KEY, native_id INT UNSIGNED NOT NULL,
            key_data BINARY(64) NOT NULL, expires BIGINT UNSIGNED NOT NULL,
            consumed BOOLEAN NOT NULL DEFAULT FALSE, INDEX (expires))""")


def ready():
    return bool(lab.owned_process("modern_world") and lab.owned_process("worldserver"))


def issue(account, client_secret, client_info):
    variant = {key: client_info.get(key) for key in ["platformType", "clientArch", "type"]}
    if variant["platformType"] != 0x57696E or variant["clientArch"] != 0x783634 or variant["type"] not in {0x576F57, 0x576F5743}:
        raise ValueError("unsupported world build variant")
    server_secret = secrets.token_bytes(32)
    ticket = json.dumps({"gameAccount": account["login"], "platform": variant["platformType"],
                         "clientArch": variant["clientArch"], "type": variant["type"],
                         "labNonce": secrets.token_hex(16)}, separators=(",", ":")).encode()
    with lab.connection() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM client442_auth.lab_world_joins WHERE expires<%s", (int(time.time()),))
        cursor.execute("INSERT INTO client442_auth.lab_world_joins(ticket_hash,native_id,key_data,expires) VALUES(%s,%s,%s,%s)",
                       (hashlib.sha256(ticket).digest(), account["id"], client_secret + server_secret, int(time.time()) + 60))
    return ticket, server_secret


def parse_auth(body):
    reader = Reader(body)
    dos, region, group, realm = reader.unpack("QIII")
    local, digest = reader.raw(32), reader.raw(24)
    ipv6 = reader.bits(1)
    size, = reader.unpack("I")
    if size > 4096 or region != 1 or group != 1 or realm != 1:
        raise ValueError("invalid realm authentication identity")
    ticket = reader.raw(size)
    reader.end()
    return ticket, local, digest


def consume(ticket, verify):
    digest = hashlib.sha256(ticket).digest()
    with lab.connection() as conn, conn.cursor() as cursor:
        conn.begin()
        cursor.execute("SELECT native_id,key_data,expires,consumed FROM client442_auth.lab_world_joins WHERE ticket_hash=%s FOR UPDATE", (digest,))
        row = cursor.fetchone()
        if not row or row[2] <= time.time() or row[3]:
            conn.rollback()
            raise ValueError("expired, unknown or consumed world ticket")
        # Invalid proofs do not consume somebody else's valid ticket.
        session_key, encrypt_key = verify(row[1])
        cursor.execute("SELECT username FROM client442_auth.account WHERE id=%s", (row[0],))
        login, = cursor.fetchone()
        if json.loads(ticket)["gameAccount"] != login:
            conn.rollback()
            raise ValueError("world ticket account mismatch")
        from tools.client_compatibility.auth.accounts import get
        if not get(login):
            conn.rollback()
            raise ValueError("world account banned, locked or absent")
        cursor.execute("UPDATE client442_auth.lab_world_joins SET consumed=TRUE WHERE ticket_hash=%s", (digest,))
        conn.commit()
    return row[0], login, session_key, encrypt_key
