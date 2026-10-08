"""Run client-harness work in a memory-limited user scope.

Example: pixi run python -m tools.client_compatibility.bounded_run --
    pixi run python -m tools.client_compatibility.bag_swap_evidence ...
Use --memory-mib 4096 for the single owned scout launcher and its game child.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import uuid


def available_mib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) // 1024
    raise RuntimeError('available memory cannot be verified')


def command_line(command, memory_mib, unit):
    if type(memory_mib) is not int or not 256 <= memory_mib <= 4096:
        raise ValueError('task memory must be between 256 and 4096 MiB')
    if type(command) not in (list, tuple) or not command or not all(
            type(arg) is str and arg and '\0' not in arg for arg in command):
        raise ValueError('an ordinary executable argument vector is required')
    if not Path('/sys/fs/cgroup/cgroup.controllers').is_file():
        raise RuntimeError('cgroup v2 memory containment is required')
    launcher = shutil.which('systemd-run')
    if launcher is None:
        raise RuntimeError('systemd-run is required; unbounded execution is refused')
    return [launcher, '--user', '--scope', '--quiet', '--collect', '--unit=' + unit,
        '--description=Client442 bounded task', '--property=MemoryMax=' + str(memory_mib) + 'M',
        '--property=MemorySwapMax=0', '--property=OOMPolicy=kill', '--', *command]


def run(command, memory_mib=2048):
    unit = 'client442-task-' + uuid.uuid4().hex
    args = command_line(command, memory_mib, unit)
    available = available_mib()
    if available < memory_mib + 4096:
        raise RuntimeError('task requires its memory budget plus a 4 GiB available reserve')
    print(json.dumps({'scope': unit, 'memory_mib': memory_mib, 'swap_mib': 0,
        'available_mib_before': available}), flush=True)
    result = subprocess.run(args, check=False)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory-mib', type=int, default=2048)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    raise SystemExit(run(command, args.memory_mib))


if __name__ == '__main__':
    main()
