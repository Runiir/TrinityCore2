"""Run the installed Whitemane launcher in an owned HDMI-1 Gamescope window.

Uses the launcher's existing login and installation without reading account files.
No local auth/worldserver, protocol bridge, or lab account participates.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from tools.second_client.place_window import place, second_monitor
from tools.client_compatibility.owned_input import descendant

ROOT = Path.home() / '.local/share/trinity-whitemane-live'
REPO = Path(__file__).resolve().parents[2]
LAUNCHER = Path.home() / '.local/share/whitemane-launcher/Whitemane.AppImage'
WIDTH, HEIGHT = 1280, 900


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.'+path.name,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(data, handle, indent=2)
            handle.write('\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def proc_start(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def owned_process(kind='client'):
    if kind != 'client':
        raise ValueError('live profile owns only its Gamescope client')
    path = ROOT / 'run/client.json'
    if not path.exists():
        return None
    row = json.loads(path.read_text())
    try:
        if proc_start(row['pid']) != row['start_ticks']:
            return None
        if Path(f"/proc/{row['pid']}/comm").read_text().strip() not in ('gamescope', 'gamescope-wl'):
            return None
    except (OSError, ValueError, IndexError):
        return None
    return row


def client_environment():
    owner = owned_process()
    if not owner:
        raise RuntimeError('owned live Gamescope is absent')
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if directory.joinpath('comm').read_text().strip() != 'whitemane':
                continue
            if not descendant(int(directory.name), owner['pid']):
                continue
            env = dict(item.decode().split('=', 1) for item in
                       directory.joinpath('environ').read_bytes().split(b'\0') if b'=' in item)
            if env.get('DISPLAY') == os.environ.get('DISPLAY', ':0') or not env.get('LIBEI_SOCKET'):
                raise RuntimeError('live launcher lacks a private input display')
            return env
        except (OSError, UnicodeError):
            continue
    raise RuntimeError('owned nested Whitemane launcher is absent')


def monitor():
    owner = owned_process()
    if not owner:
        raise RuntimeError('owned live Gamescope is absent')
    row = place(owner['pid'], timeout=1, reposition=False)
    if row['monitor']['name'] != 'HDMI-1':
        raise RuntimeError('live client is not on HDMI-1')
    return row


def start():
    if owned_process():
        raise RuntimeError('live launcher is already running')
    target = second_monitor()
    if target['name'] != 'HDMI-1':
        raise RuntimeError('required HDMI-1 is not the second monitor')
    if not LAUNCHER.is_file():
        raise RuntimeError('installed Whitemane launcher is missing')
    for name in ('run', 'logs', 'evidence'):
        (ROOT / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    env = os.environ.copy()
    for name in ('LD_LIBRARY_PATH', 'LD_PRELOAD'):
        env.pop(name, None)
    env.update(GDK_BACKEND='x11', SDL_VIDEODRIVER='x11',
               SDL_VIDEO_WINDOW_POS=f"{target['x'] + 320},{target['y'] + 80}",
               VK_DRIVER_FILES='/usr/share/vulkan/icd.d/nvidia_icd.json')
    command = ['gamescope', '-w', str(WIDTH), '-h', str(HEIGHT), '-W', str(WIDTH),
               '-H', str(HEIGHT), '-r', '30', '-o', '15', '--backend', 'sdl',
               '--force-windows-fullscreen',
               '--', str(LAUNCHER)]
    with (ROOT / 'logs/launcher.console.log').open('ab') as log:
        os.chmod(log.name, 0o600)
        process = subprocess.Popen(command, env=env, cwd=LAUNCHER.parent,
                                   stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    row = {'pid': process.pid, 'start_ticks': proc_start(process.pid),
           'launcher': str(LAUNCHER), 'started_at': time.time(),
           'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
           'account_files_read': False, 'protocol_bridge_used': False}
    write(ROOT / 'run/client.json', row)
    try:
        placement = place(process.pid, timeout=30)
        if placement['monitor']['name'] != 'HDMI-1':
            raise RuntimeError('live Gamescope placement failed')
        write(ROOT / 'evidence/client_monitor.json', placement)
    except BaseException:
        if owned_process():
            os.kill(process.pid, signal.SIGTERM)
        raise
    print(json.dumps({'runtime': row, 'placement': placement}))


def stop():
    owner = owned_process()
    if not owner:
        raise RuntimeError('owned live Gamescope is absent')
    os.kill(owner['pid'], signal.SIGTERM)
    for _ in range(40):
        if not owned_process():
            write(ROOT / 'evidence/last_client_closure.json',
                  {'runtime': owner, 'finished_at': time.time(), 'closed': True})
            print('Stopped only the owned live launcher/client supervisor')
            return
        time.sleep(.25)
    raise RuntimeError('owned live Gamescope did not stop')


def windows():
    from Xlib import X, display
    monitor()
    owner = owned_process()
    screen = display.Display(client_environment()['DISPLAY'])
    try:
        rows = []
        for window in screen.screen().root.query_tree().children:
            if window.get_attributes().map_state != X.IsViewable:
                continue
            prop = window.get_full_property(screen.intern_atom('_NET_WM_PID'), X.AnyPropertyType)
            if prop is None or len(prop.value) != 1 or not descendant(int(prop.value[0]), owner['pid']):
                continue
            geometry = window.get_geometry()
            rows.append({'id': window.id, 'pid': int(prop.value[0]), 'title': window.get_wm_name(),
                         'width': geometry.width, 'height': geometry.height})
        return rows
    finally:
        screen.close()


def screenshot(path):
    monitor()
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.unlink(missing_ok=True)
    subprocess.run(['gamescopectl', 'screenshot', str(path)],
                   env=client_environment(), check=True, capture_output=True)
    for _ in range(50):
        if path.exists() and path.stat().st_size:
            os.chmod(path, 0o600)
            return path
        time.sleep(.1)
    raise RuntimeError('owned live screenshot was not written')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status', 'shot'))
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/current.png')
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    elif args.action == 'status':
        print(json.dumps({'runtime': owned_process(), 'monitor': monitor(), 'windows': windows()}))
    else:
        print(screenshot(args.output))


if __name__ == '__main__':
    main()
