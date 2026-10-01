"""Modern world transport backed by an authenticated native Trinity session."""
import asyncio
import json
import secrets
import struct

from . import bootstrap, characters, crypto, joins, instance, gameplay, movement, casting, looting, object_queries, movement_controls, transfers
from .buffer import Reader, player_high
from .events import event, packet
from .legacy import Native
from .opcodes import MODERN, MODERN_NAMES

SERVER_HELLO = b"WORLD OF WARCRAFT CONNECTION - SERVER TO CLIENT - V2\n"
CLIENT_HELLO = b"WORLD OF WARCRAFT CONNECTION - CLIENT TO SERVER - V2\n"


class Session:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.id = secrets.token_hex(4)
        self.crypt = crypto.PacketCrypt()
        self.native = Native(self.id)
        self.account_id = None
        self.encrypt_key = None
        self.server_challenge = secrets.token_bytes(32)
        self.owner = self
        self.world = None
        self.character = None
        self.created = False
        self.pump = None

    def send(self, name, body=b""):
        self.writer.write(self.crypt.encode(MODERN[name], body))
        event("modern_packet", session=self.id, direction="to_client", name=name, bytes=len(body))
        packet("to_client", name, body, self.owner.id)

    async def receive(self):
        size, = struct.unpack("<I", await self.reader.readexactly(4))
        if size < 4 or size > 65536:
            raise ValueError("invalid modern frame size")
        tag = await self.reader.readexactly(12)
        opcode, body = self.crypt.decode(await self.reader.readexactly(size), tag)
        name = MODERN_NAMES.get(opcode, f"unknown_{opcode:08x}")
        event("modern_packet", session=self.id, direction="from_client", name=name, bytes=len(body))
        packet("from_client", name, body, self.owner.id)
        return name, body

    async def authenticate(self, body):
        ticket, local, digest = joins.parse_auth(body)
        event("world_auth_packet_parsed", session=self.id)
        variant = {0x576F57: "WoW", 0x576F5743: "WoWC"}.get(json.loads(ticket).get("type"))
        if not variant:
            raise ValueError("unsupported world build variant")
        account_id, login, self.session_key, self.encrypt_key = joins.consume(
            ticket, lambda key: crypto.derive(key, local, self.server_challenge, digest, variant))
        await asyncio.wait_for(self.native.connect(account_id, login), 15)
        self.account_id = account_id
        self.send("SMSG_ENTER_ENCRYPTED_MODE", crypto.enabled_signature(self.encrypt_key))

    async def native_packets(self):
        try:
            while True:
                name, body = await self.native.receive()
                await gameplay.receive(self, name, body)
                if self.world:
                    await self.world.writer.drain()
        except (OSError, ValueError, asyncio.IncompleteReadError) as error:
            event("native_stream_closed", session=self.id, error=str(error))
            self.writer.close()
            if self.world: self.world.writer.close()
        except Exception as error:
            event("native_translation_error", session=self.id, error=type(error).__name__)
            self.writer.close()
            if self.world: self.world.writer.close()

    async def handle(self, name, body):
        if name == "CMSG_AUTH_SESSION" and self.account_id is None:
            return await self.authenticate(body)
        if name == "CMSG_AUTH_CONTINUED_SESSION" and self.account_id is None:
            self.owner, self.encrypt_key = instance.authenticate(body, self.server_challenge)
            self.account_id = self.owner.account_id
            self.send("SMSG_ENTER_ENCRYPTED_MODE", crypto.enabled_signature(self.encrypt_key))
            return
        if name == "CMSG_ENTER_ENCRYPTED_MODE_ACK" and self.encrypt_key and self.crypt.key is None:
            if body:
                raise ValueError("encryption acknowledgement has trailing bytes")
            self.crypt.key = self.encrypt_key
            if self.owner is not self:
                self.owner.world = self
                self.send("SMSG_RESUME_COMMS")
                self.owner.native.send("CMSG_PLAYER_LOGIN", instance.native_login(self.owner.character["guid"]))
                event("instance_authenticated", session=self.id, account_id=self.account_id)
                return
            self.send("SMSG_AUTH_RESPONSE", characters.auth_success())
            self.send("SMSG_TUTORIAL_FLAGS", bytes(32))
            bootstrap.initialize(self)
            event("world_authenticated", session=self.id, account_id=self.account_id)
            self.pump = asyncio.create_task(self.native_packets())
            return
        if not self.crypt.key:
            raise ValueError("request before world authentication")
        if name == "CMSG_PING":
            if len(body) != 8:
                raise ValueError("malformed ping")
            self.send("SMSG_PONG", body[:4])
        elif name in {"CMSG_KEEP_ALIVE", "CMSG_ENABLE_NAGLE", "CMSG_LOG_DISCONNECT"}:
            return
        elif name == "CMSG_ENUM_CHARACTERS":
            self.native.send("CMSG_ENUM_CHARACTERS")
        elif name == "CMSG_DB_QUERY_BULK":
            bootstrap.query(self, body)
        elif name == "CMSG_SERVER_TIME_OFFSET_REQUEST":
            self.send("SMSG_SERVER_TIME_OFFSET", struct.pack("<q", 0))
        elif name == "CMSG_GET_UNDELETE_CHARACTER_COOLDOWN_STATUS":
            from .buffer import Writer
            self.send("SMSG_UNDELETE_COOLDOWN_STATUS_RESPONSE", Writer().bits(0, 1).pack("II", 0, 0).finish())
        elif name == "CMSG_PLAYER_LOGIN":
            r = Reader(body)
            low, high = r.guid()
            r.unpack("f"); r.end()
            if high != player_high() or self.character:
                raise ValueError("invalid or repeated character login")
            self.character = next((c for c in characters.rows(self.account_id) if c["guid"] == low), None)
            if not self.character:
                raise ValueError("character does not belong to authenticated account")
            self.send("SMSG_CONNECT_TO", instance.redirect(self))
        elif name == "CMSG_TIME_SYNC_RESPONSE":
            if len(body) != 8: raise ValueError("invalid time synchronization")
            self.owner.native.send("CMSG_TIME_SYNC_RESP", body)
        elif name == "CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE":
            if not self.owner.created or self is not self.owner.world or len(body) != 4:
                raise ValueError("invalid active mover acknowledgement")
            self.owner.native.send("CMSG_SET_ACTIVE_MOVER", instance.native_active_mover(self.owner.character["guid"]))
            event("native_active_mover_confirmed", session=self.id, guid=self.owner.character["guid"])
        elif name == "CMSG_LOGOUT_REQUEST":
            r = Reader(body); r.bits(1); r.end()
            if not self.owner.created: raise ValueError("logout before world entry")
            self.owner.native.send(name)
        elif name == "CMSG_LOGOUT_CANCEL":
            if body: raise ValueError("invalid logout cancellation")
            self.owner.native.send(name)
        elif name in transfers.CLIENT_NAMES:
            if self is not self.owner.world or not self.owner.character:
                raise ValueError('transfer acknowledgement outside owned world')
            self.owner.native.send(*transfers.request(self.owner,name,body))
        elif name in movement_controls.ACKS:
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("movement acknowledgement before world entry")
            self.owner.native.send(*movement_controls.acknowledgement(self.owner, name, body))
        elif name == "CMSG_CANCEL_MOUNT_AURA":
            if not self.owner.created or self is not self.owner.world or body:
                raise ValueError("invalid dismount request")
            self.owner.native.send(name)
        elif name == "CMSG_CANCEL_AURA":
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("aura cancellation before world entry")
            from . import auras
            self.owner.native.send(name, auras.cancel(self.owner, body))
        elif name in movement.SUPPORTED or name == "CMSG_MOVE_SET_FACING_HEARTBEAT":
            owner = self.owner
            if not owner.created or self is not owner.world:
                raise ValueError("movement before active world entry")
            state = movement.parse(body, owner.character["guid"])
            owner.latest_movement=state['position']
            native_name, native_body = movement.encode("CMSG_MOVE_SET_FACING" if name == "CMSG_MOVE_SET_FACING_HEARTBEAT" else name, owner.character["guid"], state)
            owner.native.send(native_name, native_body)
            event("movement_forwarded", session=self.id, name=name, guid=owner.character["guid"], position=state["position"])
        elif name == "CMSG_SET_ACTION_BUTTON":
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("action bar change before world entry")
            r = Reader(body)
            action, index = r.unpack("IB"); r.end()
            if index >= 144: raise ValueError("action bar slot has no native equivalent")
            from .buffer import Writer
            self.owner.native.send(name, Writer().pack("BI", index, action).finish())
        elif name == "CMSG_QUERY_GAME_OBJECT":
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("object query before world entry")
            self.owner.native.send("CMSG_GAMEOBJECT_QUERY", object_queries.request(self.owner, body))
        elif name in {"CMSG_GAME_OBJ_USE", "CMSG_GAME_OBJ_REPORT_USE", "CMSG_LOOT_ITEM", "CMSG_LOOT_RELEASE", "CMSG_LOOT_MONEY"}:
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("object interaction before world entry")
            for native_name, native_body in looting.request(self.owner, name, body):
                self.owner.native.send(native_name, native_body)
        elif name == "CMSG_CANCEL_CAST":
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("cancel before world entry")
            self.owner.native.send(name, casting.cancel(self.owner, body))
        elif name == "CMSG_CAST_SPELL":
            if not self.owner.created or self is not self.owner.world:
                raise ValueError("cast before world entry")
            try:
                encoded, spell = casting.request(self.owner, body)
            except ValueError as error:
                event("cast_translation_rejected", session=self.id, error=str(error))
                try:
                    failure = casting.rejected(body)
                    if failure is not None: self.send("SMSG_CAST_FAILED", failure)
                except ValueError:
                    pass
                return
            self.owner.native.send(name, encoded)
            event("cast_forwarded", session=self.id, opcode=spell)
        else:
            event("unmapped_client_packet", session=self.id, name=name, bytes=len(body))

    async def run(self):
        event("world_connection", session=self.id)
        self.writer.write(SERVER_HELLO)
        if await asyncio.wait_for(self.reader.readexactly(len(CLIENT_HELLO)), 10) != CLIENT_HELLO:
            raise ValueError("modern world initializer mismatch")
        self.send("SMSG_AUTH_CHALLENGE", secrets.token_bytes(32) + self.server_challenge + b"\x01")
        while True:
            name, body = await asyncio.wait_for(self.receive(), 120)
            await self.handle(name, body)
            await self.writer.drain()


async def connection(reader, writer):
    session = Session(reader, writer)
    try:
        await session.run()
    except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.TimeoutError) as error:
        event("world_connection_closed", session=session.id,
              error=str(error) if type(error) is ValueError else type(error).__name__)
    except Exception as error:
        event("world_connection_error", session=session.id, error=type(error).__name__)
        import traceback
        traceback.print_exc()
    finally:
        if session.pump:
            session.pump.cancel()
            await asyncio.gather(session.pump, return_exceptions=True)
        await session.native.close()
        if session.owner is not session:
            if session.owner.world is session:
                session.owner.writer.close()
        elif session.world:
            session.world.writer.close()
        writer.close()
        await writer.wait_closed()


async def serve():
    server = await asyncio.start_server(connection, "127.0.0.1", joins.PORT)
    event("world_listener", port=joins.PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
