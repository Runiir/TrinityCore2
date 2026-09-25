"""Drive a second WoW client inside a nested gamescope window on its own X display.

The client gets its own Wine prefix and WTF/Cache/Logs, so it never shares state
with the main client. Executables are hard links: umu resolves symlinks, which
would run the client from the main folder and read its Config.wtf.

Run with: pixi exec --spec python-xlib python -m tools.second_client.ctl <command>
"""
from pathlib import Path
import argparse
import os
import signal
import subprocess
import sys
import time

GAMES = Path.home() / 'Games'
SOURCE = GAMES / 'Cataclysm-4.3.4.15595-enUS-x64'
FOLDER = GAMES / 'wow434-claude'
PREFIX = GAMES / 'wow434-claude-prefix'
PROTON = Path.home() / '.local/share/Steam/compatibilitytools.d/GE-Proton10-34'
RUNTIME = Path('/tmp/wow434-claude')
WIDTH, HEIGHT, FPS = 1280, 720, 30
# gamescope 3.16 on GNOME 50: the nested Wayland backend hides the host cursor for
# Wine games that set their own (WoW), and --force-grab-cursor freezes it instead
# (gamescope issues #2432 and #2435). The SDL backend keeps the mouse usable.
BACKEND = 'sdl'
OWN_DIRS = {'WTF', 'Cache', 'Logs', 'Errors'}
CONFIG = f'''SET locale "enUS"
SET realmlist "localhost"
SET patchlist "localhost"
SET realmName "Trinity"
SET accounttype "CT"
SET hwDetect "0"
SET readTOS "1"
SET readEULA "1"
SET playIntroMovie "4"
SET showToolsUI "1"
SET checkAddonVersion "0"
SET gxWindow "1"
SET gxMaximize "1"
SET gxResolution "{WIDTH}x{HEIGHT}"
SET graphicsQuality "1"
SET farclip "600"
SET shadowMode "0"
SET maxFPS "{FPS}"
SET maxFPSBk "{FPS}"
SET Sound_EnableAllSound "0"
SET showGameTips "0"
'''


def setup():
    for name in OWN_DIRS:
        (FOLDER / name).mkdir(parents=True, exist_ok=True)
    for entry in SOURCE.iterdir():
        if entry.name in OWN_DIRS or entry.suffix == '.lnk':
            continue
        target = FOLDER / entry.name
        if target.is_symlink() or target.exists():
            if entry.is_dir() or target.samefile(entry) and not target.is_symlink():
                continue
            target.unlink()
        if entry.is_dir():
            target.symlink_to(entry)
        else:
            os.link(entry, target)
    config = FOLDER / 'WTF' / 'Config.wtf'
    if not config.exists():
        config.write_text(CONFIG)
    print(f'ready: {FOLDER}')


def _pids(match):
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if match(args):
            found.append(int(proc.name))
    return found


def _gamescope_pids():
    return _pids(lambda args: args.startswith('gamescope ') and str(PREFIX) in args)


def _launcher_env():
    """Display names come from the launcher's environment, which gamescope sets."""
    for pid in _pids(lambda args: 'umu-run' in args and str(FOLDER / 'Wow-64.exe') in args):
        try:
            raw = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
        except OSError:
            continue
        env = dict(item.decode().split('=', 1) for item in raw if b'=' in item)
        if 'DISPLAY' in env and 'GAMESCOPE_WAYLAND_DISPLAY' in env:
            return env
    sys.exit('second client is not running (use: start)')


def start(backend=BACKEND):
    if _gamescope_pids():
        sys.exit('second client already running')
    setup()
    RUNTIME.mkdir(exist_ok=True)
    command = [
        'gamescope', '-w', str(WIDTH), '-h', str(HEIGHT), '-W', str(WIDTH), '-H', str(HEIGHT),
        '-r', str(FPS), '-o', str(FPS), '--backend', backend, '--',
        'env', f'WINEPREFIX={PREFIX}', 'WINEARCH=win64', 'GAMEID=umu-default',
        f'PROTONPATH={PROTON}', 'WINEDEBUG=-all', 'DXVK_LOG_LEVEL=error', 'WINEESYNC=1',
        'WINEFSYNC=1', 'WINE_LARGE_ADDRESS_AWARE=1', 'LC_ALL=', 'WINEDLLOVERRIDES=winemenubuilder=',
        'umu-run', str(FOLDER / 'Wow-64.exe'),
    ]
    with open(RUNTIME / 'gamescope.log', 'wb') as log:
        subprocess.Popen(command, cwd=FOLDER, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        time.sleep(1)
        if _pids(lambda args: args.startswith(('X:', 'Z:')) and 'wow434-claude' in args):
            print(f'started; log: {RUNTIME / "gamescope.log"}')
            return
    sys.exit('client did not start within 60s; see the log')


def stop():
    """gamescopereaper kills the client tree when gamescope exits."""
    for pid in _gamescope_pids():
        os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not _gamescope_pids():
            print('stopped')
            return
        time.sleep(0.5)
    sys.exit('gamescope did not exit after SIGTERM')


def status():
    gamescope = _gamescope_pids()
    if not gamescope:
        print('stopped')
        return
    env = _launcher_env()
    print(f'running: gamescope pid {gamescope[0]}, DISPLAY={env["DISPLAY"]}, '
          f'GAMESCOPE_WAYLAND_DISPLAY={env["GAMESCOPE_WAYLAND_DISPLAY"]}')


def shot(path):
    env = _launcher_env()
    path = Path(path or RUNTIME / 'shot.png').resolve()
    path.unlink(missing_ok=True)
    subprocess.run(['gamescopectl', 'screenshot', str(path)], capture_output=True,
                   env={**os.environ, 'GAMESCOPE_WAYLAND_DISPLAY': env['GAMESCOPE_WAYLAND_DISPLAY']})
    size = -1
    for _ in range(50):
        time.sleep(0.1)
        if path.exists() and path.stat().st_size == size > 0:
            print(path)
            return
        size = path.stat().st_size if path.exists() else -1
    sys.exit('screenshot was not written')


# US-layout keys for shifted symbols. Their own keysyms can resolve to keypad-only
# keycodes (parenleft and parenright are 187 and 188 at index 0), so no Shift is
# sent and Wine drops the key.
SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8',
           '(': '9', ')': '0', '_': 'minus', '+': 'equal', '{': 'bracketleft',
           '}': 'bracketright', '|': 'backslash', ':': 'semicolon', '"': 'apostrophe',
           '<': 'comma', '>': 'period', '?': 'slash', '~': 'grave'}


