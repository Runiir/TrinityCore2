"""Authenticated native sessions keep player ownership in the lab worldserver."""
import asyncio
import hashlib
import secrets
import struct
import zlib

from tools.client_compatibility import lab_runtime as lab
from .buffer import Writer
from .crypto import legacy_crypt
from .events import event, packet
from .opcodes import LEGACY, LEGACY_NAMES

SERVER_HELLO = b"WORLD OF WARCRAFT CONNECTION - SERVER TO CLIENT"
CLIENT_HELLO = b"WORLD OF WARCRAFT CONNECTION - CLIENT TO SERVER"


def authentication(login, key, challenge):
    local = secrets.token_bytes(4)
    digest = hashlib.sha1(login.encode() + bytes(4) + local + challenge + key).digest()
    w = Writer().pack("IIB", 0, 1, 0)
    w.raw(bytes(digest[i] for i in [10, 18, 12, 5])).pack("Q", 0)
    w.raw(bytes(digest[i] for i in [15, 9, 19, 4, 7, 16, 3])).pack("H", 15595)
    w.raw(digest[8:9]).pack("IB", 1, 0)
    w.raw(bytes(digest[i] for i in [17, 6, 0, 1, 11])).raw(local).raw(digest[2:3]).pack("I", 1)
    w.raw(bytes(digest[i] for i in [14, 13])).pack("I", 0)
    w.bits(0, 1).bits(len(login), 12).raw(login.encode())
    return w.finish()


class Native:
    def __init__(self, session):
        self.session = session
        self.reader = self.writer = None
        self.send_crypt = self.recv_crypt = None
        self.inflate = zlib.decompressobj()

    async def connect(self, account_id, login):
        if not lab.owned_process("worldserver"):
            raise RuntimeError("owned native worldserver is absent")
        key = secrets.token_bytes(40)
        self.key, self.login = key, login
        with lab.connection() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE client442_auth.account SET session_key_auth=%s,os='Win',last_ip='127.0.0.1' WHERE id=%s AND username=%s",
                           (key, account_id, login))
            if cursor.rowcount != 1:
                raise ValueError("native account is absent")
        self.reader, self.writer = await asyncio.open_connection("127.0.0.1", 18085)
        size, = struct.unpack(">H", await self.reader.readexactly(2))
        if size != len(SERVER_HELLO) or await self.reader.readexactly(size) != SERVER_HELLO:
            raise ValueError("native world initializer mismatch")
        self.writer.write(struct.pack(">H", len(CLIENT_HELLO)) + CLIENT_HELLO)
        name, body = await self.receive()
        if name != "SMSG_AUTH_CHALLENGE" or len(body) != 37:
            raise ValueError("native challenge mismatch")
        self.send("CMSG_AUTH_SESSION", authentication(login, key, body[32:36]))
        self.send_crypt = legacy_crypt(key, bytes.fromhex("c2b3723cc6aed9b5343c53ee2f4367ce"))
        self.recv_crypt = legacy_crypt(key, bytes.fromhex("cc98ae04e897eaca12ddc09342915357"))
        while True:
            name, body = await self.receive()
            if name == "SMSG_AUTH_RESPONSE":
                if len(body) != 17 or not body[0] & 0x40 or body[16] != 12:
                    raise ValueError("native authentication rejected")
                event("native_authenticated", session=self.session, account_id=account_id)
                return

    def send(self, name, body=b""):
        header = struct.pack(">H", len(body) + 4) + struct.pack("<I", LEGACY[name])
        if self.send_crypt:
            header = self.send_crypt.encrypt(header)
        self.writer.write(header + body)
        if "AUTH" not in name:
            event("native_packet", session=self.session, direction="to_native", name=name, bytes=len(body))
            packet("to_native", name, body)

    async def receive(self):
        raw = await self.reader.readexactly(1)
        first = self.recv_crypt.decrypt(raw)[0] if self.recv_crypt else raw[0]
        raw = await self.reader.readexactly(4 if first & 0x80 else 3)
        tail = self.recv_crypt.decrypt(raw) if self.recv_crypt else raw
        if first & 0x80:
            size = ((first & 0x7F) << 16) | int.from_bytes(tail[:2], "big")
            opcode, = struct.unpack("<H", tail[2:])
        else:
            size = (first << 8) | tail[0]
            opcode, = struct.unpack("<H", tail[1:])
        if size < 2 or size > 1024 * 1024:
            raise ValueError("invalid native frame size")
        body = await self.reader.readexactly(size - 2)
        if opcode & 0x8000:
            expected, = struct.unpack_from("<I", body)
            if expected > 1024 * 1024:
                raise ValueError("native compressed payload too large")
            body = self.inflate.decompress(body[4:], expected + 1)
            if len(body) != expected:
                raise ValueError("native compressed payload size mismatch")
            opcode &= 0x7FFF
        name = LEGACY_NAMES.get(opcode, f"unknown_{opcode:04x}")
        event("native_packet", session=self.session, direction="from_native", name=name, bytes=len(body))
        packet("from_native", name, body)
        return name, body

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
