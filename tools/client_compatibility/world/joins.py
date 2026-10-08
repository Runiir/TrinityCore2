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


def verify_schema():
    """Verify the installed join table without issuing DDL or reading secrets."""
    with lab.connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COLUMN_NAME,DATA_TYPE,COLUMN_TYPE,IS_NULLABLE,CHARACTER_MAXIMUM_LENGTH,COLUMN_DEFAULT "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='client442_auth' "
            "AND TABLE_NAME='lab_world_joins' ORDER BY ORDINAL_POSITION")
        rows = cursor.fetchall()
        cursor.execute("SELECT INDEX_NAME,COLUMN_NAME,NON_UNIQUE,SEQ_IN_INDEX FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA='client442_auth' AND TABLE_NAME='lab_world_joins' ORDER BY INDEX_NAME,SEQ_IN_INDEX")
        indexes = cursor.fetchall()
    expected = [('ticket_hash', 'binary', 32), ('native_id', 'int', None), ('key_data', 'binary', 64),
        ('expires', 'bigint', None), ('consumed', 'tinyint', None)]
    if len(rows) != len(expected) or any(tuple(row[i] for i in (0, 1, 4)) != wanted or row[3] != 'NO'
            for row, wanted in zip(rows, expected)) or any('unsigned' not in rows[i][2] for i in (1, 3)) or rows[4][5] != '0':
        raise RuntimeError('existing owned world-join schema differs; migration is refused')
    if list(indexes) != [('expires', 'expires', 1, 1), ('PRIMARY', 'ticket_hash', 0, 1)]:
        raise RuntimeError('existing owned world-join indexes differ; migration is refused')
    return {'schema': 'client442_world_join_existing_schema_v1', 'columns': [row[0] for row in rows],
        'ddl_sent': False, 'mutation_sent': False}


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
