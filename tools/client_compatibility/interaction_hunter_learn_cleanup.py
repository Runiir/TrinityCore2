"""Source-bound ordinary Beast Lore logout, offline cleanup and restored reentry."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import struct
import time

from . import actors, lab_runtime as lab
from . import hunter_learn_preservation as preservation
from .hunter_learn_contract import (require, owned_snapshot, cleanup_expected, SPELL, MONEY,
    PRICE, BASE_SPELLS, native_prerequisites)
from .hunter_learn_sources import closed, linked, whole, private_json
from .hunter_rest_accrual import bound
from .observation.journal import entries

PRECISION_CHECKS = ('all_six_offline', 'all_saved_state_unchanged', 'hunter_identity',
    'snapshot_rest_matches', 'exact_float32')
PARK_CHECKS = ('original_character', 'original_saved_rows', 'native_worldserver', 'class_offline',
    'ordinary_logout', 'native_logout', 'delivered_logout', 'all_six_offline', 'protected_actors')
NORMALIZE_CHECKS = ('exact_source', 'all_six_offline', 'creator_only', 'health_preserved', 'protected_actors')
CLEAN_CHECKS = ('exact_source', 'all_six_offline', 'removed_new1462_only', 'exact_refund',
    'saved_inventory_preserved', 'protected_actors')
PET_COLUMNS = ('id', 'entry', 'owner', 'modelid', 'CreatedBySpell', 'PetType', 'level', 'exp',
    'Reactstate', 'name', 'renamed', 'active', 'slot', 'curhealth', 'curmana', 'savetime', 'abdata')


def identity(kind):
    process = lab.owned_process(kind)
    require(process, 'owned ' + kind + ' is absent')
    return {key: process[key] for key in ('pid', 'start_ticks', 'engine', 'build') if key in process}


def shot(path):
    from .interaction_bridge_deploy import shot as capture
    return capture(path)


def snapshot():
    with lab.connection() as con, con.cursor() as q:
        return cursor_snapshot(q, lock=False)


def prepared(t, path):
    from .interaction_owned_class_fixture import prepared as read
    return read(t, path)


def saved(guid):
    from .interaction_owned_class_fixture import saved as read
    return read(guid)


def origin_checks(old):
    from .interaction_owned_class_fixture import origin_checks as read
    return read(old)


def protected(old):
    from .interaction_hunter_fixture import protected as read
    return read(old)


def logout(t):
    from .interaction_owned_language_fixture import logout as ordinary_logout
    return ordinary_logout(t)


def Trial(*args, **kwargs):
    from .interaction_trial import Trial as LiveTrial
    return LiveTrial(*args, **kwargs)


@contextmanager
def scout():
    previous = os.environ.get('CLIENT442_ACTOR')
    os.environ['CLIENT442_ACTOR'] = 'scout'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CLIENT442_ACTOR', None)
        else:
            os.environ['CLIENT442_ACTOR'] = previous


def runtime():
    return {k: identity(k) for k in ('worldserver', 'modern_world', 'client')}


def create_receipt(output, phase, sources, before):
    output = Path(output)
    require(not output.exists() and output.resolve().is_relative_to(lab.ROOT / 'evidence'),
        'requires a new private learning cleanup episode')
    output.mkdir(parents=True, mode=0o700)
    receipt = {'schema': 'client442_hunter_learn_offline_lifecycle_v1', 'started_at': time.time(),
        'completed': False, 'failure': None, 'phase': phase, 'input_sent': False,
        'mutation_sent': False, 'qualification_added': False, 'sources': sources, 'before': before}
    persist(output, receipt)
    return receipt


def persist(output, receipt):
    lab.private_write(Path(output) / 'episode.json', json.dumps(receipt, indent=2) + '\n')


def source_snapshot(value):
    phase = value.get('phase')
    if phase == 'await_owned_class_lobby_review':
        result = value.get('learn_offline_baseline')
    elif phase in ('await_original_selection_review', 'owned_revive_parked_boundary'):
        result = value.get('all_offline_snapshot')
    elif phase in ('hunter_learn_creator_normalized', 'hunter_learn_offline_cleaned'):
        result = value.get('after')
    else:
        raise RuntimeError('exact learning precision requires its own offline source boundary')
    owned_snapshot(result)
    return result


def preflight(output, source):
    """Read native prerequisites at a closed all-offline boundary before launch."""
    old = closed(source)
    before = snapshot()
    require(before == source_snapshot(old), 'prerequisite source is not the current whole offline snapshot')
    h = owned_snapshot(before)
    require(h['saved']['spells'] == BASE_SPELLS and h['native']['money'] == MONEY,
        'prerequisite review requires the exact untrained Hunter')
    ref = bound(source)
    native = {k: identity(k) for k in ('worldserver', 'modern_world')}
    receipt = create_receipt(output, 'hunter_learn_prerequisites_started', [ref], before)
    receipt.update(source=ref, actor=old.get('actor'), runtime=native)
    try:
        prerequisite = native_prerequisites()
        after = snapshot()
        require(after == before and bound(source) == ref and
            {k: identity(k) for k in native} == native, 'read-only prerequisite review source or state changed')
        receipt.update(after=after, prerequisite_fingerprint=prerequisite, completed=True,
            checks={'source_bound': True, 'all_six_offline': True, 'snapshot_preserved': True,
                'untrained_hunter': True, 'native_prerequisites': True}, phase='hunter_learn_prerequisites_reviewed')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def precision(output, source):
    """Read-only exact SQL FLOAT observations; deliberately never constructs Trial."""
    old = closed(source)
    before = snapshot()
    require(before == source_snapshot(old), 'precision source is not the current whole offline snapshot')
    owned_snapshot(before)
    ref, native = bound(source), runtime()
    receipt = create_receipt(output, 'hunter_learn_rest_precision_started', [ref], before)
    receipt.update(source=ref, actor=old.get('actor'), runtime=native, query=preservation.PRECISION_QUERY)
    try:
        require(snapshot() == before and bound(source) == ref, 'precision source or offline snapshot changed before query')
        with lab.connection() as con, con.cursor() as q:
            q.execute(preservation.PRECISION_QUERY)
            rows = q.fetchall()
            require(len(rows) == 1, 'one exact owned Hunter FLOAT row is required')
            row = dict(zip([c[0] for c in q.description], rows[0]))
        row = json.loads(json.dumps(row))
        row['exact_rest_bonus_float32_bits'] = struct.pack('<f', row['exact_rest_bonus']).hex()
        preservation.precision(row, before)
        after = snapshot()
        require(after == before and runtime() == native and bound(source) == ref,
            'read-only precision changed state, source or runtime')
        receipt.update(row=row, after=after, rest_sources=preservation.rest_sources(),
            checks={k: True for k in PRECISION_CHECKS}, completed=True,
            phase='hunter_learn_rest_precision_complete')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def precision_source(path, source_ref, expected):
    e = closed(path)
    require(e.get('phase') == 'hunter_learn_rest_precision_complete' and e.get('source') == source_ref and
        e.get('sources') == [source_ref] and e.get('query') == preservation.PRECISION_QUERY and
        e.get('input_sent') is False and e.get('mutation_sent') is False and e.get('qualification_added') is False and
        e.get('before') == e.get('after') == expected and set(e.get('checks', {})) == set(PRECISION_CHECKS) and
        e.get('rest_sources') == preservation.rest_sources(), 'exact immutable learning FLOAT source differs')
    whole(e, 'checks', len(PRECISION_CHECKS))
    parent = linked(source_ref)
    require(source_snapshot(parent) == expected and parent['finished_at'] <= e['started_at'],
        'precision source boundary or chronology differs')
    preservation.precision(e['row'], expected)
    return e


def logout_checks(rows, session, since, until):
    relevant = [p for p in rows if p.get('session') == session and since <= p.get('time', 0) <= until and
        p.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE') and
        p.get('direction') in ('to_native', 'from_native', 'to_client')]
    wanted = [('CMSG_LOGOUT_REQUEST', 'to_native'), ('SMSG_LOGOUT_COMPLETE', 'from_native'),
        ('SMSG_LOGOUT_COMPLETE', 'to_client')]
    matches = [[p for p in relevant if (p.get('name'), p.get('direction')) == pair] for pair in wanted]
    exact = len(relevant) == 3 and all(len(v) == 1 for v in matches)
    require(exact and since <= matches[0][0]['time'] <= matches[1][0]['time'] <= matches[2][0]['time'] <= until and
        matches[2][0]['time'] - matches[1][0]['time'] < 2 and
        [match[0].get('body') for match in matches] == ['', '', '00'],
        'one ordered native request, native logout and delivered completion is required')
    return relevant


def recovery_contract(source, preparation_ref, old):
    """An excluded actual failure is eligible for housekeeping, never admission."""
    paid = source.get('phase') == 'hunter_learn_recovery_restored'
    require(source.get('phase') in ('hunter_learn_recovery_restored', 'hunter_learn_no_purchase_recovery_restored') and
        source.get('fixture_source') == preparation_ref and source.get('baseline', {}).get('snapshot') == old['learn_offline_baseline'] and
        source.get('failed_whole_excluded') is True and source.get('recovery_only') is True and
        source.get('qualification_added') is False and source.get('train_input_replayed') is False and
        source.get('failed_source') == source.get('purchase_source'), 'recovery-only learning source differs')
    failed_ref = source['failed_source']
    failed = private_json(Path(failed_ref['path']))
    require(bound(Path(failed_ref['path'])) == failed_ref and failed.get('completed') is False and failed.get('failure') and
        failed.get('actor') == source.get('actor') and failed.get('runtime') == source.get('runtime') and
        failed.get('native_session') == source.get('native_session') and failed.get('entry_source') == source.get('entry_source') and
        failed.get('fixture_source') == preparation_ref and failed.get('baseline') == source.get('baseline') and
        failed['started_at'] < failed['finished_at'] <= source['started_at'],
        'recovery source is not the actual unchanged closed failed learning trial')
    expected_saved = {**old['learn_offline_baseline']['6']['saved'],
        'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])} if paid else old['learn_offline_baseline']['6']['saved']
    require(source.get('after_saved') == expected_saved and source.get('after_resources') ==
        {**source['baseline']['resources'], 'money': MONEY - PRICE if paid else MONEY} and
        source.get('book_layout_restored') and source.get('pose_restoration', {}).get('restored') ==
        failed.get('pose_fixture', {}).get('before') and source['pose_restoration'].get('checks') and
        all(v is True for v in source['pose_restoration']['checks'].values()), 'exact failure housekeeping preservation differs')
    if paid:
        from .hunter_learn_contract import TRAINER_GUID, TRAINER
        packets = source.get('purchase_packets', [])
        buys = [p for p in packets if p.get('direction') == 'to_native' and p.get('name') == 'CMSG_TRAINER_BUY_SPELL']
        learns = [p for p in packets if p.get('direction') == 'from_native' and p.get('name') == 'SMSG_LEARNED_SPELL']
        require(failed.get('purchase_input_sent') is True and source.get('purchase_qualified') is False and
            source.get('purchase_input_sent') is True and source.get('purchase_started_at') == failed.get('purchase_started_at') and
            len(buys) == len(learns) == 1 and buys[0].get('body') == struct.pack('<QII', TRAINER_GUID, TRAINER, SPELL).hex() and
            learns[0].get('body') == struct.pack('<II', SPELL, 0).hex() and
            all(p.get('session') == source.get('native_session') for p in buys + learns) and
            source['purchase_started_at'] <= buys[0]['time'] <= learns[0]['time'] <= source['finished_at'] and
            not any(p.get('direction') == 'to_native' and p.get('name') in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in packets),
            'paid recovery needs one attributable native purchase and learn without replay or casts')
    else:
        require(source.get('no_purchase_observed') is True and type(source.get('purchase_packets')) is list and
            not any(p.get('name') in ('CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS',
                'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in source['purchase_packets']),
            'no-purchase recovery cannot refund an actual purchase')
    return paid, expected_saved, failed_ref


def park(t, preparation, source, recovery=False):
    old = prepared(t, preparation)
    e = closed(source)
    phases = ('hunter_learn_recovery_restored', 'hunter_learn_no_purchase_recovery_restored') if recovery else (
        'hunter_learn_online_restored', 'hunter_learn_reentry_verified')
    require(e.get('phase') in phases and
        e.get('actor') == t.fixture and e.get('runtime') == t.receipt['runtime'] and
        e.get('fixture_source') == bound(preparation) and e['finished_at'] <= t.receipt['started_at'],
        'whole restored online learning source differs')
    require(recovery or not e.get('recovery_only'), 'ordinary learning park cannot admit recovery-only work')
    if recovery:
        _, expected_saved, _ = recovery_contract(e, bound(preparation), old)
        t.receipt.update(recovery_only=True, failed_whole_excluded=True, purchase_qualified=False,
            failed_source=e['failed_source'], train_input_replayed=False)
    elif e['phase'] == 'hunter_learn_online_restored':
        purchase = linked(e['purchase_source'])
        whole(purchase, 'purchase_checks', 10)
        require(purchase.get('phase') == 'hunter_learn_transition_complete' and
            purchase.get('baseline') == e.get('baseline') and purchase.get('entry_source') == e.get('entry_source') and
            purchase.get('fixture_source') == bound(preparation) and purchase.get('runtime') == t.receipt['runtime'] and
            purchase.get('actor') == t.fixture and e.get('book_layout_restored') and
            e.get('pose_restoration', {}).get('restored') == purchase.get('pose_fixture', {}).get('before') and
            all(v is True for v in e['pose_restoration'].get('checks', {}).values()),
            'online learning requires whole purchase and exact pose/layout restoration')
        expected_saved = {**purchase['baseline']['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
        require(e.get('after_saved') == expected_saved, 'whole online restoration must clear only automatic1462 placement')
    else:
        whole(e, 'checks', 8)
        expected_saved = e['baseline']['saved']
    entry = linked(e['entry_source'])
    require(entry.get('phase') == 'owned_class_entered' and entry.get('fixture_source') == bound(preparation) and
        entry.get('actor') == t.fixture and entry.get('runtime') == t.receipt['runtime'] and
        entry.get('native_session') == e.get('native_session') and
        saved(6) == expected_saved and all(protected(old).values()), 'learning park entry or saved rows differ')
    session = actors.session_entry(t.fixture)['session']
    require(session == e['native_session'], 'ordinary learning park session differs')
    t.receipt.update(source=bound(source), entry_source=e['entry_source'], baseline=e['baseline'],
        rest_baseline_source=e['baseline']['rest_baseline_source'], native_pet_reload=entry['native_pet_reload'],
        native_session=session, input_sent=True, qualification_added=False, phase='hunter_learn_logout_started')
    t.persist()
    t.clean_panels()
    started = time.time()
    t.receipt['logout_started_at'] = started
    t.persist()
    try:
        logout(t)
    finally:
        until = time.time()
        t.receipt['logout_finished_at'] = until
        t.persist()
        t.receipt['logout_packets'] = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')
            if p.get('session') == session and started <= p.get('time', 0) <= until and
            p.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE')]
        t.persist()
    packets = logout_checks(t.receipt['logout_packets'], session, started, until)
    after = snapshot()
    owned_snapshot(after)
    t.receipt['all_offline_snapshot'] = after
    t.persist()
    checks = origin_checks(old)
    checks.update(class_offline=True, ordinary_logout=True, native_logout=True, delivered_logout=True,
        all_six_offline=True, protected_actors=all(after[g] == old['protected_baseline'][g] for g in map(str, range(1, 6))))
    require(set(checks) == set(PARK_CHECKS) and all(v is True for v in checks.values()) and
        after['6']['saved'] == expected_saved, 'normal learning park changed protected or saved rows')
    require(actors.register(2) == old['origin_actor'], 'learning park original registration differs')
    t.receipt.update(checks=checks, logout_packets=packets, logout_started_at=started, logout_finished_at=until,
        all_offline_snapshot=after, retained_class_fixture=after['6']['native'], retained_class_saved=after['6']['saved'],
        retained_class_pets=after['6']['pets'], completed=True, phase='await_original_selection_review',
        frame=shot(t.out / 'origin_selection.png'))


def parking_proof(preparation, park_path, precision_path, recovery=False):
    old, park = closed(preparation), closed(park_path)
    require(old.get('phase') == 'await_owned_class_lobby_review' and
        park.get('phase') == 'await_original_selection_review' and park.get('fixture_source') == bound(preparation) and
        park.get('actor') == old.get('class_actor') and park.get('runtime') == old.get('runtime') and
        set(park.get('checks', {})) == set(PARK_CHECKS), 'source-bound ordinary learning parking differs')
    whole(park, 'checks', 9)
    source = linked(park['source'])
    entry = linked(park['entry_source'])
    phases = ('hunter_learn_recovery_restored', 'hunter_learn_no_purchase_recovery_restored') if recovery else (
        'hunter_learn_online_restored', 'hunter_learn_reentry_verified')
    require(source.get('phase') in phases and
        source.get('entry_source') == park['entry_source'] and source.get('baseline') == park['baseline'] and
        source.get('fixture_source') == park['fixture_source'] and source.get('actor') == park['actor'] and
        source.get('runtime') == park['runtime'] and source.get('native_session') == park['native_session'] and
        entry.get('rest_baseline_source') == park['rest_baseline_source'] and
        entry.get('native_pet_reload') == park['native_pet_reload'] and
        entry.get('fixture_source') == park['fixture_source'] and entry.get('runtime') == park['runtime'] and
        entry.get('actor') == park['actor'] and entry.get('native_session') == park['native_session'] and
        entry['finished_at'] <= source['started_at'] < source['finished_at'] <= park['started_at'],
        'learning parking entry, restoration ancestry or chronology differs')
    require(recovery or not park.get('recovery_only') and not source.get('recovery_only'),
        'ordinary learning preservation cannot admit an excluded recovery')
    logout_checks(park['logout_packets'], park['native_session'], park['logout_started_at'], park['logout_finished_at'])
    baseline = old['learn_offline_baseline']
    before_precision = precision_source(Path(park['rest_baseline_source']['path']), bound(preparation), baseline)
    require(bound(Path(park['rest_baseline_source']['path'])) == park['rest_baseline_source'],
        'native login exact baseline source digest differs')
    after_precision = precision_source(precision_path, bound(park_path), park['all_offline_snapshot'])
    require(before_precision.get('rest_sources') == after_precision.get('rest_sources') and
        before_precision.get('runtime') == after_precision.get('runtime') == park['runtime'] and
        before_precision['finished_at'] <= entry['started_at'], 'learning rest formula, config or runtime changed')
    current = park['all_offline_snapshot']
    if recovery:
        require(park.get('recovery_only') is True and park.get('failed_whole_excluded') is True and
            park.get('purchase_qualified') is False and park.get('failed_source') == source.get('failed_source'),
            'recovery parking must preserve whole-trial exclusion')
        paid, expected_saved, _ = recovery_contract(source, bound(preparation), old)
        money = MONEY - PRICE if paid else MONEY
    elif source['phase'] == 'hunter_learn_online_restored':
        purchase = linked(source['purchase_source'])
        whole(purchase, 'purchase_checks', 10)
        require(purchase.get('phase') == 'hunter_learn_transition_complete' and
            purchase.get('baseline') == park['baseline'] and purchase.get('entry_source') == park['entry_source'] and
            purchase.get('actor') == park['actor'] and purchase.get('runtime') == park['runtime'] and
            purchase.get('fixture_source') == park['fixture_source'], 'whole source purchase differs at cleanup')
        expected_saved = {**purchase['baseline']['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
        require(source.get('after_saved') == expected_saved and source.get('book_layout_restored') and
            source.get('pose_restoration', {}).get('restored') == purchase.get('pose_fixture', {}).get('before') and
            source['pose_restoration'].get('checks') and
            all(v is True for v in source['pose_restoration']['checks'].values()),
            'whole source online saved, book or pose restoration differs')
        money = MONEY - PRICE
    else:
        whole(source, 'checks', 8)
        money, expected_saved = MONEY, baseline['6']['saved']
    proof = preservation.parked_preservation(baseline, current, entry, before_precision['row'],
        after_precision['row'], money, expected_saved)
    preservation.creator_expected(baseline, current, park['native_pet_reload'])
    return {**proof, 'entry_source': park['entry_source'], 'before_precision_source': park['rest_baseline_source'],
        'after_precision_source': bound(precision_path), 'rest_sources': before_precision['rest_sources']}


def cursor_snapshot(q, lock=True):
    """Read the complete established six-actor projection on the mutation connection."""
    suffix = ' FOR UPDATE' if lock else ''
    result = {}
    def rows(query, args):
        q.execute(query + suffix, args)
        return json.loads(json.dumps(q.fetchall()))
    for guid in range(1, 7):
        account = 1 if guid == 1 else 2
        q.execute('SELECT * FROM client442_characters.characters WHERE guid=%s AND account=%s' + suffix, (guid, account))
        native_rows = q.fetchall()
        require(len(native_rows) == 1, 'locked owned actor is absent or ambiguous')
        native = json.loads(json.dumps(dict(zip([c[0] for c in q.description], native_rows[0]))))
        spells = rows('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=%s ORDER BY spell', (guid,))
        skills = rows('SELECT skill,value,max FROM client442_characters.character_skills WHERE guid=%s ORDER BY skill', (guid,))
        actions = rows('SELECT spec,button,action,type FROM client442_characters.character_action WHERE guid=%s ORDER BY spec,button', (guid,))
        quests = {table: rows('SELECT * FROM client442_characters.' + table + ' WHERE guid=%s ORDER BY quest', (guid,))
            for table in ('character_queststatus', 'character_queststatus_rewarded')}
        q.execute('SELECT * FROM client442_characters.character_pet WHERE owner=%s ORDER BY id' + suffix, (guid,))
        pets = json.loads(json.dumps([dict(zip([c[0] for c in q.description], row)) for row in q.fetchall()]))
        inventory = rows('SELECT ci.*,ii.* FROM client442_characters.character_inventory ci '
            'JOIN client442_characters.item_instance ii ON ii.guid=ci.item WHERE ci.guid=%s ORDER BY ci.bag,ci.slot', (guid,))
        result[str(guid)] = {'native': native, 'saved': {'spells': spells, 'skills': skills, 'actions': actions, 'quests': quests},
            'pets': pets, 'inventory': inventory}
    owned_snapshot(result)
    return result


def transaction(before, expected, source_guard, mutation, checkpoint=None):
    """Lock and compare all state, then verify the entire delta before commit."""
    owned_snapshot(before)
    owned_snapshot(expected)
    source_guard()
    require(snapshot() == before, 'offline snapshot changed before transaction')
    with lab.connection() as con, con.cursor() as q:
        con.begin()
        try:
            require(cursor_snapshot(q) == before, 'locked six-actor snapshot changed before mutation')
            source_guard()
            mutation(q)
            require(cursor_snapshot(q) == expected, 'transaction postcondition exceeds the declared delta')
            source_guard()
            if checkpoint:
                checkpoint('commit_attempted')
            con.commit()
            if checkpoint:
                checkpoint('transaction_committed')
        except BaseException:
            con.rollback()
            raise
    after = snapshot()
    require(after == expected, 'committed six-actor snapshot differs from the verified delta')
    source_guard()
    return after


def commit_checkpoint(output, receipt):
    def checkpoint(key):
        receipt[key] = True
        persist(output, receipt)
    return checkpoint


def cleanup_sql(q):
    q.execute('DELETE FROM client442_characters.character_spell WHERE guid=6 AND spell=1462 AND active=1 AND disabled=0 '
        'AND NOT EXISTS (SELECT 1 FROM client442_characters.characters WHERE guid IN (1,2,3,4,5,6) AND online<>0)')
    require(q.rowcount == 1, 'exact newly learned active1462 row was not removed once')
    q.execute('UPDATE client442_characters.characters SET money=8708 WHERE guid=6 AND account=2 AND name=%s '
        'AND race=1 AND class=3 AND level=10 AND online=0 AND money=8062', ('Harnesshunt',))
    require(q.rowcount == 1, 'exact owned offline Hunter purchase refund did not match once')


def creator_sql(q, before, expected):
    old = {p['id']: p for p in before['6']['pets']}
    restored = next(p for p in expected['6']['pets'] if p['id'] == 16)
    require(set(old) == {4, 16} and all(set(p) == set(PET_COLUMNS) for p in old.values()) and
        old[16]['CreatedBySpell'] == 883 and restored == {**old[16], 'CreatedBySpell': 13481},
        'creator transaction requires the exact creator-only difference')
    where = ' AND '.join('p.`' + k + '`=%s' for k in PET_COLUMNS)
    named = ' AND '.join('n.`' + k + '`=%s' for k in PET_COLUMNS)
    q.execute('UPDATE client442_characters.character_pet p JOIN client442_characters.character_pet n '
        'ON n.id=4 AND n.owner=6 SET p.CreatedBySpell=13481 WHERE ' + where + ' AND ' + named +
        ' AND NOT EXISTS (SELECT 1 FROM client442_characters.characters WHERE guid IN (1,2,3,4,5,6) AND online<>0)',
        tuple(old[16][k] for k in PET_COLUMNS) + tuple(old[4][k] for k in PET_COLUMNS))
    require(q.rowcount == 1, 'exact source-proven offline creator normalization did not match once')


def immutable_guard(refs, native, rest_sources):
    def guard():
        for ref in refs:
            linked(ref)
        require(runtime() == native and preservation.rest_sources() == rest_sources,
            'learning cleanup source, runtime, config or formula changed')
    return guard


def normalize(output, preparation, park_path, precision_path):
    old, park = closed(preparation), closed(park_path)
    rest = parking_proof(preparation, park_path, precision_path)
    before = snapshot()
    require(before == park['all_offline_snapshot'] and runtime() == park['runtime'], 'creator normalization offline boundary differs')
    expected = preservation.creator_expected(old['learn_offline_baseline'], before, park['native_pet_reload'])
    refs = [bound(p) for p in (preparation, park_path, precision_path)]
    receipt = create_receipt(output, 'hunter_learn_creator_normalization_started', refs, before)
    receipt.update(actor=park['actor'], runtime=park['runtime'], source=bound(park_path), fixture_source=bound(preparation),
        precision_source=bound(precision_path), entry_source=park['entry_source'], rest_baseline_source=park['rest_baseline_source'],
        expected_after=expected, native_rest_accrual_preserved=rest,
        normalized_columns=[] if expected == before else ['CreatedBySpell'])
    try:
        guard = immutable_guard(refs, park['runtime'], rest['rest_sources'])
        if expected == before:
            guard()
            after = snapshot()
            require(after == before, 'unchanged native creator normalization boundary changed')
        else:
            receipt['mutation_sent'] = True
            persist(output, receipt)
            after = transaction(before, expected, guard, lambda q: creator_sql(q, before, expected))
        receipt.update(after=after, checks={k: True for k in NORMALIZE_CHECKS},
            completed=True, phase='hunter_learn_creator_normalized')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def clean(output, preparation, transition, restoration, park_path, precision_path, normalization=None):
    old, purchase, restored, park = [closed(p) for p in (preparation, transition, restoration, park_path)]
    refs = [bound(p) for p in (preparation, transition, restoration, park_path, precision_path)]
    require(purchase.get('phase') == 'hunter_learn_transition_complete' and
        restored.get('phase') == 'hunter_learn_online_restored' and restored.get('purchase_source') == refs[1] and
        park.get('source') == refs[2] and park.get('fixture_source') == refs[0] and
        purchase.get('baseline', {}).get('snapshot') == old['learn_offline_baseline'] and
        purchase['finished_at'] <= restored['started_at'] < restored['finished_at'] <= park['started_at'],
        'whole purchase, restoration and ordinary offline cleanup ancestry differs')
    whole(purchase, 'purchase_checks', 10)
    rest = parking_proof(preparation, park_path, precision_path)
    before = snapshot()
    current = park['all_offline_snapshot']
    if normalization is not None:
        normalized = closed(normalization)
        normalized_ref = bound(normalization)
        whole(normalized, 'checks', 5)
        require(normalized.get('phase') == 'hunter_learn_creator_normalized' and normalized.get('source') == refs[3] and
            normalized.get('fixture_source') == refs[0] and normalized.get('precision_source') == refs[4] and
            normalized.get('before') == current and normalized.get('after') == normalized.get('expected_after') ==
            preservation.creator_expected(old['learn_offline_baseline'], current, park['native_pet_reload']) and
            normalized.get('native_rest_accrual_preserved') == rest and normalized.get('input_sent') is False and
            normalized.get('qualification_added') is False and normalized.get('runtime') == park['runtime'],
            'source-proven creator normalization differs')
        refs.append(normalized_ref)
        current = normalized['after']
    require(before == current and runtime() == park['runtime'], 'offline learning cleanup boundary differs')
    expected = cleanup_expected(old['learn_offline_baseline'], before)
    receipt = create_receipt(output, 'hunter_learn_offline_cleanup_started', refs, before)
    receipt.update(actor=park['actor'], runtime=park['runtime'], preparation_source=refs[0], purchase_source=refs[1],
        restoration_source=refs[2], park_source=refs[3], precision_source=refs[4],
        creator_normalization_source=refs[5] if normalization else None, expected_after=expected,
        native_rest_accrual_preserved=rest, refunded_copper=PRICE, removed_spell=SPELL,
        commit_attempted=False, transaction_committed=False)
    try:
        guard = immutable_guard(refs, park['runtime'], rest['rest_sources'])
        receipt['mutation_sent'] = True
        persist(output, receipt)
        after = transaction(before, expected, guard, cleanup_sql, commit_checkpoint(output, receipt))
        receipt.update(after=after, checks={k: True for k in CLEAN_CHECKS},
            completed=True, phase='hunter_learn_offline_cleaned')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def clean_recovery(output, preparation, restoration, park_path, precision_path):
    old, restored, park = [closed(p) for p in (preparation, restoration, park_path)]
    require(restored.get('phase') == 'hunter_learn_recovery_restored' and park.get('source') == bound(restoration),
        'recovery cleanup requires a paid whole-trial-excluded restoration and ordinary park')
    paid, _, failed_ref = recovery_contract(restored, bound(preparation), old)
    require(paid, 'no-purchase recovery has no newly learned spell or refund to clean')
    rest = parking_proof(preparation, park_path, precision_path, recovery=True)
    before = snapshot()
    require(before == park['all_offline_snapshot'] and runtime() == park['runtime'], 'paid recovery offline boundary differs')
    expected = cleanup_expected(old['learn_offline_baseline'], before)
    refs = [bound(p) for p in (preparation, restoration, park_path, precision_path)]
    receipt = create_receipt(output, 'hunter_learn_recovery_cleanup_started', refs + [failed_ref], before)
    receipt.update(actor=park['actor'], runtime=park['runtime'], preparation_source=refs[0], restoration_source=refs[1],
        park_source=refs[2], precision_source=refs[3], failed_source=failed_ref, expected_after=expected,
        native_rest_accrual_preserved=rest, recovery_only=True, failed_whole_excluded=True,
        purchase_qualified=False, train_input_replayed=False, removed_spell=SPELL, refunded_copper=PRICE,
        commit_attempted=False, transaction_committed=False)
    try:
        ordinary_guard = immutable_guard(refs, park['runtime'], rest['rest_sources'])
        def guard():
            ordinary_guard()
            recovery_contract(linked(refs[1]), refs[0], linked(refs[0]))
        receipt['mutation_sent'] = True
        persist(output, receipt)
        after = transaction(before, expected, guard, cleanup_sql, commit_checkpoint(output, receipt))
        receipt.update(after=after, checks={k: True for k in CLEAN_CHECKS},
            completed=True, phase='hunter_learn_recovery_offline_cleaned')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def settle_clean(output, failed_path, recovery=False):
    """Observe an already committed declared cleanup; never replay DELETE/refund."""
    failed = private_json(failed_path)
    failed_ref = bound(failed_path)
    phase = 'hunter_learn_recovery_cleanup_started' if recovery else 'hunter_learn_offline_cleanup_started'
    require(failed.get('schema') == 'client442_hunter_learn_offline_lifecycle_v1' and
        failed.get('phase') == phase and failed.get('completed') is False and
        type(failed.get('failure')) is str and failed['failure'] and
        type(failed.get('started_at')) in (int, float) and type(failed.get('finished_at')) in (int, float) and
        failed['started_at'] < failed['finished_at'] and failed.get('mutation_sent') is True and
        failed.get('input_sent') is False and failed.get('qualification_added') is False and
        failed.get('commit_attempted') is True and type(failed.get('transaction_committed')) is bool and
        (recovery or not failed.get('recovery_only')), 'settlement requires an actual closed failed cleanup commit attempt')
    role_names = ('preparation_source', 'restoration_source', 'park_source', 'precision_source') if recovery else (
        'preparation_source', 'purchase_source', 'restoration_source', 'park_source', 'precision_source')
    refs = [failed[name] for name in role_names]
    if not recovery and failed.get('creator_normalization_source'):
        refs.append(failed['creator_normalization_source'])
    expected_sources = refs + [failed['failed_source']] if recovery else refs
    require(failed.get('sources') == expected_sources, 'cleanup commit attempt source roles differ')
    sources = {name: linked(failed[name]) for name in role_names}
    old, park = sources['preparation_source'], sources['park_source']
    restored = sources['restoration_source']
    require(park.get('source') == failed['restoration_source'] and park.get('fixture_source') == failed['preparation_source'] and
        failed.get('actor') == park.get('actor') and failed.get('runtime') == park.get('runtime') and
        failed.get('removed_spell') == SPELL and failed.get('refunded_copper') == PRICE,
        'settlement original owned restoration or exact declared delta differs')
    if recovery:
        require(recovery_contract(restored, failed['preparation_source'], old)[0] and
            failed.get('failed_source') == restored.get('failed_source') and failed.get('recovery_only') is True and
            failed.get('failed_whole_excluded') is True and failed.get('purchase_qualified') is False and
            failed.get('train_input_replayed') is False, 'cleanup recovery settlement lost whole-trial exclusion')
    else:
        purchase = sources['purchase_source']
        whole(purchase, 'purchase_checks', 10)
        require(purchase.get('phase') == 'hunter_learn_transition_complete' and
            restored.get('phase') == 'hunter_learn_online_restored' and restored.get('purchase_source') == failed['purchase_source'] and
            purchase.get('baseline', {}).get('snapshot') == old['learn_offline_baseline'],
            'ordinary settlement cannot adopt a different or excluded purchase')
    rest = parking_proof(Path(failed['preparation_source']['path']), Path(failed['park_source']['path']),
        Path(failed['precision_source']['path']), recovery=recovery)
    original_before = park['all_offline_snapshot']
    if not recovery and failed.get('creator_normalization_source'):
        normalized = linked(failed['creator_normalization_source'])
        whole(normalized, 'checks', 5)
        require(normalized.get('phase') == 'hunter_learn_creator_normalized' and normalized.get('source') == failed['park_source'] and
            normalized.get('precision_source') == failed['precision_source'] and normalized.get('before') == original_before and
            normalized.get('after') == normalized.get('expected_after') ==
            preservation.creator_expected(old['learn_offline_baseline'], original_before, park['native_pet_reload']),
            'committed cleanup creator baseline differs')
        original_before = normalized['after']
    expected = cleanup_expected(old['learn_offline_baseline'], original_before)
    require(failed.get('before') == original_before and failed.get('expected_after') == expected and
        failed.get('native_rest_accrual_preserved') == rest and runtime() == failed['runtime'],
        'settlement cannot change the failed cleanup declaration')
    current = snapshot()
    require(current == expected, 'cleanup has not reached its exact declared committed state; never replay it')
    output_phase = 'hunter_learn_recovery_cleanup_settlement_started' if recovery else 'hunter_learn_offline_cleanup_settlement_started'
    receipt = create_receipt(output, output_phase, expected_sources + [failed_ref], original_before)
    receipt.update({k: deepcopy(v) for k, v in failed.items() if k not in (
        'started_at', 'finished_at', 'completed', 'failure', 'phase', 'input_sent', 'mutation_sent', 'sources',
        'commit_attempted', 'transaction_committed', 'after', 'checks')})
    receipt.update(cleanup_failed_source=failed_ref, settled_commit_only=True, original_mutation_sent=True,
        transaction_committed=True, commit_attempted=False)
    try:
        guard = immutable_guard(refs, failed['runtime'], rest['rest_sources'])
        guard()
        require(bound(failed_path) == failed_ref and private_json(failed_path) == failed and
            failed['finished_at'] <= receipt['started_at'], 'actual failed commit attempt digest or chronology changed')
        after = snapshot()
        require(after == current == expected, 'committed cleanup settlement state changed during read-only verification')
        guard()
        require(bound(failed_path) == failed_ref, 'actual failed cleanup source changed during settlement')
        receipt.update(after=after, checks={k: True for k in CLEAN_CHECKS}, completed=True,
            phase='hunter_learn_recovery_offline_cleaned' if recovery else 'hunter_learn_offline_cleaned')
    except BaseException as error:
        receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist(output, receipt)
    return receipt


def prepare(t, preparation, cleaned_path, finish_path):
    old, cleaned, finish = [closed(p) for p in (preparation, cleaned_path, finish_path)]
    baseline = cleaned.get('after')
    owned_snapshot(baseline)
    require(t.fixture == actors.load() == old.get('origin_actor') and old.get('origin_actor', {}).get('guid') == 2 and
        old.get('class_actor', {}).get('guid') == 6 and cleaned.get('phase') == 'hunter_learn_offline_cleaned' and
        cleaned.get('preparation_source') == bound(preparation) and
        cleaned.get('before') and cleaned.get('after') == cleaned.get('expected_after') ==
        cleanup_expected(old['learn_offline_baseline'], cleaned['before']) and
        finish.get('fixture_source') == bound(preparation) and finish.get('actor') == t.fixture and
        all(e.get('runtime') == t.receipt['runtime'] for e in (old, cleaned, finish)) and
        old['finished_at'] < cleaned['started_at'] < cleaned['finished_at'] <= finish['started_at'] <
        finish['finished_at'] <= t.receipt['started_at'] and snapshot() == baseline,
        'fresh cleaned reentry preparation requires the reviewed original selection')
    whole(finish, 'checks', 5)
    require(baseline['6']['saved']['spells'] == BASE_SPELLS and baseline['6']['native']['money'] == MONEY and
        all(protected(old).values()), 'cleaned reentry baseline or protected actors differ')
    checks = origin_checks(old)
    checks.update({f'actor_{g}_unchanged': baseline[g] == old['protected_baseline'][g] for g in map(str, range(1, 6))})
    t.receipt.update(source=bound(cleaned_path), cleaned_source=bound(cleaned_path), original_finish_source=bound(finish_path),
        previous_preparation_source=bound(preparation), origin_actor=old['origin_actor'], origin_native=baseline['2']['native'],
        origin_saved=baseline['2']['saved'], origin_roster=old['origin_roster'], class_actor=old['class_actor'],
        natural_native=baseline['6']['native'], natural_saved=baseline['6']['saved'], retained_class_pets=baseline['6']['pets'],
        protected_baseline={g: baseline[g] for g in map(str, range(1, 6))}, learn_offline_baseline=baseline,
        accepted_previous_sources=old['accepted_previous_sources'], remote_source=old['remote_source'],
        primary_stop_source=old['primary_stop_source'], learning_reentry_only=True, checks=checks,
        input_sent=False, qualification_added=False)
    t.persist()
    require(actors.register(6) == old['class_actor'], 'cleaned Hunter registration differs')
    t.receipt.update(completed=True, phase='await_owned_class_lobby_review', frame=shot(t.out / 'owned_lobby.png'))


def reentry(t, preparation, entry_path, cleaned_path):
    from .interaction_spellbook_learn_spell import caption, restore_layout
    from .interaction_spellbook_navigation import wire_known, known
    from .interaction_spellbook_recon import resources
    from .observation.inventory import Inventory
    old = prepared(t, preparation)
    entry, cleaned = closed(entry_path), closed(cleaned_path)
    require(old.get('learning_reentry_only') is True and old.get('cleaned_source') == bound(cleaned_path) and
        cleaned.get('phase') == 'hunter_learn_offline_cleaned' and old['learn_offline_baseline'] == cleaned['after'] and
        entry.get('phase') == 'owned_class_entered' and entry.get('fixture_source') == bound(preparation) and
        entry.get('actor') == t.fixture and entry.get('runtime') == t.receipt['runtime'] and
        entry.get('learn_offline_baseline') == old['learn_offline_baseline'] and
        entry['finished_at'] <= t.receipt['started_at'], 'restored ordinary Hunter entry ancestry differs')
    session = actors.session_entry(t.fixture)['session']
    login = wire_known(t, session)
    oracle = Inventory(lab.ROOT, session, 6).poll()
    t.clean_panels()
    probe, row = caption(t, login, 'hunter_learn_restored_future', False)
    purchase = linked(cleaned['purchase_source'])
    layout_restored = restore_layout(t, login, purchase['book_layout_baseline'])
    t.clean_panels()
    state, frame = t.observe('hunter_learn_restored_clean')
    h = cleaned['after']['6']
    checks = {'exact_native1462_absent': SPELL not in login, 'saved_spell_baseline': known(6) == BASE_SPELLS,
        'saved_rows_baseline': saved(6) == h['saved'], 'resource_baseline': resources(oracle) == entry['resources'] ==
            purchase['baseline']['resources'],
        'refund_preserved': resources(oracle)['money'] == MONEY, 'stock_future_row': row['kind'] == 'FUTURESPELL',
        'protected_actors': all(protected(old).values()),
        'public_clean': not state.get('lua_errors') and not state.get('blocked_actions') and not state.get('panels')}
    require(session == entry['native_session'] and all(v is True for v in checks.values()),
        'restored Hunter native absence, FUTURESPELL, resource or public preservation differs')
    baseline = {'snapshot': old['learn_offline_baseline'], 'saved': h['saved'], 'resources': entry['resources'],
        'pets': h['pets'], 'entry_source': bound(entry_path), 'rest_baseline_source': entry['rest_baseline_source'],
        'native_pet_reload': entry['native_pet_reload'], 'prerequisite_fingerprint': native_prerequisites()}
    t.receipt.update(entry_source=bound(entry_path), cleaned_source=bound(cleaned_path), baseline=baseline,
        native_session=session, login_known_spell_ids=sorted(login), future_probe=probe, future_row=row,
        book_layout_baseline=purchase['book_layout_baseline'], book_layout_restored=layout_restored,
        checks=checks, state=state, frame=frame, completed=True, input_sent=True, qualification_added=False,
        phase='hunter_learn_reentry_verified')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['preflight', 'precision', 'park', 'park-recovery', 'normalize', 'clean',
        'clean-recovery', 'settle-clean', 'settle-clean-recovery', 'prepare', 'reentry'])
    p.add_argument('--output', type=Path, required=True)
    for name in ('source', 'preparation', 'transition', 'restore', 'park', 'precision', 'normalization', 'cleaned', 'finish', 'entry'):
        p.add_argument('--' + name, type=Path)
    a = p.parse_args()
    needed = {'preflight': ('source',), 'precision': ('source',), 'park': ('preparation', 'source'),
        'park-recovery': ('preparation', 'source'),
        'normalize': ('preparation', 'park', 'precision'), 'clean': ('preparation', 'transition', 'restore', 'park', 'precision'),
        'clean-recovery': ('preparation', 'restore', 'park', 'precision'),
        'settle-clean': ('source',), 'settle-clean-recovery': ('source',),
        'prepare': ('preparation', 'cleaned', 'finish'), 'reentry': ('preparation', 'entry', 'cleaned')}[a.action]
    if not all(getattr(a, name) is not None for name in needed):
        p.error('requires ' + ', '.join('--' + name for name in needed))
    with scout():
        if a.action == 'preflight':
            result = preflight(a.output, a.source)
        elif a.action == 'precision':
            result = precision(a.output, a.source)
        elif a.action == 'normalize':
            result = normalize(a.output, a.preparation, a.park, a.precision)
        elif a.action == 'clean':
            result = clean(a.output, a.preparation, a.transition, a.restore, a.park, a.precision, a.normalization)
        elif a.action == 'clean-recovery':
            result = clean_recovery(a.output, a.preparation, a.restore, a.park, a.precision)
        elif a.action in ('settle-clean', 'settle-clean-recovery'):
            result = settle_clean(a.output, a.source, recovery=a.action == 'settle-clean-recovery')
        else:
            from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
            t = Trial(a.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
            t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
            try:
                if a.action in ('park', 'park-recovery'): park(t, a.preparation, a.source, recovery=a.action == 'park-recovery')
                elif a.action == 'prepare': prepare(t, a.preparation, a.cleaned, a.finish)
                else: reentry(t, a.preparation, a.entry, a.cleaned)
            except BaseException as error:
                t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
                if not isinstance(error, Exception):
                    raise
            finally:
                t.receipt['finished_at'] = time.time()
                t.persist()
            result = t.receipt
        print(json.dumps({k: result.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
