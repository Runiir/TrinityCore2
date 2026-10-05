"""Passive bearings from one live client; stop on 30 minutes of gameplay inactivity."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import struct
import sys
import time

ROOT = Path.home() / '.local/share/trinity-whitemane-live'


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def start_ticks(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def validate(scope):
    for pid, ticks in [(scope['game_pid'], scope['game_start_ticks']),
                       (scope['runtime']['pid'], scope['runtime']['start_ticks'])]:
        if start_ticks(pid) != ticks:
            raise RuntimeError('owned live process lifetime changed')
    # CWD is mutable during in-process addon loading. Pin the already-owned
    # client lifetime, process name and host executable instead.
    if Path(f"/proc/{scope['game_pid']}/comm").read_text().strip() != 'WowClassic.exe':
        raise RuntimeError('owned game process identity changed')
    expected=scope.get('host_executable_identity')
    if expected:
        executable=Path(f"/proc/{scope['game_pid']}/exe").stat()
        if {'device':executable.st_dev,'inode':executable.st_ino} != expected:
            raise RuntimeError('owned game executable changed')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    os.umask(0o077)
    scope = json.loads((ROOT / 'run/bearing_scope.json').read_text())
    validate(scope)
    here = Path(scope['game_directory']) / 'Interface/AddOns/CanopicHelper/tools'
    reader = load('whitemane_installed_reader', here / 'live-direction.py')
    files = load('whitemane_installed_mailbox', here / 'file-bearing.py')
    runtime = reader.runtime_directory()
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (runtime / 'session.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    mailbox = files.Mailbox()
    if not (mailbox.addon.parent / (files.PREFIX + '001') / 'Data.lua').is_file():
        raise RuntimeError('existing Canopic Helper file-reader slots are absent')
    session = {'pid': os.getpid(), 'start_ticks': start_ticks(os.getpid()), 'scope': scope,
               'started_at': time.time(), 'status': 'starting', 'raw_capture_saved': False,
               'memory_writes': False, 'authenticated_frames': 0, 'bearings': 0,
               'idle_timeout_seconds': 1800, 'fixed_session_limit': None}
    write(ROOT / 'run/bearing_reader.json', session)
    def interrupt(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    buffer, flows, keys, header = bytearray(), {}, set(), None
    mailbox.clear()
    try:
        library = reader.crypto.load_native(runtime)
        keys, scanned, _, limited = reader.crypto.schedules(library, scope['game_pid'], 4096, 45)
        if not keys:
            raise RuntimeError('no live crypto schedules found')
        last_activity, heartbeat = time.monotonic(), 0
        session.update(status='ready', ready_at=time.time(), scan_bytes=scanned, scan_limited=limited)
        write(ROOT / 'run/bearing_reader.json', session)
        print('Session ready. Cast Survey in the digsite. Stops after 30 minutes of gameplay inactivity.', flush=True)
        def clear():
            mailbox.clear()
            (ROOT / 'run/telescope.json').unlink(missing_ok=True)
        def emit(record):
            validate(scope)
            mailbox.write(reader.wire_record(record))
            row = {'source': 'owned_client_authenticated_visible_survey_telescope',
                   'runtime': scope['runtime'], 'reader_pid': os.getpid(),
                   'observed_at': record['at'], 'instance': record['instance'],
                   'north': record['north'], 'west': record['west'],
                   'facing_radians': record['angle'], 'entry': record['entry']}
            write(ROOT / 'run/telescope.json', row)
            session['bearings'] += 1
            print('Fresh telescope bearing delivered to Canopic Helper.', flush=True)
        window = reader.SurveyWindow(emit, clear)
        def packet(direction, opcode, payload, stamp):
            nonlocal last_activity
            window.packet(direction, opcode, payload, stamp)
            session['authenticated_frames'] += 1
            activity = False
            try:
                if direction == 'client_to_server':
                    if opcode in reader.MOVEMENT:
                        mover = reader.Reader(payload).guid()
                        activity = window.player is not None and mover == window.player
                    elif opcode == 0x340155:
                        activity = bool(reader.spell_request(payload))
            except (ValueError, struct.error, IndexError):
                pass
            if activity:
                last_activity = time.monotonic()
                session['last_gameplay_activity_at'] = stamp
        while time.monotonic() - last_activity < 1800:
            validate(scope)
            window.expire(time.time())
            if time.monotonic() - heartbeat >= 2:
                session['idle_seconds'] = round(time.monotonic() - last_activity, 1)
                write(ROOT / 'run/bearing_reader.json', session)
                heartbeat = time.monotonic()
            ready, _, _ = select.select([sys.stdin.buffer], [], [], .5)
            if not ready:
                continue
            block = os.read(sys.stdin.fileno(), 65536)
            if not block:
                session['stop_reason'] = 'capture_pipe_closed'
                break
            buffer.extend(block)
            if header is None and len(buffer) >= 24:
                formats = {b'\xd4\xc3\xb2\xa1': ('<', 1e6), b'\x4d\x3c\xb2\xa1': ('<', 1e9)}
                if bytes(buffer[:4]) not in formats:
                    raise ValueError('unsupported live pcap format')
                endian, scale = formats[bytes(buffer[:4])]
                link = struct.unpack_from(endian+'I', buffer, 20)[0]
                header = endian, scale, link
                del buffer[:24]
            if header is None:
                continue
            while len(buffer) >= 16:
                sec, fraction, size, original = struct.unpack_from(endian+'IIII', buffer)
                if size != original or not 1 <= size <= 262144:
                    raise ValueError('truncated or oversized live packet')
                if len(buffer) < 16+size:
                    break
                segment = reader.tcp_segment(bytes(buffer[16:16+size]), link)
                del buffer[:16+size]
                if segment:
                    key, seq, body = segment
                    if key not in flows:
                        if len(flows) >= 8:
                            raise ValueError('reconnect/flow limit; restart the helper')
                        flows[key] = reader.Flow(library, keys, key[1], packet)
                    flows[key].segment(seq, body, sec+fraction/scale)
                if len(buffer) > 2**20:
                    raise ValueError('live capture buffer limit')
            if any(f.gap_at and time.monotonic()-f.gap_at > 3 for f in flows.values()):
                raise ValueError('TCP gap; stopped without guessing a direction')
        else:
            session['stop_reason'] = '30_minutes_gameplay_inactivity'
    except KeyboardInterrupt:
        session['stop_reason'] = 'supervisor_interruption'
    except Exception as error:
        session['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        mailbox.clear()
        (ROOT / 'run/telescope.json').unlink(missing_ok=True)
        flows.clear(); keys.clear(); buffer.clear()
        session.update(status='stopped', finished_at=time.time())
        write(ROOT / 'run/bearing_reader.json', session)
        print('Stopped. Raw buffers discarded and bearing mailbox cleared.', flush=True)


if __name__ == '__main__':
    main()
