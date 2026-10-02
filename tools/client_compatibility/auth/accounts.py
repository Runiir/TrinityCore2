"""Login verifiers and hashed expiring tickets in the dedicated lab database."""
import hashlib
import hmac
import secrets
import time

from tools.client_compatibility.lab_runtime import connection
from . import srp

# Cached credentials must outlive a normal play session and permit reconnect.
# Refresh extends a still-valid ticket; expired/revoked credentials never revive.
TICKET_DURATION = 24 * 60 * 60


def migrate():
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS client442_auth.lab_login_accounts (
            native_id INT UNSIGNED PRIMARY KEY, login VARCHAR(128) NOT NULL UNIQUE,
            srp_salt BINARY(32) NOT NULL, srp_verifier VARBINARY(256) NOT NULL) ENGINE=InnoDB""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS client442_auth.lab_login_tickets (
            ticket_hash BINARY(32) PRIMARY KEY, native_id INT UNSIGNED NOT NULL,
            expires BIGINT NOT NULL, mode VARCHAR(16) NOT NULL, INDEX(expires)) ENGINE=InnoDB""")


def native_account(login):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("""SELECT id, username, salt, verifier, locked, last_ip,
            EXISTS(SELECT 1 FROM client442_auth.account_banned b WHERE b.id=a.id AND b.active=1
                AND (b.unbandate>b.bandate AND b.unbandate>UNIX_TIMESTAMP() OR b.unbandate=b.bandate))
            FROM client442_auth.account a WHERE username=%s""", (login.upper(),))
        return cursor.fetchone()


def check_native(login, password):
    account = native_account(login)
    if not account or account[6] or account[4] and account[5] != "127.0.0.1":
        return None
    identity = hashlib.sha1((account[1].upper() + ":" + password.upper()).encode()).digest()
    x = int.from_bytes(hashlib.sha1(account[2] + identity).digest(), "little")
    modulus = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
    calculated = pow(7, x, modulus).to_bytes(32, "little")
    return account if hmac.compare_digest(calculated, account[3]) else None


def provision(login, password):
    account = check_native(login, password)
    if not account:
        raise ValueError("lab native credentials do not match")
    salt = secrets.token_bytes(32)
    value = srp.verifier(account[1], password, salt).to_bytes(256, "big")
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT login FROM client442_auth.lab_login_accounts WHERE native_id=%s", (account[0],))
        if cursor.fetchone():
            return account[0]
        cursor.execute("INSERT INTO client442_auth.lab_login_accounts VALUES (%s,%s,%s,%s)",
                       (account[0], account[1].upper(), salt, value))
    return account[0]


def get(login):
    if not isinstance(login, str) or not 1 <= len(login) <= 128:
        return None
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT native_id,login,srp_salt,srp_verifier FROM client442_auth.lab_login_accounts WHERE login=%s", (login.upper(),))
        row = cursor.fetchone()
    if not row:
        return None
    native = native_account(row[1])
    if not native or native[6] or native[4] and native[5] != "127.0.0.1":
        return None
    return {"id": row[0], "login": row[1], "salt": row[2], "verifier": int.from_bytes(row[3], "big")}


def check_password(login, password):
    account = get(login)
    if not account or not isinstance(password, str) or len(password) > 128:
        return None
    candidate = srp.verifier(account["login"], password, account["salt"]).to_bytes(256, "big")
    return account if hmac.compare_digest(candidate, account["verifier"].to_bytes(256, "big")) else None


def issue(account, mode):
    if mode not in {"launcher", "direct"}:
        raise ValueError("invalid login mode")
    ticket = "TC-" + secrets.token_hex(32).upper()
    digest = hashlib.sha256(ticket.encode()).digest()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM client442_auth.lab_login_tickets WHERE expires<=%s", (int(time.time()),))
        cursor.execute("INSERT INTO client442_auth.lab_login_tickets VALUES (%s,%s,%s,%s)",
                       (digest, account["id"], int(time.time()) + TICKET_DURATION, mode))
    return ticket


def from_ticket(ticket):
    if not isinstance(ticket, str) or not ticket.startswith("TC-") or len(ticket) != 67:
        return None
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("""SELECT a.login,t.mode,t.expires FROM client442_auth.lab_login_tickets t
            JOIN client442_auth.lab_login_accounts a ON a.native_id=t.native_id
            WHERE ticket_hash=%s AND expires>%s""", (hashlib.sha256(ticket.encode()).digest(), int(time.time())))
        row = cursor.fetchone()
    if not row:
        return None
    account = get(row[0])
    if account:
        account.update(mode=row[1], expires=row[2])
    return account


def refresh(ticket):
    account = from_ticket(ticket)
    if not account:
        return None
    now = int(time.time())
    digest = hashlib.sha256(ticket.encode()).digest()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("""UPDATE client442_auth.lab_login_tickets
            SET expires=GREATEST(expires,%s) WHERE ticket_hash=%s AND native_id=%s AND expires>%s""",
            (now + TICKET_DURATION, digest, account['id'], now))
        cursor.execute("""SELECT expires FROM client442_auth.lab_login_tickets
            WHERE ticket_hash=%s AND native_id=%s AND expires>%s""", (digest, account['id'], now))
        row = cursor.fetchone()
    if not row:
        return None
    account['expires'] = row[0]
    return account
