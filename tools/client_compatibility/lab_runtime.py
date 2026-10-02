"""Manage only the isolated client442 lab, using private configs and owned PIDs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import time

ROOT = Path.home() / ".local/share/trinity-client442-lab"
REPO = Path(__file__).resolve().parents[2]
BASE = Path.home() / "Games/trinity-cata"
SOURCE = Path.home() / "Games/_whitemane-60895_"
PROTON = Path.home() / ".local/share/Steam/compatibilitytools.d/GE-Proton10-34"
CLIENT_SHA256 = "9d963af8c7ce67aa9828b834a91f59e41221767801e78a9b91d9ea81971ee796"
HELPER_SHA256 = "b84b94a646210d3494f06f36b62fb5a845a8f3f1e470820304938a1d496d17fb"


def actor_name():
    name=os.environ.get('CLIENT442_ACTOR','primary')
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,23}',name):raise ValueError('invalid client442 actor name')
    return name


def client_root():
    name=actor_name()
    return ROOT if name=='primary' else ROOT/'actors'/name


def private_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("w") as handle:
        os.chmod(path, 0o600)
        handle.write(content)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def connection():
    import pymysql
    creds = json.loads((ROOT / "secrets/runtime.json").read_text())
    if (creds["host"], creds["port"], creds["user"]) != ("127.0.0.1", 13306, "client442_runtime"):
        raise RuntimeError("credentials do not target the lab")
    conn = pymysql.connect(host=creds["host"], port=creds["port"], user=creds["user"],
                           password=creds["password"], autocommit=True)
    with conn.cursor() as cursor:
        cursor.execute("SELECT @@hostname")
        if cursor.fetchone()[0] != "trinity-client442-db":
            raise RuntimeError("wrong database instance")
    return conn


def prepare_servers() -> None:
    connection().close()
    receipt = {"schema": "client442_runtime_setup_v1", "binaries": {}}
    for directory in ["bin", "config", "logs/auth", "logs/world", "run", "evidence"]:
        (ROOT / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    for kind in ["authserver", "worldserver"]:
        target = ROOT / "bin" / kind
        source = BASE / f"build/src/server/{kind}/{kind}"
        if not target.exists():
            shutil.copy2(source, target)
        receipt["binaries"][kind] = {"sha256": sha256(target), "source_path": str(source),
            "version": subprocess.check_output([str(target), "--version"], text=True).strip(),
            "fresh_worktree_build": False}
        template = (REPO / f"src/server/{kind}/{kind}.conf.dist").read_text()
        values = {"BindIP": '"127.0.0.1"', "SourceDirectory": f'"{REPO}"',
                  "Updates.AutoSetup": "0", "Updates.CleanDeadRefMaxCount": "0",
                  "PidFile": f'"{ROOT}/run/{kind}.pid"', "MySQLExecutable": '"/usr/bin/mysql"',
                  "LogsDir": f'"{ROOT}/logs/{"auth" if kind == "authserver" else "world"}"'}
        if kind == "authserver":
            values.update({"RealmServerPort": "13724", "Updates.EnableDatabases": "0"})
        else:
            values.update({"WorldServerPort": "18085", "InstanceServerPort": "18086",
                "DataDir": f'"{ROOT if (ROOT / "data/dbc/enUS/QuestPOIPoint.dbc").exists() else BASE}/data"', "Updates.EnableDatabases": "15", "Console.Enable": "1",
                "Ra.Enable": "0", "SOAP.Enabled": "0", "BotWorld.Enable": "0",
                "InstantFlightPaths": "1",
                "PlayerBot.Enable": "0", "BotWorld.AutoStart": "0", "BotWorld.AutoStartRecording": "0",
                "BotWorld.PlayMode.Enable": "0", "BotWorld.RuntimeProfile": '""',
                "BotWorld.ValidationRoute.Enable": "0", "Appender.Server": "2,3,0,Server.log,a",
                "Appender.GM": "2,3,0,GM.log,a", "Appender.DBErrors": "2,3,0,DBErrors.log,a"})
        values.update(dict(line.split(" = ", 1) for line in
                           (ROOT / "database.connections.conf").read_text().splitlines()
                           if kind == "worldserver" or line.startswith("Login")))
        for key, value in values.items():
            pattern = rf"(?m)^{re.escape(key)}\s*=.*$"
            if re.search(pattern, template):
                template = re.sub(pattern, lambda _: f"{key} = {value}", template)
            else:
                template += f"\n{key} = {value}\n"
        private_write(ROOT / f"config/{kind}.conf", template)
    private_write(ROOT / "evidence/runtime_setup.json", json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


def import_content() -> None:
    conn = connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM client442_world.creature")
        if cursor.fetchone()[0]:
            raise RuntimeError("world already has content; refusing a repeated full import")
    conn.close()
    receipts = []
    for role in ["world", "hotfixes"]:
        source = BASE / f"data/TDB_full_434.22011_2022_01_09/TDB_full_{role}_434.22011_2022_01_09.sql"
        with source.open("rb") as handle:
            for line in handle:
                if re.match(rb"\s*(USE\s|CREATE\s+DATABASE)", line, re.I):
                    raise RuntimeError("dump changes database selection")
        with source.open("rb") as handle:
            result = subprocess.run(["docker", "exec", "--interactive", "trinity-client442-db", "mariadb",
                "--defaults-extra-file=/run/secrets/admin.cnf", f"client442_{role}"], stdin=handle,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError(f"{role} content import failed: {result.stderr.decode()[:2000]}")
        receipts.append({"role": role, "path": str(source), "sha256": sha256(source)})
        print(f"Imported clean TDB {role} content", flush=True)
    private_write(ROOT / "evidence/content_import.json", json.dumps(receipts, indent=2) + "\n")


def proc_start(pid: int) -> str:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    if fields[0] == "Z":
        raise ProcessLookupError("process has exited")
    return fields[19]


def owned_process(kind: str):
    file = (client_root() if kind=='client' else ROOT) / f"run/{kind}.json"
    if not file.exists():
        return None
    info = json.loads(file.read_text())
    try:
        if proc_start(info["pid"]) == info["start_ticks"]:
            return info
    except (FileNotFoundError, ProcessLookupError):
        pass
    return None


def free_port(port: int) -> None:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))


def start_server(kind: str) -> None:
    if owned_process(kind):
        raise RuntimeError(f"{kind} already running")
    ports = [13724] if kind == "authserver" else [18085, 18086]
    for port in ports:
        free_port(port)
    connection().close()
    config = ROOT / f"config/{kind}.conf"
    # Every database key is checked before launch, without printing secrets.
    entries = re.findall(r'(?m)^(\w+DatabaseInfo)\s*=\s*"([^"]+)"', config.read_text())
    expected = {"LoginDatabaseInfo": "auth", "WorldDatabaseInfo": "world",
                "CharacterDatabaseInfo": "characters", "HotfixDatabaseInfo": "hotfixes"}
    if len(entries) != (1 if kind == "authserver" else 4):
        raise RuntimeError("database config keys missing or duplicated")
    for key, entry in entries:
        fields = entry.split(";")
        if fields[:3] != ["127.0.0.1", "13306", "client442_runtime"] or fields[4] != "client442_" + expected[key]:
            raise RuntimeError("config targets a non-lab database")
    fifo = ROOT / "run/worldserver.stdin"
    if kind == "worldserver" and not fifo.exists():
        os.mkfifo(fifo, 0o600)
    stdin = os.open(fifo, os.O_RDWR) if kind == "worldserver" else subprocess.DEVNULL
    cmd = ["nice", "-n", "10", "bwrap", "--bind", "/", "/", "--ro-bind", str(BASE / "data"),
           str(BASE / "data"), "--", str(ROOT / "bin" / kind), "--config", str(config)]
    with (ROOT / f"logs/{kind}.console.log").open("ab") as log:
        os.chmod(log.name, 0o600)
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=stdin, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
    if kind == "worldserver":
        os.close(stdin)
    private_write(ROOT / f"run/{kind}.json", json.dumps({"pid": proc.pid,
                  "start_ticks": proc_start(proc.pid), "command": cmd}, indent=2) + "\n")
    print(f"Started {kind}, supervisor PID {proc.pid}; loopback ports {ports}")


def server_command(text: str) -> None:
    if not owned_process("worldserver"):
        raise RuntimeError("owned worldserver is not running")
    fd = os.open(ROOT / "run/worldserver.stdin", os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, (text + "\n").encode())
    finally:
        os.close(fd)


def stop(kind: str) -> None:
    info = owned_process(kind)
    if info:
        os.killpg(info["pid"], signal.SIGTERM)
        print(f"Sent SIGTERM to owned {kind} process group {info['pid']}")
        for attempt in range(300):
            members=[]
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                except (FileNotFoundError,ProcessLookupError):continue
                if fields[0]!='Z' and int(fields[2])==info['pid']:members.append(proc.name)
            if not members:
                return
            if kind == 'client' and attempt >= 30:
                # Gamescope can exit while its child reaper waits forever.
                # Kill only that leftover helper, after the owned game group
                # has no other live members. Never apply this to a server.
                reapers=[]
                for pid in members:
                    try:
                        proc=Path('/proc')/pid
                        if (proc/'comm').read_text().strip()=='gamescopereaper' and str(ROOT).encode() in (proc/'cmdline').read_bytes():
                            reapers.append(int(pid))
                    except (FileNotFoundError,ProcessLookupError):pass
                if len(reapers)==len(members):
                    for pid in reapers:os.kill(pid,signal.SIGKILL)
            time.sleep(0.1)
        raise RuntimeError(f"owned {kind} process group has not stopped after SIGTERM")


def prepare_client() -> None:
    root=client_root()
    for name in ['logs','evidence','run','bin','secrets']:(root/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    client = root / "client/_whitemane-60895_"
    client.mkdir(parents=True, exist_ok=True, mode=0o700)
    # CASC reads use the original data; its writes go to a private overlay.
    for name in ["WTF", "Cache", "Logs", "Errors", "Interface"]:
        (client / name).mkdir(exist_ok=True)
    for entry in SOURCE.iterdir():
        if entry.name in {"WTF", "Cache", "Logs", "Errors", "2fa", "Interface"} or entry.name.startswith("launcher-"):
            continue
        target = client / entry.name
        if target.exists():
            continue
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
    (client.parent / "Data").mkdir(exist_ok=True)
    if not (client.parent / ".build.info").exists():
        shutil.copy2(Path.home() / "Games/.build.info", client.parent / ".build.info")
    config = '''SET portal "127.0.0.1"
SET realmlist "127.0.0.1:13724"
SET textLocale "enUS"
SET audioLocale "enUS"
SET readTOS "1"
SET readEULA "1"
SET playIntroMovie "4"
SET gxApi "D3D11"
SET gxWindow "1"
SET gxMaximize "0"
SET gxResolution "1280x720"
SET graphicsQuality "1"
SET maxFPS "30"
SET maxFPSBk "15"
SET Sound_EnableAllSound "0"
'''
    if not (client / "WTF/Config.wtf").exists():
        private_write(client / "WTF/Config.wtf", config)
    helper = root / "bin/launcher-game.exe"
    if not helper.exists():
        candidates = [ROOT/'bin/launcher-game.exe',*Path("/tmp").glob(".mount_Whitem*/usr/lib/Whitemane/binaries/launcher-game.exe")]
        matching = [path for path in candidates if path.exists() and sha256(path) == HELPER_SHA256]
        if not matching:
            raise RuntimeError("pinned Whitemane launch helper is unavailable; open the installed launcher to mount its resources")
        helper.parent.mkdir(exist_ok=True, mode=0o700)
        shutil.copy2(matching[0], helper)
    print(f"Prepared private client at {client}; separate prefix at {root / 'wineprefix'}")


def client_environment() -> dict[str, str]:
    owned=owned_process('client')
    if not owned:
        raise RuntimeError("owned client is not running")
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            command = (process / "cmdline").read_bytes()
            group=int((process/'stat').read_text().rsplit(')',1)[1].split()[2])
            if group!=owned['pid'] or str(client_root()).encode() not in command or b"proton\x00run\x00" not in command:
                continue
            env = dict(item.decode().split("=", 1) for item in
                       (process / "environ").read_bytes().split(b"\0") if b"=" in item)
            if "GAMESCOPE_WAYLAND_DISPLAY" in env:
                return env
        except (OSError, UnicodeError):
            continue
    raise RuntimeError("no owned client's Gamescope display found")


def screenshot() -> None:
    env = client_environment()
    path = client_root() / "evidence/client.png"
    path.unlink(missing_ok=True)
    subprocess.run(["gamescopectl", "screenshot", str(path)], env=env, check=True)
    for _ in range(50):
        time.sleep(0.1)
        if path.exists() and path.stat().st_size > 0:
            print(path)
            return
    raise RuntimeError("client screenshot was not written")


def create_account() -> None:
    path = client_root() / "secrets/game_account.json"
    if path.exists():
        raise RuntimeError("lab account already provisioned")
    username, password = ('CLIENTLAB' if actor_name()=='primary' else 'CL442_'+actor_name().upper()), secrets.token_hex(6).upper()
    salt = secrets.token_bytes(32)
    identity = hashlib.sha1(f"{username}:{password}".encode()).digest()
    exponent = int.from_bytes(hashlib.sha1(salt + identity).digest(), "little")
    modulus = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
    verifier = pow(7, exponent, modulus).to_bytes(32, "little")
    conn = connection()
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO client442_auth.account (username,salt,verifier,expansion) VALUES (%s,%s,%s,3)",
                       (username, salt, verifier))
        account_id = cursor.lastrowid
        cursor.execute("INSERT INTO client442_auth.realmcharacters (realmid,acctid,numchars) VALUES (1,%s,0)", (account_id,))
    conn.close()
    private_write(path, json.dumps({"username": username, "password": password,
                  "account_id": account_id, "native_auth_endpoint": "127.0.0.1:13724"}, indent=2) + "\n")
    print(f"Created isolated account {username}; credentials in {path}")


def start_client(launcher: bool = False, sso_ticket: str | None = None, game_account: str | None = None) -> None:
    from tools.second_client.place_window import second_monitor
    root=client_root()
    if owned_process("client"):
        raise RuntimeError("lab client already running")
    folder = root / "client/_whitemane-60895_"
    if sha256(folder / "WowClassic.exe") != CLIENT_SHA256:
        raise RuntimeError("client differs from the audited executable")
    if launcher and sha256(root / "bin/launcher-game.exe") != HELPER_SHA256:
        raise RuntimeError("launcher helper differs from the tested version")
    # The client persists the region default (US) after an SSO session. Restore
    # the private lab endpoints before every launch, including direct login.
    config_path = folder / "WTF/Config.wtf"
    import re
    config = config_path.read_text()
    for name, value in {"portal": "127.0.0.1", "realmlist": "127.0.0.1:13724"}.items():
        line = f'SET {name} "{value}"'
        pattern = rf"(?m)^SET {name} .*$"
        config = re.sub(pattern, line, config) if re.search(pattern, config) else config + "\n" + line + "\n"
    private_write(config_path, config)
    for directory in ["casc-upper", "casc-work"]:
        (root / "client" / directory).mkdir(exist_ok=True, mode=0o700)
    env = os.environ.copy()
    # The desktop application's bundled libraries hide the host NVIDIA driver.
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    env["VK_DRIVER_FILES"] = "/usr/share/vulkan/icd.d/nvidia_icd.json"
    monitor = second_monitor()
    env["SDL_VIDEODRIVER"] = "x11"
    env["SDL_VIDEO_WINDOW_POS"] = f"{monitor['x'] + 320},{monitor['y'] + 180}"
    # Never inherit an SSO ticket or account from the desktop launcher.
    for key in list(env):
        if key.startswith("WM_"):
            del env[key]
    if sso_ticket:
        if not launcher or not game_account or not sso_ticket.startswith("TC-"):
            raise ValueError("SSO requires the local launcher and a lab account")
        env.update(WM_PORTAL="127.0.0.1:1119", WM_WEB_TOKEN=sso_ticket, WM_GAME_ACCOUNT=game_account)
    executable = [str(folder / "WowClassic.exe")]
    if launcher:
        executable = [str(root / "bin/launcher-game.exe"), "--exe",
            "Z:" + str(folder / "WowClassic.exe").replace("/", "\\"), "--working-dir",
            "Z:" + str(folder).replace("/", "\\"), "--scenario", "cata-windows-60895",
            "--version-url", "http://m.gamefreedom.org/w/60895/versions",
            "--cdn-url", "http://m.gamefreedom.org/w/60895/cdn",
            "--realmlist-url", "127.0.0.1", "--locale", "enUS"]
        if sso_ticket:
            executable.extend(["--", "-launcherlogin", "-uid", "WoW"])
    # Gamescope owns host X sockets; put only Wine in the data overlay namespace.
    command = ["gamescope", "-w", "1280", "-h", "720", "-W", "1280",
        "-H", "720", "-r", "30", "-o", "15", "--backend", "sdl", "--",
        "bwrap", "--bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc",
        "--ro-bind", str(SOURCE), str(SOURCE),
        "--ro-bind", str(Path.home() / "Games/Data"), str(Path.home() / "Games/Data"),
        "--overlay-src", str(Path.home() / "Games/Data"), "--overlay",
        str(root / "client/casc-upper"), str(root / "client/casc-work"), str(folder.parent / "Data"),
        "--", "env",
        f"WINEPREFIX={root / 'wineprefix'}", "WINEARCH=win64", "GAMEID=umu-default",
        f"STEAM_COMPAT_DATA_PATH={root / 'wineprefix'}",
        f"STEAM_COMPAT_CLIENT_INSTALL_PATH={Path.home() / '.local/share/Steam'}",
        f"PROTONPATH={PROTON}", "WINEDEBUG=-all", "DXVK_LOG_LEVEL=error", "LC_ALL=",
        "WINEDLLOVERRIDES=winemenubuilder=", str(PROTON / "proton"), "run", *executable]
    with (root / "logs/client.console.log").open("ab") as log:
        os.chmod(log.name, 0o600)
        proc = subprocess.Popen(command, cwd=folder, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True, env=env)
    private_write(root / "run/client.json", json.dumps({"pid": proc.pid,
        "start_ticks": proc_start(proc.pid), "command": command}, indent=2) + "\n")
    with (root / "logs/client-monitor.log").open("ab") as log:
        placement = subprocess.Popen(["pixi", "exec", "--spec", "python-xlib", "python",
            str(REPO / "tools/second_client/place_window.py"), "--pid", str(proc.pid),
            "--receipt", str(root / "evidence/client_monitor.json")], cwd=REPO,
            stdout=log, stderr=subprocess.STDOUT, env=env)
    if placement.wait(timeout=35) != 0:
        stop("client")
        raise RuntimeError("second-monitor placement failed; stopped the owned client")
    print(f"Verified game window on second monitor {monitor['name']}")
    print(f"Started isolated client supervisor PID {proc.pid}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare-servers", "import-content", "start-auth", "start-world",
        "prepare-client", "start-client", "status", "stop-auth", "stop-world", "stop-client", "command",
        "screenshot", "create-account"])
    parser.add_argument("--text")
    parser.add_argument("--launcher", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare-servers":
        prepare_servers()
    elif args.action == "import-content":
        import_content()
    elif args.action.startswith("start-"):
        kind = args.action.removeprefix("start-")
        start_client(args.launcher) if kind == "client" else start_server(kind + "server")
    elif args.action.startswith("stop-"):
        kind = args.action.removeprefix("stop-")
        stop(kind if kind == "client" else kind + "server")
    elif args.action == "prepare-client":
        prepare_client()
    elif args.action == "create-account":
        create_account()
    elif args.action == "screenshot":
        screenshot()
    elif args.action == "command":
        if not args.text:
            parser.error("command requires --text")
        server_command(args.text)
    else:
        print(json.dumps({kind: owned_process(kind) for kind in ["authserver", "worldserver", "modern_auth", "client"]}, indent=2))


if __name__ == "__main__":
    main()
