"""Classic's signed instance redirect, using its public development identity."""
from pathlib import Path
import secrets
import struct
import time

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

from . import crypto, joins
from .buffer import Reader, Writer

PENDING = {}
SIGNER = RSA.import_key(Path(__file__).with_name("upstream-development-connect-to.pem").read_bytes())


def redirect(owner):
    for key, (_, expires) in list(PENDING.items()):
        if expires <= time.time(): del PENDING[key]
    key = owner.account_id | 1 << 32 | secrets.randbits(31) << 33
    PENDING[key] = (owner, time.time() + 30)
    where = b"\x01\x7f\x00\x00\x01"
    digest = SHA256.new(where + struct.pack("<IH", 1, joins.PORT))
    signature = pkcs1_15.new(SIGNER).sign(digest)[::-1]
    return signature + where + struct.pack("<HIBQ", joins.PORT, 17, 1, key)


def authenticate(body, challenge):
    r = Reader(body)
    _, key = r.unpack("QQ")
    local, digest = r.raw(32), r.raw(24)
    r.end()
    pending = PENDING.get(key)
    if not pending or pending[1] <= time.time() or pending[0].writer.is_closing():
        raise ValueError("unknown or expired instance continuation")
    owner = pending[0]
    expected = crypto.mac(owner.session_key, struct.pack("<Q", key) + local + challenge + crypto.CONTINUED_SEED)[:24]
    import hmac
    if not hmac.compare_digest(digest, expected):
        raise ValueError("instance authentication proof rejected")
    del PENDING[key]
    return owner, crypto.mac(owner.session_key, local + challenge + crypto.ENCRYPT_SEED)[:32]


def native_login(guid):
    octets = struct.pack("<Q", guid)
    w = Writer()
    for i in [2, 3, 0, 6, 4, 5, 1, 7]:
        w.bits(bool(octets[i]), 1)
    for i in [2, 7, 0, 3, 5, 6, 1, 4]:
        if octets[i]: w.pack("B", octets[i] ^ 1)
    return w.finish()


def native_active_mover(guid):
    octets = struct.pack("<Q", guid)
    w = Writer()
    for i in [7, 2, 1, 0, 4, 5, 6, 3]: w.bits(bool(octets[i]), 1)
    for i in [3, 2, 4, 0, 5, 1, 6, 7]:
        if octets[i]: w.pack("B", octets[i] ^ 1)
    return w.finish()
