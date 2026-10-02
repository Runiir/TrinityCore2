"""Qualify trainer filtering without changing known spells or character resources."""
from collections import Counter
import struct
from . import lab_runtime as lab
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.journal import entries


def spell_baseline(t):
    with lab.connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=%s ORDER BY spell',
                       (t.fixture['guid'],))
        return cursor.fetchall()


def native_catalog(t):
    found = None
    for row in entries(lab.ROOT / 'evidence/world_packets.jsonl'):
        if (row.get('time', 0) < t.receipt['started_at'] or row.get('direction') != 'from_native' or
                row.get('name') != 'SMSG_TRAINER_LIST' or not row.get('body')):
            continue
        data = bytes.fromhex(row['body']); guid, kind, trainer, count = struct.unpack_from('<QIII', data)
        if (guid >> 32) & 0xfffff != 5499:
            continue
        states = Counter(data[20 + index * 34 + 4] for index in range(count))
        found = {'guid': guid, 'type': kind, 'trainer': trainer, 'count': count,
                 'native_states': dict(states), 'body_sha256': __import__('hashlib').sha256(data).hexdigest()}
    if not found or found['native_states'] != {0: found['count']}:
        raise RuntimeError('requires the exact native all-known alchemy trainer fixture')
    return found


def open_filter(t, label):
    require(click_case(t, 'trainer.filter_open.' + label, 'Open the trainer Filter menu.',
        lambda c: c['text'] == 'Filter',
        lambda b,a,s: {'status': 'trainer_filter_open_pass' if s and 'ContextMenu' in a['panels'] else
                      ('controller_failure' if not s else 'client_or_protocol_failure')}), 'trainer_filter_open_pass')


def toggle_known(t, label, expected):
    require(click_case(t, 'trainer.known_filter.' + label,
        ('Show' if expected else 'Hide') + ' already known trainer recipes.',
        lambda c: 'known' in c['text'].lower(),
        lambda b,a,s: {'status': 'trainer_filter_change_pass' if s and
                      a.get('trainer',{}).get('filters',{}).get('used') == expected else
                      ('controller_failure' if not s else 'client_or_protocol_failure'),
                      'oracle': {'trainer': a.get('trainer'), 'errors': a.get('errors')}}), 'trainer_filter_change_pass')
    # The stock menu remains open after checking a filter; dismiss it normally.
    state, _ = t.observe(label + '_filter_result')
    if 'ContextMenu' in state['panels']:
        t.execute({'kind':'key', 'value':'Escape'})


def known_catalog(t):
    state, _ = t.observe('trainer_filter_baseline')
    baseline = state.get('trainer',{}).get('filters'); money = state.get('money'); spells = spell_baseline(t)
    catalog = native_catalog(t)
    if baseline != {'available': True, 'unavailable': True, 'used': False}:
        raise RuntimeError('requires the stock trainer filter baseline')
    t.receipt['trainer_filter_baseline'] = {'filters': baseline, 'money': money, 'native_catalog': catalog}
    t.persist()
    try:
        open_filter(t, 'show'); toggle_known(t, 'show', True)
        state, frame = t.observe('trainer_known_catalog')
        counts = state.get('trainer',{}).get('service_counts',{})
        passed = counts.get('used') == catalog['count'] and not counts.get('available') and not counts.get('unavailable')
        t.receipt['trainer_known_catalog'] = {'state': state, 'frame': frame, 'matches_native_count': passed}
        t.persist()
        if not passed:
            raise RuntimeError('visible known trainer services disagree with the native catalog')
        open_filter(t, 'hide'); toggle_known(t, 'hide', False)
    finally:
        state, _ = t.observe('trainer_filter_cleanup_check')
        if state.get('trainer',{}).get('filters',{}).get('used'):
            controller = t.controller; t.controller = 'code'
            try:
                if 'ContextMenu' not in state['panels']: open_filter(t, 'cleanup')
                toggle_known(t, 'cleanup', False)
            finally: t.controller = controller
        state, frame = t.observe('trainer_filter_restored')
        passed = (state.get('trainer',{}).get('filters') == baseline and state.get('money') == money and
                  spell_baseline(t) == spells)
        t.receipt['trainer_filter_restoration'] = {'filters_money_spells_restored': passed, 'frame': frame}
        t.persist()
        if not passed: raise RuntimeError('trainer filter fixture restoration failed')
