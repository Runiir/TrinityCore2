"""Hunter authority metadata uses supplied ordered bytes, not nearby guesses."""
from copy import deepcopy
import subprocess
import sys

import pytest

from tools.client_compatibility import hunter_learn_metadata as metadata


def busy_fixture():
    # Actual retained UI170 receive order. Two earlier 53-byte movement events
    # fall inside the old candidate window for the trainer's middle packet.
    rows = [
        ('SMSG_ON_MONSTER_MOVE', 'f32221fe0730f1003de013c635deb14204276a42e15b000004e2e91740000010004e000000010000003de013c635deb142f85f6942',
            1791406262.7290087, 1791406262.7289896),
        ('SMSG_ON_MONSTER_MOVE', 'd320213630f1009ae113c6e908bc42362b6a42e25b000004e02d4a400000100050000000010000009ae113c6e908bc429e5e6942',
            1791406262.7290702, 1791406262.7290506),
        ('SMSG_ON_MONSTER_MOVE', 'f31d211d0330f100524c13c65ebaf942b6736d42e35b000000000010000100000001000000524c13c65ebaf942aa7a6d42',
            1791406262.7291257, 1791406262.7291043),
        ('SMSG_UPDATE_OBJECT', '00000100000000f31a2187b730f1030000300000008020002200001821000089b730f100004000298a00000000000031000000',
            1791406262.7292182, 1791406262.7291694),
        ('SMSG_ON_MONSTER_MOVE', 'f31a2187b730f100c3e313c62fddea421b2f6842e45b0000046fb8a33f000010000100000001000000c3e313c62fddea421b2f6842',
            1791406262.7296638, 1791406262.729643),
        ('SMSG_ON_MONSTER_MOVE', 'f316216c0230f100665213c6aaf10243071f6d42e55b00000000001000130a0000020000003f4813c616d90843180a6b42fff73f00',
            1791406262.7298033, 1791406262.729775),
    ]
    wire = [{'session': '341976ca', 'direction': 'from_native', 'name': name, 'body': body, 'time': stamp}
        for name, body, stamp, _ in rows]
    events = [{'session': '341976ca', 'direction': 'from_native', 'name': name, 'bytes': len(bytes.fromhex(body)),
        'time': stamp, 'event': 'native_packet'} for name, body, _, stamp in rows]
    return wire, events, [deepcopy(wire[4])]


def test_actual_busy_equal_size_events_pair_by_complete_logger_order():
    wire, events, required = busy_fixture()
    target = required[0]
    assert len([e for e in events if e['bytes'] == 53 and 0 <= target['time'] - e['time'] < .1]) == 2
    assert metadata.native_authority_metadata(wire, events, required, session='341976ca') == [
        {'ordinal': 4, 'packet': target, 'metadata': events[4]}]


def test_complete_receive_order_keeps_interleaved_unrelated_protocol_outside_scope():
    wire, events, required = busy_fixture()
    for destination in (wire, events):
        destination.insert(2, {'name': 'CMSG_TRAINER_BUY_SPELL', 'session': '341976ca', 'direction': 'to_native'})
        destination.insert(4, {'name': 'SMSG_ON_MONSTER_MOVE', 'session': 'foreign', 'direction': 'from_native'})
        destination.append({'name': 'SMSG_UPDATE_OBJECT', 'session': '341976ca', 'direction': 'to_client'})
    assert metadata.native_authority_metadata(wire, events, required, session='341976ca')[0]['ordinal'] == 4


@pytest.mark.parametrize('fault', ['missing_body', 'extra_body', 'missing_event', 'extra_event', 'reordered_bodies',
    'reordered_events', 'wrong_size', 'wrong_opcode', 'event_after_body', 'next_event_before_body', 'late_body',
    'duplicate_pair', 'duplicate_required', 'missing_required', 'foreign_required', 'foreign_event', 'wrong_direction',
    'wrong_event', 'invalid_time', 'invalid_body', 'noncanonical_body', 'bool_bytes', 'empty_required', 'wrong_session'])
def test_complete_stream_or_required_authority_cannot_be_substituted(fault):
    wire, events, required = busy_fixture()
    session = '341976ca'
    if fault == 'missing_body': wire.pop(0)
    elif fault == 'extra_body': wire.insert(0, {**wire[0], 'time': wire[0]['time'] - .0001})
    elif fault == 'missing_event': events.pop(0)
    elif fault == 'extra_event': events.insert(0, {**events[0], 'time': events[0]['time'] - .0001})
    elif fault == 'reordered_bodies': wire[0], wire[4] = wire[4], wire[0]
    elif fault == 'reordered_events': events[0], events[4] = events[4], events[0]
    elif fault == 'wrong_size': events[4]['bytes'] += 1
    elif fault == 'wrong_opcode': events[4]['name'] = 'SMSG_DESTROY_OBJECT'
    elif fault == 'event_after_body': events[4]['time'] = wire[4]['time'] + .00001
    elif fault == 'next_event_before_body': events[5]['time'] = wire[4]['time'] - .00001
    elif fault == 'late_body': wire[5]['time'] += .1
    elif fault == 'duplicate_pair': wire.append(deepcopy(wire[-1])); events.append(deepcopy(events[-1]))
    elif fault == 'duplicate_required': required.append(deepcopy(required[0]))
    elif fault == 'missing_required': required[0]['body'] = '00'
    elif fault == 'foreign_required': required[0]['session'] = 'foreign'
    elif fault == 'foreign_event': events[4]['session'] = 'foreign'
    elif fault == 'wrong_direction': events[4]['direction'] = 'to_client'
    elif fault == 'wrong_event': events[4]['event'] = 'modern_packet'
    elif fault == 'invalid_time': events[4]['time'] = float('nan')
    elif fault == 'invalid_body': wire[0]['body'] = 'zz'
    elif fault == 'noncanonical_body': wire[0]['body'] = wire[0]['body'].upper()
    elif fault == 'bool_bytes': events[4]['bytes'] = True
    elif fault == 'empty_required': required = []
    else: session = 'foreign'
    with pytest.raises(RuntimeError):
        metadata.native_authority_metadata(wire, events, required, session=session)


def test_pairing_does_not_sort_or_modify_either_retained_stream():
    wire, events, required = busy_fixture()
    original = deepcopy((wire, events, required))
    result = metadata.native_authority_metadata(wire, events, required, session='341976ca')
    result[0]['packet']['body'] = '00'
    result[0]['metadata']['bytes'] = 0
    assert (wire, events, required) == original


def test_metadata_pairing_import_has_no_ui_protocol_or_image_dependencies():
    program = """
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('google.protobuf', 'PIL')) or 'interaction_' in fullname:
            raise RuntimeError('forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from tools.client_compatibility.hunter_learn_metadata import native_authority_metadata
"""
    run = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
