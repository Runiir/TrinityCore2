"""Classic world cryptography derived from pinned TrinityCore, GPL-2.0-or-later.

Reference: 6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2, WorldSocket.cpp,
WorldPacketCrypt.cpp and AuthenticationPackets.cpp. Signing material is the
upstream public development identity, never an account secret.
"""
import hashlib
import hmac
import struct

from Crypto.Cipher import AES, ARC4
from Crypto.Signature import eddsa

AUTH_SEED = bytes.fromhex("de3a2a8e6b895266889d7e7a771d5d1f4ed90c239bcd0edcd2e8043a6864c7b0")
SESSION_SEED = bytes.fromhex("e81e8b5927621eaa861518eac0bf668c6dbf8393bcaa80525b1edc23a012b750")
ENCRYPT_SEED = bytes.fromhex("71c9ed5aa70e4dff4c36a65a3e468a4a5da148c830474adef60d6cbe6fe45573")
CONTINUED_SEED = bytes.fromhex("565c619c483a521f615d0549b29a39bf4b97b01bf96cded6801dab2602a99b9d")
ENABLE_SEED = bytes.fromhex("66be2979eff2d5b56153f65f45ae81cb32ec94ec75b35f446a63436717204434")
ENABLE_CONTEXT = bytes.fromhex("a71fb69bc97cdd96e9bbb821398d5ad4")
DEV_SIGN_KEY = bytes.fromhex("08bdc7a3ccc34f3f6a0bffcf31c1b697691e729a0aab2c77c36f8ae75a9aa7c9")
BUILD_KEYS = {"WoW": bytes.fromhex("5885e3019ae3f51d0227f92c365babd3"),
              "WoWC": bytes.fromhex("0cae464f32d03f1eef0f14b2529907d2")}


def mac(key, data):
    return hmac.digest(key, data, "sha512")


def derive(key_data, local, server, digest, variant="WoW"):
    expected = mac(hashlib.sha512(key_data + BUILD_KEYS[variant]).digest(), local + server + AUTH_SEED)[:24]
    if not hmac.compare_digest(expected, digest):
        raise ValueError("world authentication proof rejected")
    material = mac(hashlib.sha512(key_data).digest(), server + local + SESSION_SEED)
    first, second = hashlib.sha512(material[:32]).digest(), hashlib.sha512(material[32:]).digest()
    session = hashlib.sha512(first + bytes(64) + second).digest()[:40]
    return session, mac(session, local + server + ENCRYPT_SEED)[:32]


def enabled_signature(key):
    signer = eddsa.new(eddsa.import_private_key(DEV_SIGN_KEY), "rfc8032", context=ENABLE_CONTEXT)
    return signer.sign(mac(key, b"\x01" + ENABLE_SEED)) + b"\x80"


class PacketCrypt:
    def __init__(self):
        self.key = None
        self.recv_counter = self.send_counter = 0

    def encode(self, opcode, body):
        payload = struct.pack("<I", opcode) + body
        if self.key:
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=struct.pack("<QI", self.send_counter, 0x52565253), mac_len=12)
            payload, tag = cipher.encrypt_and_digest(payload)
        else:
            tag = bytes(12)
        self.send_counter += 1
        return struct.pack("<I", len(payload)) + tag + payload

    def decode(self, payload, tag):
        if self.key:
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=struct.pack("<QI", self.recv_counter, 0x544E4C43), mac_len=12)
            payload = cipher.decrypt_and_verify(payload, tag)
        elif tag != bytes(12):
            raise ValueError("unexpected integrity tag before encryption")
        self.recv_counter += 1
        if len(payload) < 4:
            raise ValueError("world packet lacks opcode")
        return struct.unpack_from("<I", payload)[0], payload[4:]


def legacy_crypt(key, seed):
    cipher = ARC4.new(hmac.digest(seed, key, "sha1"))
    cipher.decrypt(bytes(1024))
    return cipher
