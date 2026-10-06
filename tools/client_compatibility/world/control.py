"""Supervise only the owned modern world endpoint; native gameplay stays separate."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import time

from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility.auth.control import MANIFEST
from . import joins

BUILD = lab.ROOT / 'build/native_bridge'
BINARY = BUILD / 'client442_bridge'
RECEIPT = BUILD / 'build_receipt.json'
SANITIZERS = False


def source_digest():
    """Include the independent target and its pinned wire schemas."""
    digest = hashlib.sha256()
    paths = sorted((lab.REPO / 'tools/client_compatibility/native_bridge').glob('*'))
    paths += sorted((lab.REPO / 'tools/client_compatibility/world').glob('*.json'))
    paths += [lab.REPO / 'tools/client_compatibility/world/upstream-development-connect-to.pem']
    paths += [lab.REPO/'experiments/configs/client_harness'/name for name in
        ['public_portal_hotfix_v1.json','control_skill_metadata_v1.json']]
    for path in paths:
        if path.is_file() and path.suffix in {'.cpp', '.hpp', '.txt', '.json', '.pem'}:
            digest.update(str(path.relative_to(lab.REPO)).encode() + b'\0')
            digest.update(path.read_bytes())
    return digest.hexdigest()


def build(jobs=1):
    """Build only the packet bridge, never Trinity's worldserver."""
    if not 1<=jobs<=4:raise ValueError('bridge build jobs must be between1 and4')
    available=next(int(line.split()[1]) for line in open('/proc/meminfo') if line.startswith('MemAvailable:'))
    if available<6*1024*1024:raise RuntimeError('bridge build requires at least6GiB available memory')
    subprocess.run(['cmake', '-S', str(lab.REPO / 'tools/client_compatibility/native_bridge'),
        '-B', str(BUILD), '-DCMAKE_BUILD_TYPE=' + ('Debug' if SANITIZERS else 'Release'),
        '-DCMAKE_CXX_FLAGS=' + ('-fsanitize=address,undefined -fno-omit-frame-pointer' if SANITIZERS else '')], check=True)
    subprocess.run(['cmake', '--build', str(BUILD), '-j', str(jobs)], check=True)
    receipt = {'schema': 'client442_native_bridge_build_v1', 'engine': 'cpp',
        'source_digest': source_digest(), 'binary_sha256': lab.sha256(BINARY), 'sanitizers': SANITIZERS,
        'build_jobs':jobs,'available_memory_kib_before':available,
        'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()}
    lab.private_write(RECEIPT, json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


def native_command(workers=4, maximum=64):
    if not 1 <= workers <= 32 or not 2 <= maximum <= 1024:
        raise ValueError('invalid bridge worker or connection bound')
    if not BINARY.is_file() or not RECEIPT.is_file():
        raise RuntimeError('run world.control build before starting the C++ bridge')
    receipt = json.loads(RECEIPT.read_text())
    if receipt['source_digest'] != source_digest() or receipt['binary_sha256'] != lab.sha256(BINARY):
        raise RuntimeError('bridge sources/binary changed; rebuild the independent bridge target')
    return [str(BINARY), '--root', str(lab.ROOT), '--repo', str(lab.REPO),
        '--workers', str(workers), '--maximum-connections', str(maximum)], receipt


def start(engine='cpp', workers=4, maximum=64):
    if lab.owned_process("modern_world"):
        raise RuntimeError("owned modern world endpoint already running")
    if not lab.owned_process("worldserver"):
        raise RuntimeError("owned native worldserver is absent")
    lab.free_port(joins.PORT)
    joins.migrate()
    receipt = {}
    if engine == 'cpp':
        executable, receipt = native_command(workers, maximum)
        command = ['nice', '-n', '10', *executable]
    else:
        command = ["nice", "-n", "10", "pixi", "run", "--manifest-path", str(MANIFEST),
                   "python", "-m", "tools.client_compatibility.world.service"]
    with (lab.ROOT / "logs/modern_world.console.log").open("ab") as log:
        os.chmod(log.name, 0o600)
        process = subprocess.Popen(command, cwd=lab.REPO, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    lab.private_write(lab.ROOT / "run/modern_world.json", json.dumps({"pid": process.pid,
        "start_ticks": lab.proc_start(process.pid), "command": command,
        'engine': engine, 'build': receipt}, indent=2) + "\n")
    # ASan instruments the public-table preload; allow its measured startup cost.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not lab.owned_process("modern_world"):
            raise RuntimeError("modern world endpoint exited during startup")
        try:
            with socket.create_connection(("127.0.0.1", joins.PORT), timeout=0.5) as probe:
                if probe.recv(100).startswith(b"WORLD OF WARCRAFT CONNECTION"):
                    print(f"Started {engine} world bridge on 127.0.0.1:{joins.PORT}.")
                    return
        except OSError:
            time.sleep(0.1)
    lab.stop("modern_world")
    raise RuntimeError("modern world endpoint did not become ready")


def main():
    global BUILD, BINARY, RECEIPT, SANITIZERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "start", "stop", "status"])
    parser.add_argument('--engine', choices=['cpp', 'python'], default='cpp')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--build-jobs', type=int, default=1, help='compile jobs; default1 to preserve client memory headroom')
    parser.add_argument('--maximum-connections', type=int, default=64)
    parser.add_argument('--sanitizers', action='store_true', help='use the independent ASan/UBSan debug target')
    args = parser.parse_args()
    if args.sanitizers:
        SANITIZERS = True
        BUILD = lab.ROOT / 'build/native_bridge_asan'
        BINARY = BUILD / 'client442_bridge'
        RECEIPT = BUILD / 'build_receipt.json'
    action = args.action
    if action == "start":
        start(args.engine, args.workers, args.maximum_connections)
    elif action == 'build':
        build(args.build_jobs)
    elif action == "stop":
        lab.stop("modern_world")
    else:
        print(json.dumps(lab.owned_process("modern_world"), indent=2))


if __name__ == "__main__":
    main()
