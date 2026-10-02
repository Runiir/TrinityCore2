"""TLS Battle.net connection, account login and realm discovery services."""
import asyncio
import os
import secrets
import time

from . import accounts, realms, wire
from .events import event

HASHES = {0x65446991: "connection", 0x2782094B: "connection", 0x0DECFC01: "auth",
          0xFF5A6AC3: "auth", 0x62DA0891: "account", 0x1E4DC42F: "account",
          0x3FC1274D: "utilities", 0x51923A28: "utilities"}


class Session:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.id = secrets.token_hex(4)
        self.account = None
        self.ticket = ""
        self.build = 0
        self.client_secret = None
        self.client_info = None
        self.next_token = 0
        self.bindings = {}

    def send_request(self, service_hash, method, payload):
        self.writer.write(wire.request(service_hash, method, self.next_token, payload))
        self.next_token += 1

    def logon(self, ticket):
        try:
            ticket = ticket.decode("ascii")
        except UnicodeError:
            return 3
        account = accounts.from_ticket(ticket)
        if not account:
            self.account = None
            self.ticket = ""
            event("login_rejected", session=self.id, status=3)
            return 3
        self.account, self.ticket = account, ticket
        result = wire.message("authentication.v1.LogonResult", error_code=0, session_key=secrets.token_bytes(64))
        result.account_id.high, result.account_id.low = 0x100000000000000, account["id"]
        game = result.game_account_id.add()
        game.high, game.low = 0x200000200576F57, account["id"]
        self.send_request(0x71240E35, 5, result)
        event("login_complete", session=self.id, mode=account["mode"], account_id=account["id"], build=self.build)
        return 0

    def dispatch(self, service, method, body):
        if service == "connection":
            if method == 1:
                request = wire.message("connection.v1.ConnectRequest", body)
                result = wire.message("connection.v1.ConnectResponse", server_time=int(time.time()*1000),
                                      use_bindless_rpc=request.use_bindless_rpc)
                result.server_id.label, result.server_id.epoch = os.getpid(), int(time.time())
                if request.HasField("client_id"):
                    result.client_id.CopyFrom(request.client_id)
                return 0, result
            if method == 5:
                return 0, b""
            if method == 7:
                self.send_request(0x65446991, 4, wire.message("connection.v1.DisconnectNotification", error_code=0))
                return 0, b""
            if method == 3:
                request = wire.message("connection.v1.EchoRequest", body)
                return 0, wire.message("connection.v1.EchoResponse", time=request.time, payload=request.payload)
        if service == "auth":
            if method == 1:
                request = wire.message("authentication.v1.LogonRequest", body)
                self.build = request.application_version
                if request.program != "WoW":
                    return 0x4D, None
                if request.platform not in {"Win", "Wn64", "Mc64", "Mac"}:
                    return 0x4F, None
                if self.build != 60895:
                    return 0x1C, None
                if request.HasField("cached_web_credentials"):
                    return self.logon(request.cached_web_credentials), b""
                challenge = wire.message("challenge.v1.ChallengeExternalRequest", payload_type="web_auth_url",
                                         payload=b"http://127.0.0.1:18081/bnetserver/login/")
                self.send_request(0xBBDA171F, 3, challenge)
                return 0, b""
            if method == 7:
                request = wire.message("authentication.v1.VerifyWebCredentialsRequest", body)
                return self.logon(request.web_credentials), b""
            if method == 8 and self.account:
                self.account = accounts.refresh(self.ticket)
                if not self.account:
                    self.ticket = ''
                    return 3, None
                return 0, wire.message("authentication.v1.GenerateWebCredentialsResponse", web_credentials=self.ticket.encode())
        if not self.account or self.account["expires"] <= time.time():
            return 3, None
        if service == "account":
            if method == 30:
                request = wire.message("account.v1.GetAccountStateRequest", body)
                result = wire.message("account.v1.GetAccountStateResponse")
                if request.options.field_privacy_info:
                    result.state.privacy_info.is_using_rid = False
                    result.state.privacy_info.is_visible_for_view_friends = False
                    result.state.privacy_info.is_hidden_from_friend_finder = True
                    result.tags.privacy_info_tag = 0xD7CA834D
                return 0, result
            if method == 31:
                request = wire.message("account.v1.GetGameAccountStateRequest", body)
                if request.game_account_id.low != self.account["id"]:
                    return 3, None
                result = wire.message("account.v1.GetGameAccountStateResponse")
                if request.options.field_game_level_info:
                    result.state.game_level_info.name = self.account["login"]
                    result.state.game_level_info.program = 5730135
                    result.tags.game_level_info_tag = 0x5C46D483
                if request.options.field_game_status:
                    result.state.game_status.is_suspended = False
                    result.state.game_status.is_banned = False
                    result.state.game_status.suspension_expires = 0
                    result.state.game_status.program = 5730135
                    result.tags.game_status_tag = 0x98B75F99
                return 0, result
        if service == "utilities":
            if method == 10:
                request = wire.message("game_utilities.v1.GetAllValuesForAttributeRequest", body)
                if realms.command_name(request.attribute_key) != "Command_RealmListRequest_v1":
                    return 0xBC7, None
                result = wire.message("game_utilities.v1.GetAllValuesForAttributeResponse")
                result.attribute_value.add(string_value=realms.SUBREGION)
                return 0, result
            if method == 1:
                request = wire.message("game_utilities.v1.ClientRequest", body)
                command = next((realms.command_name(a.name) for a in request.attribute if a.name.startswith("Command_")), "missing")
                # Only command names from the fixed protocol are emitted.
                safe_command = command if command in {"Command_RealmListTicketRequest_v1", "Command_LastCharPlayedRequest_v1",
                    "Command_RealmListRequest_v1", "Command_RealmJoinRequest_v1"} else "unsupported"
                event("realm_request", session=self.id, command=safe_command)
                return realms.process(self, request)
        return 0xBC7, None

    async def run(self):
        event("tls_connected", session=self.id)
        try:
            while True:
                header, body = await asyncio.wait_for(wire.read(self.reader), timeout=120)
                if header.service_id == 0xFE:
                    continue
                service = HASHES.get(header.service_hash, "unsupported")
                method = header.method_id & 0x3FFFFFFF
                event("rpc_request", session=self.id, service=service, method=method, bytes=len(body))
                try:
                    status, payload = self.dispatch(service, method, body)
                except (ValueError, KeyError, TypeError, OverflowError):
                    status, payload = 0xBC5, None
                self.writer.write(wire.response(header.token, payload or b"", status))
                await self.writer.drain()
                event("rpc_response", session=self.id, service=service, method=method, status=status)
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.TimeoutError, ValueError) as error:
            event("tls_closed", session=self.id, error=type(error).__name__)
        finally:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (ConnectionError, OSError):
                pass
