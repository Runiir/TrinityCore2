"""Cancel normal logout, then complete logout and reenter the owned character."""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import struct
import time

from . import actors, lab_runtime as lab, owned_input
from .interaction_trial import Trial, choose
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_group_state import capture
from .interaction_social import actor
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.objects import INDEX


class Packets:
    def __init__(self, session):
        self.session = session
        self.cursor = Cursor(lab.ROOT / 'evidence/world_packets.jsonl')
        self.rows = []
        list(self.cursor.poll())  # Prime before entering the 20-second cancel window.

    def since(self, started):
        self.rows.extend(row for row in self.cursor.poll() if row.get('session') == self.session)
        return [row for row in self.rows if row.get('time', 0) >= started]

    def has(self, started, name, direction):
        return any(row['name'] == name and row['direction'] == direction for row in self.since(started))

    def response(self, started):
        row = next((row for row in self.since(started) if row['name'] == 'SMSG_LOGOUT_RESPONSE'
                    and row['direction'] == 'from_native'), None)
        return struct.unpack('<IB', bytes.fromhex(row['body'])) if row else None


def request_logout(trial, packets, label, cancel):
    require(trial.step('lifecycle.menu.' + label, 'Open the game menu.', {
        'menu': {'kind': 'key', 'value': 'Escape', 'description': 'Press Escape to open the game menu.'},
        'map': {'kind': 'key', 'value': 'm', 'description': 'Open the world map.'},
        'bags': {'kind': 'key', 'value': 'b', 'description': 'Open the backpack.'}},
        lambda b, a, s: {'status': 'panel_open_pass' if 'GameMenuFrame' in a['panels'] else 'controller_failure'}),
        'panel_open_pass')
    started = time.time()

    def verdict(before, after, selected):
        response = packets.response(started)
        requested = packets.has(started, 'CMSG_LOGOUT_REQUEST', 'from_client')
        visible = any(p.startswith('StaticPopup') for p in after['panels'])
        return {'status': 'logout_countdown_pass' if requested and response == (0, 0) and visible else
                ('controller_failure' if not selected else 'client_or_protocol_failure'),
                'oracle': {'client_request': requested, 'native_response': response, 'popup_visible': visible}}

    require(click_case(trial, 'lifecycle.logout_request.' + label, 'Log out to character selection.',
                       lambda c: c['name'] == 'GameMenuButtonLogout', verdict), 'logout_countdown_pass')
    if not cancel:
        return started

    def cancelled(before, after, selected):
        request = packets.has(started, 'CMSG_LOGOUT_CANCEL', 'from_client')
        ack = packets.has(started, 'SMSG_LOGOUT_CANCEL_ACK', 'from_native')
        done = packets.has(started, 'SMSG_LOGOUT_COMPLETE', 'from_native')
        gone = not any(p.startswith('StaticPopup') for p in after['panels'])
        return {'status': 'logout_cancel_pass' if request and ack and gone and not done else
                ('controller_failure' if selected != 'cancel' else 'client_or_protocol_failure'),
                'oracle': {'client_request': request, 'native_ack': ack, 'logout_completed': done,
                           'popup_closed': gone, 'same_character': after['guid'] == trial.guid}}

    require(trial.step('lifecycle.logout_cancel', 'Cancel the logout countdown and stay on this character.', {
        'cancel': {'kind': 'key', 'value': 'Escape', 'description': 'Press Escape to cancel the logout countdown.'},
        'map': {'kind': 'key', 'value': 'm', 'description': 'Open the world map.'},
        'bags': {'kind': 'key', 'value': 'b', 'description': 'Open the backpack.'}}, cancelled), 'logout_cancel_pass')
    trial.clean_panels()
    return started


def lobby_frame(trial, label):
    from tools.second_client import ctl
    monitor = owned_input.focus()
    path = trial.out / (label + '.png')
    with redirect_stdout(StringIO()):
        ctl.shot(str(path))
    return {'file': path.name, 'sha256': lab.sha256(path), 'monitor': monitor}


