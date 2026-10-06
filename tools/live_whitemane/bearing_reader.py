"""Passive bearings from one live client; stop on 30 minutes of gameplay inactivity."""
import fcntl
import hashlib
import importlib.util
import json
import os
import queue
from pathlib import Path
import signal
import struct
import sys
import time
import threading
from . import own_pose, owned_sockets, addon_relay,survey_find
from tools.client_compatibility.world import movement

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


def segment_flow(flows, key, seq, body, stamp, ignored, session):
    flow=flows[key]
    try:
        flow.segment(seq,body,stamp)
    except ValueError as error:
        diagnostic={'local_port':key[0],'direction':key[1],
            'authenticated':flow.authenticated,'alignment':flow.alignment,
            'buffer_bytes':len(flow.buffer),'initial_attempts':len(flow.checked),
            'reason':str(error)}
        session.setdefault('flow_failures',[]).append(diagnostic)
        if flow.authenticated:raise
        # No plaintext or observations were emitted on this unsuccessful
        # channel. Quarantine it within the existing strict resource bounds.
        ignored.add(key);del flows[key]
        if len(ignored)>=8:raise ValueError('unauthenticated channel limit')


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
    # Drain the capture pipe during initial key discovery/authentication too.
    # Otherwise immediate-mode capture can overflow its small kernel ring
    # while the decoder is busy. This bounded queue stays entirely in RAM.
    captured=queue.Queue(maxsize=128);capture_errors=[]
    def capture_pipe():
        try:
            while True:
                block=os.read(sys.stdin.fileno(),65536)
                captured.put(block,timeout=1)
                if not block:return
        except queue.Full:capture_errors.append('8 MiB capture queue limit')
        except OSError as error:capture_errors.append(str(error))
    threading.Thread(target=capture_pipe,daemon=True).start()
    session['capture_queue_limit_bytes']=128*65536
    ignored=set(); poses=[]; owned_ports=owned_sockets.ports(scope['game_pid'])
    if not owned_ports:raise RuntimeError('owned live world socket is absent')
    opcode_table=json.loads(Path(movement.__file__).with_name('opcodes.json').read_text())['modern']
    movement_opcodes={opcode_table[name] for name in movement.SUPPORTED}
    movement_opcodes.add(opcode_table['CMSG_MOVE_SET_FACING_HEARTBEAT'])
    mailbox.clear();relay=addon_relay.Assembler()
    relay_file=Path(addon_relay.__file__);relay_hash=hashlib.sha256(relay_file.read_bytes()).hexdigest()
    session['addon_decoder_sha256']=relay_hash
    find_file=Path(survey_find.__file__);find_hash=hashlib.sha256(find_file.read_bytes()).hexdigest()
    session['find_decoder_sha256']=find_hash
    pose_file=Path(own_pose.__file__);pose_hash=hashlib.sha256(pose_file.read_bytes()).hexdigest()
    session['height_decoder_sha256']=pose_hash
    try:
        library = reader.crypto.load_native(runtime)
        keys, scanned, _, limited = reader.crypto.schedules(library, scope['game_pid'], 4096, 45)
        if not keys:
            raise RuntimeError('no live crypto schedules found')
        last_activity, heartbeat = time.monotonic(), 0
        session.update(status='waiting_capture', scan_bytes=scanned, scan_limited=limited)
        write(ROOT / 'run/bearing_reader.json', session)
        print('Decoder initialized. Waiting for authenticated capture; complete sudo authentication in this terminal.', flush=True)
        def clear():
            mailbox.clear()
            (ROOT / 'run/telescope.json').unlink(missing_ok=True)
            (ROOT / 'run/visible_find.json').unlink(missing_ok=True)
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
            # Crypto initialization alone does not prove the sudo capture has
            # started. Announce readiness only after authenticating an owned
            # client's frame from the pipe.
            if session['status']=='waiting_capture':
                session.update(status='ready',ready_at=time.time())
                write(ROOT/'run/bearing_reader.json',session)
                print('Session ready. Authenticated owned-client feed active. Stops after 30 minutes of gameplay inactivity.',flush=True)
            window.packet(direction, opcode, payload, stamp)
            find=survey_find.owned(reader,window,direction,opcode,payload,stamp,
                session.setdefault('visible_find_diagnostics',{}))
            if find:
                write(ROOT/'run/visible_find.json',{**find,'runtime':scope['runtime'],
                    'reader_pid':os.getpid(),'reader_start_ticks':session['start_ticks']})
                session['visible_find_samples']=session.get('visible_find_samples',0)+1
            session['authenticated_frames'] += 1
            activity = False
            try:
                if direction == 'client_to_server':
                    counts=session.setdefault('outbound_opcode_counts',{})
                    if str(opcode) in counts or len(counts)<128:counts[str(opcode)]=counts.get(str(opcode),0)+1
                    if opcode==opcode_table['CMSG_CHAT_ADDON_MESSAGE_TARGETED']:
                        session['relay_targeted_frames']=session.get('relay_targeted_frames',0)+1
                        message=addon_relay.targeted(payload,window.player)
                        if message is not None and relay.packet(message,stamp):
                            write(ROOT/'run/addon_state.json',relay.state(scope['runtime'],session))
                            session['addon_updates']=session.get('addon_updates',0)+1
                    elif opcode in movement_opcodes:
                        mover = reader.Reader(payload).guid()
                        if mover[1]>>58==2 and (window.player is None or mover==window.player):
                            window.player=mover
                            activity=True
                            position=own_pose.parse(payload,mover)
                            position.update(observed_at=stamp,runtime=scope['runtime'],
                                            reader_pid=os.getpid(),reader_start_ticks=session['start_ticks'])
                            poses.append(position)
                            del poses[:-16]
                            write(ROOT/'run/movement_pose.json',{**position,'samples':poses})
                            session['height_samples']=session.get('height_samples',0)+1
                    elif opcode == 0x340155:
                        activity = bool(reader.spell_request(payload))
            except (ValueError, struct.error, IndexError) as error:
                if opcode==opcode_table['CMSG_CHAT_ADDON_MESSAGE_TARGETED']:
                    # Layout diagnostics contain no prefix payload or chat.
                    counts=session.setdefault('relay_rejections',{});reason=str(error)[:120]
                    if reason in counts or len(counts)<16:counts[reason]=counts.get(reason,0)+1
                elif direction=='client_to_server' and opcode in movement_opcodes:
                    counts=session.setdefault('height_rejections',{});reason=str(error)[:120]
                    if reason in counts or len(counts)<16:counts[reason]=counts.get(reason,0)+1
            if activity:
                last_activity = time.monotonic()
                session['last_gameplay_activity_at'] = stamp
        while time.monotonic() - last_activity < 1800:
            validate(scope)
            window.expire(time.time())
            if time.monotonic() - heartbeat >= 2:
                candidate_hash=hashlib.sha256(pose_file.read_bytes()).hexdigest()
                if candidate_hash!=pose_hash:
                    importlib.reload(own_pose);pose_hash=candidate_hash;poses.clear()
                    session['height_decoder_sha256']=pose_hash
                candidate_hash=hashlib.sha256(find_file.read_bytes()).hexdigest()
                if candidate_hash!=find_hash:
                    importlib.reload(survey_find);find_hash=candidate_hash
                    session['find_decoder_sha256']=find_hash
                candidate_hash=hashlib.sha256(relay_file.read_bytes()).hexdigest()
                if candidate_hash!=relay_hash:
                    importlib.reload(addon_relay);relay_hash=candidate_hash
                    previous=relay;relay=addon_relay.Assembler();relay.channels=previous.channels
                    session['addon_decoder_sha256']=relay_hash
                owned_ports=owned_sockets.ports(scope['game_pid'])
                if not owned_ports:raise RuntimeError('owned world socket closed')
                session['idle_seconds'] = round(time.monotonic() - last_activity, 1)
                session['flows']=[{'local_port':k[0],'direction':k[1],
                    'authenticated':f.authenticated,'alignment':f.alignment} for k,f in flows.items()]
                write(ROOT / 'run/bearing_reader.json', session)
                heartbeat = time.monotonic()
            if capture_errors:raise ValueError(capture_errors[0])
            try:block=captured.get(timeout=.5)
            except queue.Empty:continue
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
                    if key[0] not in owned_ports or key in ignored:continue
                    if key not in flows:
                        if len(flows) >= 8:
                            raise ValueError('reconnect/flow limit; restart the helper')
                        flows[key] = reader.Flow(library, keys, key[1], packet)
                    segment_flow(flows,key,seq,body,sec+fraction/scale,ignored,session)
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
        (ROOT / 'run/movement_pose.json').unlink(missing_ok=True)
        (ROOT / 'run/visible_find.json').unlink(missing_ok=True)
        flows.clear(); keys.clear(); buffer.clear()
        while not captured.empty():
            try:captured.get_nowait()
            except queue.Empty:break
        session.update(status='stopped', finished_at=time.time())
        write(ROOT / 'run/bearing_reader.json', session)
        print('Stopped. Raw buffers discarded and bearing mailbox cleared.', flush=True)


if __name__ == '__main__':
    main()
