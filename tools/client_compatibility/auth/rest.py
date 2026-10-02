"""Loopback Classic login REST endpoints and the lab launcher's local API."""
import base64
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
import uuid

from . import accounts, srp
from .events import event

ORIGIN = "http://127.0.0.1:18081"
CSRF = secrets.token_urlsafe(32)
STATES = {}
LOCK = threading.Lock()


def input_values(data):
    return {entry["input_id"]: entry["value"] for entry in data.get("inputs", [])}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.session_id = str(uuid.uuid4())

    def log_message(self, *args):
        pass

    def reply(self, data, status=200, content_type="application/json;charset=utf-8", cookie=None):
        payload = json.dumps(data).encode() if content_type.startswith("application/json") else data.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.path.startswith("/bnetserver/"):
            cookie = cookie or self.session_id
        if cookie:
            self.send_header("Set-Cookie", f"JSESSIONID={cookie}; Path=/bnetserver; Domain=127.0.0.1; Secure; HttpOnly; SameSite=None")
        self.end_headers()
        self.wfile.write(payload)

    def ticket(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return ""
        try:
            return base64.b64decode(header[6:], validate=True).decode().split(":", 1)[0]
        except (ValueError, UnicodeError):
            return ""

    def do_GET(self):
        self.restore_session()
        if self.path in {"/", "/launcher"}:
            html = Path(__file__).with_name("launcher.html").read_text().replace("__CSRF__", CSRF)
            return self.reply(html, content_type="text/html;charset=utf-8")
        if self.path == "/lab/status":
            from .control import LAUNCH_STATE
            return self.reply({"client_build": 60895, "login_modes": ["launcher", "direct"],
                "world_build": 15595, "world_entry_ready": False, "launch": LAUNCH_STATE.copy()})
        if self.path == "/lab/session":
            return self.reply({"csrf": CSRF})
        if self.path == "/bnetserver/portal/":
            return self.reply("127.0.0.1:1119", content_type="text/plain")
        if self.path == "/bnetserver/login/":
            event("rest_form")
            return self.reply({"type": "LOGIN_FORM", "inputs": [
                {"input_id": "account_name", "type": "text", "label": "Username", "max_length": 128},
                {"input_id": "password", "type": "password", "label": "Password", "max_length": 128},
                {"input_id": "log_in_submit", "type": "submit", "label": "Log In"}],
                "srp_url": ORIGIN + "/bnetserver/login/srp/"})
        if self.path == "/bnetserver/gameAccounts/":
            account = accounts.from_ticket(self.ticket())
            if not account:
                return self.reply({}, 401)
            return self.reply({"game_accounts": [{"display_name": account["login"], "expansion": 3,
                "is_suspended": False, "is_banned": False}]})
        self.reply({}, 404)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 65536 or "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("invalid request body")
        raw = self.rfile.read(length)
        self.body_consumed = True
        if self.headers.get("Origin") not in {None, ORIGIN}:
            raise ValueError("foreign origin")
        return json.loads(raw)

    def do_POST(self):
        self.body_consumed = False
        try:
            self.restore_session()
            data = self.body()
            if not isinstance(data, dict):
                raise ValueError("invalid JSON object")
            return self.post(data)
        except (ValueError, KeyError, TypeError, OverflowError):
            self.close_connection = not self.body_consumed
            self.reply({"authentication_state": "LOGIN", "error_code": "UNABLE_TO_DECODE"}, 400)

    def restore_session(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies.get("JSESSIONID")
        if cookie:
            self.session_id = str(uuid.UUID(cookie.value))

    def post(self, data):
        if self.path.startswith("/lab/"):
            if not secrets.compare_digest(self.headers.get("X-Lab-CSRF", ""), CSRF):
                return self.reply({"error": "Invalid launcher request."}, 403)
            from .control import launch
            if self.path == "/lab/launch-direct":
                threading.Thread(target=launch, args=("direct",), daemon=True).start()
                return self.reply({"message": "Starting the game with username/password login on the second monitor."})
            if self.path == "/lab/login-launch":
                account = accounts.check_password(data.get("username"), data.get("password"))
                if not account:
                    event("launcher_rejected", status=3)
                    return self.reply({"error": "Username or password is incorrect."}, 401)
                token = accounts.issue(account, "launcher")
                threading.Thread(target=launch, args=("launcher", token, account["login"]), daemon=True).start()
                event("launcher_ticket_issued", mode="launcher", account_id=account["id"])
                return self.reply({"message": "Signed in. Starting the game on the second monitor."})
            return self.reply({}, 404)
        if self.path == "/bnetserver/login/srp/":
            inputs = input_values(data)
            account = accounts.get(inputs.get("account_name"))
            if not account:
                return self.reply({"authentication_state": "DONE"})
            challenge = srp.Challenge(account["login"], account["salt"], account["verifier"])
            # Native clients can retain their SRP session on the same HTTP
            # connection without echoing cookies, as TrinityCore does.
            cookie = self.session_id
            with LOCK:
                for key in list(STATES):
                    if STATES[key][0] <= time.time():
                        del STATES[key]
                if len(STATES) >= 256:
                    return self.reply({}, 503)
                STATES[cookie] = (time.time()+60, account, challenge)
            event("srp_challenge", mode="direct", account_id=account["id"])
            return self.reply(challenge.json(), cookie=cookie)
        if self.path == "/bnetserver/login/":
            inputs = input_values(data)
            m2 = None
            if "public_A" in inputs or "client_evidence_M1" in inputs:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
                cookie = cookies.get("JSESSIONID")
                with LOCK:
                    state = STATES.pop(cookie.value if cookie else self.session_id, None)
                account = None
                failure = ("unknown_session_cookie" if cookie else "missing_connection_state") if not state else "srp_identity_mismatch"
                if state and state[0] > time.time() and state[1]["login"] == inputs.get("account_name", "").upper():
                    failure = "srp_proof_mismatch"
                    if len(inputs.get("public_A", "")) <= 512:
                        m2 = state[2].verify(int(inputs["public_A"], 16), inputs["client_evidence_M1"])
                        account = accounts.get(state[1]["login"]) if m2 else None
            else:
                account = accounts.check_password(inputs.get("account_name"), inputs.get("password"))
            if not account:
                event("rest_login_rejected", mode="direct", status=3,
                      error=failure if "public_A" in inputs else "password_mismatch")
                return self.reply({"authentication_state": "DONE"})
            result = {"authentication_state": "DONE", "login_ticket": accounts.issue(account, "direct")}
            if m2:
                result["server_evidence_M2"] = m2
            event("rest_ticket_issued", mode="direct", account_id=account["id"])
            return self.reply(result)
        if self.path == "/bnetserver/refreshLoginTicket/":
            account = accounts.refresh(self.ticket())
            if not account:
                return self.reply({"login_ticket_expiry": 0, "is_expired": True})
            event("login_ticket_refreshed", mode=account['mode'], account_id=account['id'])
            return self.reply({"login_ticket_expiry": account["expires"], "is_expired": False})
        self.reply({}, 404)


def server():
    result = ThreadingHTTPServer(("127.0.0.1", 18081), Handler)
    result.daemon_threads = True
    return result
