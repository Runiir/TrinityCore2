"""Supervise only the owned modern world endpoint; native gameplay stays separate."""
import argparse
import json
import os
import socket
import subprocess
import time

from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility.auth.control import MANIFEST
from . import joins


def start():
    if lab.owned_process("modern_world"):
        raise RuntimeError("owned modern world endpoint already running")
    if not lab.owned_process("worldserver"):
        raise RuntimeError("owned native worldserver is absent")
    lab.free_port(joins.PORT)
    joins.migrate()
    command = ["nice", "-n", "10", "pixi", "run", "--manifest-path", str(MANIFEST),
               "python", "-m", "tools.client_compatibility.world.service"]
    with (lab.ROOT / "logs/modern_world.console.log").open("ab") as log:
        os.chmod(log.name, 0o600)
        process = subprocess.Popen(command, cwd=lab.REPO, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    lab.private_write(lab.ROOT / "run/modern_world.json", json.dumps({"pid": process.pid,
        "start_ticks": lab.proc_start(process.pid), "command": command}, indent=2) + "\n")
    for _ in range(100):
        if not lab.owned_process("modern_world"):
            raise RuntimeError("modern world endpoint exited during startup")
        try:
            with socket.create_connection(("127.0.0.1", joins.PORT), timeout=0.5) as probe:
                if probe.recv(100).startswith(b"WORLD OF WARCRAFT CONNECTION"):
                    print(f"Started modern world endpoint on 127.0.0.1:{joins.PORT}.")
                    return
        except OSError:
            time.sleep(0.1)
    lab.stop("modern_world")
    raise RuntimeError("modern world endpoint did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    action = parser.parse_args().action
    if action == "start":
        start()
    elif action == "stop":
        lab.stop("modern_world")
    else:
        print(json.dumps(lab.owned_process("modern_world"), indent=2))


if __name__ == "__main__":
    main()