def key_for_char(char):
    """(keysym name, needs Shift) for typing char, or None to look up its own keysym."""
    if char == '\n':
        return 'Return', False
    if char in SHIFTED:
        return SHIFTED[char], True
    if char.isascii() and char.isalpha() and char.isupper():
        return char.lower(), True
    return None


class Input:
    MODIFIERS = {'ctrl': 'Control_L', 'shift': 'Shift_L', 'alt': 'Alt_L'}

    def __init__(self):
        from Xlib import X, XK, display
        from Xlib.ext import xtest
        self.X, self.XK, self.xtest = X, XK, xtest
        self.display = display.Display(_launcher_env()['DISPLAY'])

    def _send(self, kind, detail=0, **position):
        self.xtest.fake_input(self.display, kind, detail, **position)
        self.display.sync()

    def move(self, x, y):
        self._send(self.X.MotionNotify, x=x, y=y)

    def click(self, x, y, button=1, count=1):
        self.move(x, y)
        time.sleep(0.05)
        for _ in range(count):
            self._send(self.X.ButtonPress, button)
            time.sleep(0.05)
            self._send(self.X.ButtonRelease, button)
            time.sleep(0.05)

    def _keycode(self, keysym):
        keycode = self.display.keysym_to_keycode(keysym)
        if not keycode:
            sys.exit(f'no keycode for keysym {keysym:#x}')
        return keycode, self.display.keycode_to_keysym(keycode, 0) != keysym

    def _tap(self, keycodes, hold):
        for keycode in keycodes:
            self._send(self.X.KeyPress, keycode)
        time.sleep(hold)
        for keycode in reversed(keycodes):
            self._send(self.X.KeyRelease, keycode)
        time.sleep(0.03)

    def key(self, combo, hold=0.05):
        """combo like 'Return', 'Escape', 'ctrl+a', 'shift+F1', 'w'."""
        *mods, name = combo.split('+')
        keysym = self.XK.string_to_keysym(name)
        if not keysym:
            sys.exit(f'unknown key {name!r}')
        keycode, shifted = self._keycode(keysym)
        names = [self.MODIFIERS[mod.lower()] for mod in mods] + (['Shift_L'] if shifted else [])
        held = [self._keycode(self.XK.string_to_keysym(mod))[0] for mod in names]
        self._tap(held + [keycode], hold)

    def type(self, text):
        for char in text:
            mapped = key_for_char(char)
            if mapped:
                keycode, shifted = self._keycode(self.XK.string_to_keysym(mapped[0]))
                shifted = mapped[1]
            else:
                keycode, shifted = self._keycode(ord(char))
            shift = [self._keycode(self.XK.string_to_keysym('Shift_L'))[0]] if shifted else []
            self._tap(shift + [keycode], 0.02)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('setup', 'stop', 'status'):
        commands.add_parser(name)
    commands.add_parser('start').add_argument('--backend', default=BACKEND,
                                              choices=('sdl', 'wayland'))
    commands.add_parser('shot').add_argument('path', nargs='?')
    click = commands.add_parser('click')
    click.add_argument('x', type=int)
    click.add_argument('y', type=int)
    click.add_argument('--button', type=int, default=1, help='1 left, 2 middle, 3 right')
    click.add_argument('--count', type=int, default=1)
    move = commands.add_parser('move')
    move.add_argument('x', type=int)
    move.add_argument('y', type=int)
    key = commands.add_parser('key')
    key.add_argument('combo', nargs='+')
    key.add_argument('--hold', type=float, default=0.05, help='seconds to hold, e.g. to walk')
    commands.add_parser('type').add_argument('text')
    args = parser.parse_args()

    if args.command == 'start':
        return start(args.backend)
    if args.command in ('setup', 'stop', 'status'):
        return globals()[args.command]()
    if args.command == 'shot':
        return shot(args.path)
    keyboard = Input()
    if args.command == 'click':
        keyboard.click(args.x, args.y, args.button, args.count)
    elif args.command == 'move':
        keyboard.move(args.x, args.y)
    elif args.command == 'key':
        for combo in args.combo:
            keyboard.key(combo, args.hold)
    elif args.command == 'type':
        keyboard.type(args.text)


if __name__ == '__main__':
    main()
