"""World authentication, packet integrity and movement ownership boundaries."""
import asyncio
import hashlib
import struct
import time

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15
import pytest

from tools.client_compatibility.world import crypto, instance, movement
from tools.client_compatibility.world.buffer import Reader, Writer, player_high
from tools.client_compatibility.world.service import Session
from types import SimpleNamespace


def client_frame(key, counter, opcode, body=b""):
    payload = struct.pack("<I", opcode) + body
    cipher = AES.new(key, AES.MODE_GCM, nonce=struct.pack("<QI", counter, 0x544E4C43), mac_len=12)
    return cipher.encrypt_and_digest(payload)


def test_packet_integrity_counter_and_direction():
    c = crypto.PacketCrypt(); c.key = bytes(range(32))
    payload, tag = client_frame(c.key, 0, 123, b"payload")
    assert c.decode(payload, tag) == (123, b"payload")
    with pytest.raises(ValueError): c.decode(payload, tag)  # replay
    fresh = crypto.PacketCrypt(); fresh.key = c.key
    with pytest.raises(ValueError): fresh.decode(payload[:-1] + bytes([payload[-1] ^ 1]), tag)
    server = fresh.encode(123, b"payload")
    decrypt = AES.new(c.key, AES.MODE_GCM, nonce=struct.pack("<QI", 0, 0x52565253), mac_len=12)
    assert decrypt.decrypt_and_verify(server[16:], server[4:16]) == struct.pack("<I", 123) + b"payload"
    with pytest.raises(ValueError): crypto.PacketCrypt().decode(payload, tag)


def test_world_build_variant_and_bad_proof():
    key, local, server = bytes(range(64)), bytes(range(32)), bytes(reversed(range(32)))
    proof = crypto.mac(hashlib.sha512(key + crypto.BUILD_KEYS["WoW"]).digest(), local + server + crypto.AUTH_SEED)[:24]
    session, encryption = crypto.derive(key, local, server, proof)
    assert len(session) == 40 and len(encryption) == 32
    with pytest.raises(ValueError): crypto.derive(key, local, server, proof, "WoWC")
    with pytest.raises(ValueError): crypto.derive(key, local, server, bytes(24))


class Output:
    def __init__(self): self.packets = []; self.closed = False
    def write(self, data): self.packets.append(data)
    def is_closing(self): return self.closed
    def close(self): self.closed = True


def test_instance_signed_address_proof_and_replay(monkeypatch):
    instance.PENDING.clear()
    owner = Session(None, Output()); owner.account_id = 1; owner.session_key = bytes(range(40))
    body = instance.redirect(owner)
    signature, where = body[:256], body[256:261]
    port, serial, connection, key = struct.unpack("<HIBQ", body[261:])
    assert where == b"\x01\x7f\x00\x00\x01" and port == 18087 and serial == 17 and connection == 1
    pkcs1_15.new(instance.SIGNER.public_key()).verify(SHA256.new(where + struct.pack("<IH", 1, port)), signature[::-1])
    local, server = bytes(32), bytes([1]) * 32
    prefix = struct.pack("<QQ", 0, key) + local
    with pytest.raises(ValueError): instance.authenticate(prefix + bytes(24), server)
    assert key in instance.PENDING
    digest = crypto.mac(owner.session_key, struct.pack("<Q", key) + local + server + crypto.CONTINUED_SEED)[:24]
    assert instance.authenticate(prefix + digest, server)[0] is owner
    with pytest.raises(ValueError): instance.authenticate(prefix + digest, server)
    instance.PENDING[key] = (owner, time.time() - 1)
    with pytest.raises(ValueError): instance.authenticate(prefix + digest, server)
    instance.PENDING.clear()


def move_body(guid=1, x=-8914.57):
    return Writer().guid(guid, player_high()).pack("IIII6fII", 1, 0, 0, 42, x, -134, 80.5, 5.1, 0, 0, 0, 0).bits(0, 8).finish()


def test_movement_ownership_and_invalid_coordinates():
    state = movement.parse(move_body(), 1)
    assert state["time"] == 42 and state["flags"] == 1
    for body in [move_body(2), move_body(x=float("nan")), move_body(x=18000), move_body()[:-1], move_body() + b"\x00"]:
        with pytest.raises(ValueError): movement.parse(body, 1)
    for name in movement.SUPPORTED:
        native, encoded = movement.encode(name, 1, state)
        assert native == ("CMSG_MOVE_SET_CAN_FLY" if name == "CMSG_MOVE_SET_FLY" else "MSG_" + name.removeprefix("CMSG_")) and encoded


def test_trial83_static_gameobject_contact_preserves_ordinary_owned_movement():
    from tools.client_compatibility.world.objects import INDEX
    body=bytes.fromhex('01a0010408000000000002000000000000b6e64503b60e84c52417a143aa6a06432f88b040000000000000000000000000000000008003bef45d15b34042042c')
    state=movement.parse(body,1)
    guid=(0xF11<<52)|(183380<<32)|24052
    record={'map':530,'fields':{INDEX['GAMEOBJECT_BYTES_1']:5<<8}}
    owner=SimpleNamespace(visible_gameobjects={guid:record})
    movement.validate_standing(owner,state)
    assert state['standing_gameobject'][0]==24052 and state['flags']==state['flags2']==0
    assert state['position'][:3]==pytest.approx([-4225.838867,322.180786,134.416656])
    assert movement.encode('CMSG_MOVE_STOP',1,state)==movement.encode('CMSG_MOVE_STOP',1,{**state,'standing_gameobject':None})
    with pytest.raises(ValueError,match='not visible'):movement.validate_standing(SimpleNamespace(),state)
    record['fields'][INDEX['GAMEOBJECT_BYTES_1']]=15<<8
    with pytest.raises(ValueError,match='transports'):movement.validate_standing(owner,state)


def test_no_movement_before_world_or_from_realm(monkeypatch):
    monkeypatch.setattr("tools.client_compatibility.world.service.event", lambda *a, **k: None)
    owner = Session(None, Output()); owner.crypt.key = bytes(32)
    owner.character = {"guid": 1}; owner.created = False
    with pytest.raises(ValueError): asyncio.run(owner.handle("CMSG_MOVE_START_FORWARD", move_body()))
    owner.created = True
    with pytest.raises(ValueError): asyncio.run(owner.handle("CMSG_MOVE_START_FORWARD", move_body()))


def test_foreign_character_cannot_get_redirect(monkeypatch):
    from tools.client_compatibility.world import characters
    monkeypatch.setattr(characters, "rows", lambda account: [{"guid": 7}])
    s = Session(None, Output()); s.crypt.key = bytes(32); s.account_id = 1
    body = Writer().guid(1, player_high()).pack("f", 1000).finish()
    with pytest.raises(ValueError): asyncio.run(s.handle("CMSG_PLAYER_LOGIN", body))
    assert not s.writer.packets