def suite(out, actor_name, cancel_only):
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    cohort = {'started_at': time.time(), 'completed': False, 'failure': None}
    trials = {}
    try:
        with actor(actor_name):
            trial = trials[actor_name] = Trial(out / actor_name)
            trial.clean_panels()
            session = actors.session_entry(trial.fixture)['session']
            inventory = Inventory(lab.ROOT, session, trial.fixture['guid']).poll()
            flags = inventory.objects.get(trial.fixture['guid'], {}).get(INDEX['PLAYER_FLAGS'])
            if flags is None or flags & 0x20:
                raise RuntimeError('logout cancellation requires an observed non-resting character')
            trial.receipt['native_logout_fixture'] = {'player_flags': flags, 'session': session}
            trial.persist()
            packets = Packets(session)
            before, _ = trial.observe('lifecycle_baseline')
            request_logout(trial, packets, 'cancel', True)
            if not cancel_only:
                started = request_logout(trial, packets, 'complete', False)
                deadline = time.monotonic() + 32
                while not packets.has(started, 'SMSG_LOGOUT_COMPLETE', 'from_native'):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('native logout completion deadline exceeded')
                    time.sleep(.2)
                # Glue screens have no addon observations. Preserve the frame and native enum.
                deadline = time.monotonic() + 8
                while not packets.has(started, 'SMSG_ENUM_CHARACTERS_RESULT', 'from_native'):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('character selection enumeration deadline exceeded')
                    time.sleep(.2)
                frame = lobby_frame(trial, 'character_selection')
                row = {'id': 'lifecycle.logout_complete', 'status': 'logout_complete_pass',
                       'selection_source': 'read_only_native_oracle', 'time': time.time(), 'frame': frame,
                       'oracle': {'native_completion': True, 'native_character_enumeration': True}}
                trial.receipt['cases'].append(row); trial.persist()
        if not cancel_only:
            peer_name = 'primary' if actor_name == 'scout' else 'scout'
            with actor(peer_name):
                peer = trials[peer_name] = Trial(out / peer_name)
                peer.clean_panels()
                facts = capture(peer, 'member_logged_out')
                unit = next((u for u in facts['group']['units'] if u['name'] == trial.fixture['character_name']), None)
                if not unit or unit['connected']:
                    raise RuntimeError('peer raid roster does not show the logged-out member offline')
                peer.receipt['offline_member'] = facts; peer.persist()
            with actor(actor_name):
                started = time.time()
                actions = {
                    'enter': {'kind': 'key', 'value': 'Return', 'description': 'Press Enter to enter the selected character.'},
                    'back': {'kind': 'key', 'value': 'Escape', 'description': 'Go back from character selection.'}}
                request, response, selected = choose('Enter the selected owned character.',
                    {'panels': ['CharacterSelect'], 'bags': [], 'errors': []}, actions, 44260895)
                row = {'id': 'lifecycle.reenter', 'time': started, 'request': request, 'response': response,
                       'selected': selected, 'input': actions[selected], 'selection_source': 'laya',
                       'before_frame': lobby_frame(trial, 'reenter_before'), 'status': 'started'}
                trial.receipt['cases'].append(row); trial.persist()
                trial.execute(actions[selected]); time.sleep(4)
                after, frame = trial.observe('reentered')
                login = packets.has(started, 'CMSG_PLAYER_LOGIN', 'from_client')
                restored = all(after.get(k) == before.get(k) for k in ['equipment', 'group', 'raid_profile'])
                row.update(status='reenter_pass' if login and restored else 'client_or_protocol_failure',
                           after=after, after_frame=frame, oracle={'client_login': login,
                           'same_character': after['guid'] == trial.guid, 'equipment_group_profile_restored': restored})
                trial.persist(); require(row, 'reenter_pass'); trial.clean_panels()
            with actor(peer_name):
                facts = capture(peer, 'member_reentered')
                unit = next((u for u in facts['group']['units'] if u['name'] == trial.fixture['character_name']), None)
                if not unit or not unit['connected']:
                    raise RuntimeError('peer raid roster does not show the reentered member online')
                peer.receipt['online_member'] = facts; peer.persist()
        cohort['completed'] = True
    except Exception as e:
        cohort['failure'] = f'{type(e).__name__}: {e}'
    finally:
        for name, trial in trials.items():
            with actor(name):
                try:
                    trial.clean_panels()
                except Exception as e:
                    trial.receipt['cleanup_failure'] = f'{type(e).__name__}: {e}'
            trial.receipt.update(completed=cohort['completed'], failure=cohort['failure'], finished_at=time.time())
            trial.persist()
        cohort['finished_at'] = time.time()
        lab.private_write(out / 'cohort.json', json.dumps(cohort, indent=2) + '\n')
        print(json.dumps(cohort), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--actor', choices=['primary', 'scout'], default='scout')
    parser.add_argument('--cancel-only', action='store_true')
    args = parser.parse_args()
    suite(args.output, args.actor, args.cancel_only)


if __name__ == '__main__':
    main()
