"""Provision and supervise the lab login service and its two client modes."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.request

from tools.client_compatibility import lab_runtime as lab
from . import accounts
from .events import event
from .generate_schema import REVISION

MANIFEST = Path(__file__).with_name("pixi.toml")
LAUNCH_LOCK = threading.Lock()
LAUNCH_STATE = {"state": "idle"}


def setup(reference):
    accounts.migrate()
    credentials = json.loads((lab.client_root() / "secrets/game_account.json").read_text())
    account_id = accounts.provision(credentials["username"], credentials["password"])
    sources = {}
    for name, target in [("bnetserver.cert.pem", lab.ROOT / "config/bnetserver.cert.pem"),
                         ("bnetserver.key.pem", lab.ROOT / "secrets/bnetserver.key.pem")]:
        data = subprocess.check_output(["git", "show", REVISION + ":src/server/bnetserver/" + name], cwd=reference)
        lab.private_write(target, data.decode())
        sources[name] = lab.sha256(target)
    lab.private_write(lab.ROOT / "evidence/modern_auth_setup.json", json.dumps({
        "source_revision": REVISION, "certificates": sources, "native_account_id": account_id,
        "database": "client442_auth", "schema_additions": ["lab_login_accounts", "lab_login_tickets"],
        "login_modes": ["launcher", "direct"], "tls_endpoint": "127.0.0.1:1119",
        "rest_endpoint": "127.0.0.1:18081", "certificate_kind": "upstream_local_development"}, indent=2)+"\n")
    print("Provisioned the local modern login account and pinned development certificate.")


def start():
    if lab.owned_process("modern_auth"):
        raise RuntimeError("modern login service already running")
    for port in [1119, 18081]:
        lab.free_port(port)
    lab.connection().close()
    command = ["nice", "-n", "10", "pixi", "run", "--manifest-path", str(MANIFEST),
               "python", "-m", "tools.client_compatibility.auth.service"]
    with (lab.ROOT / "logs/modern_auth.console.log").open("ab") as log:
        os.chmod(log.name, 0o600)
        proc = subprocess.Popen(command, cwd=lab.REPO, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
    lab.private_write(lab.ROOT / "run/modern_auth.json", json.dumps({"pid": proc.pid,
        "start_ticks": lab.proc_start(proc.pid), "command": command}, indent=2)+"\n")
    for _ in range(100):
        if not lab.owned_process("modern_auth"):
            raise RuntimeError("modern login service exited during startup")
        try:
            with urllib.request.urlopen("http://127.0.0.1:18081/lab/status", timeout=0.5) as response:
                if json.load(response)["client_build"] == 60895:
                    print(f"Started ready local modern login supervisor PID {proc.pid}.")
                    return
        except (OSError, ValueError):
            time.sleep(0.1)
    lab.stop("modern_auth")
    raise RuntimeError("modern login service did not become ready")


def clear_sso():
    # Only edit registry files belonging to the stopped, private prefix.
    if lab.owned_process("client"):
        raise RuntimeError("cannot clear SSO while the owned client is running")
    root=lab.client_root()
    for path in [root / "wineprefix/pfx/user.reg", root / "wineprefix/user.reg"]:
        if not path.exists():
            continue
        text = path.read_text()
        sections = re.split(r"(?m)(?=^\[)", text)
        kept = []
        for section in sections:
            heading = section.splitlines()[0] if section else ""
            if ("TrinityCore" in heading or "Trinitycore" in heading) and "Battle.net" in heading:
                continue
            kept.append(section)
        lab.private_write(path, "".join(kept))


def launch(mode, ticket=None, login=None):
    if not LAUNCH_LOCK.acquire(blocking=False):
        raise RuntimeError("a client launch is already in progress")
    try:
        LAUNCH_STATE.update(state="starting", mode=mode)
        if mode not in {"direct", "launcher"}:
            raise ValueError("invalid launch mode")
        if mode == "launcher":
            account = accounts.from_ticket(ticket)
            if not account or account["login"] != login or account["mode"] != "launcher":
                raise ValueError("invalid local launch ticket")
        lab.stop("client")
        clear_sso()
        lab.start_client(launcher=True, sso_ticket=ticket if mode == "launcher" else None, game_account=login)
        LAUNCH_STATE.update(state="running", mode=mode)
        event("client_launched", mode=mode)
    except Exception as error:
        LAUNCH_STATE.update(state="failed", error=type(error).__name__)
        event("client_launch_failed", mode=mode, error=type(error).__name__)
        raise
    finally:
        LAUNCH_LOCK.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "start", "stop", "status", "launch-direct", "launch-sso"])
    parser.add_argument("--reference", type=Path, default=Path("/tmp/trinity-cata-classic-compat-reference"))
    args = parser.parse_args()
    if args.action == "setup":
        setup(args.reference)
    elif args.action == "start":
        start()
    elif args.action == "stop":
        lab.stop("modern_auth")
    elif args.action == "launch-direct":
        launch("direct")
    elif args.action == "launch-sso":
        credentials = json.loads((lab.client_root() / "secrets/game_account.json").read_text())
        account = accounts.check_password(credentials["username"], credentials["password"])
        if not account:
            raise RuntimeError("local saved credentials are invalid")
        launch("launcher", accounts.issue(account, "launcher"), account["login"])
    else:
        print(json.dumps(lab.owned_process("modern_auth"), indent=2))


if __name__ == "__main__":
    main()
