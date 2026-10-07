"""Pure proof of ordinary Beast Lore learning, cleanup, reentry and shutdown.

No client, UI, SQL or protocol translation module is imported here. ``proof``
reads only supplied archive values; ``close`` reads private JSON sources and
writes a distinct parked boundary for the separately attributed resource pause.
Neither entry point admits an operation to the qualification ledger.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time

from . import lab_runtime as lab
from .hunter_learn_contract import (SPELL, TRAINER_GUID, TRAINER, PRICE, MONEY, BASE_SPELLS,
    DBC_HASHES, EFFECT, ABILITY, TRAINER_ROW, book_row, learned_checks, reconciled_known,
    cleanup_expected, owned_snapshot, untrained_boundary, fingerprint)
from .hunter_learn_preservation import (PRECISION_QUERY, POSE_KEYS, precision, parked_preservation,
    creator_expected)
from .hunter_learn_sources import (require, whole, closed, linked, private_json, POINTER,
    ARCHIVE_SHA256, ARCHIVE_BYTES, REMOTE_SHA256, CHECKPOINT_SHA256)
from .hunter_rest_accrual import bound, FORMULA_SOURCE
from .hunter_learn_autobar import addition_guard, clear_guard, PICKUP_SOURCE, BINDING_SOURCE
from .world.buffer import Reader
from .hunter_learn_pet import reload_proof
from .hunter_learn_trainer import validate_trainer_identity, SPAWN_SOURCE


SCHEMA = 'client442_owned_hunter_learn_closure_v1'
PHASE = 'hunter_learn_parked_boundary'
ROLES = ('preparation', 'purchase', 'restoration', 'first_park', 'first_precision',
    'cleaned', 'reentry', 'final_park', 'final_precision', 'finish')
OPTIONAL_ROLES = ('first_normalization', 'final_normalization')
CLOSURE_NAMES = frozenset(('untrained_owned_baseline', 'accepted_previous_remote',
    'same_native_bridge_client', 'ordinary_untrained_entry', 'stock_future_caption',
    'existing_trainer', 'available_selected_lesson', 'one_exact_purchase',
    'ordered_native_modern_learn', 'saved_direct_spell_only', 'exact_resource_charge',
    'stock_learned_caption', 'original_stock_layout', 'original_exact_pose',
    'first_ordinary_logout', 'first_exact_rest_accounting', 'first_pet_preservation',
    'exact_offline_cleanup', 'restored_ordinary_reentry', 'restored_future_caption',
    'final_ordinary_logout', 'final_exact_rest_accounting', 'final_pet_preservation',
    'original_selection_restored', 'all_six_offline', 'protected_actors_unchanged',
    'primary_remains_stopped', 'no_qualification_added'))
PURCHASE_NAMES = frozenset(('one_exact_native_purchase', 'owned_ordered_learn_delivery',
    'no_purchase_failure', 'saved_direct_spell_only', 'exact_charge_resources',
    'ordinary_train', 'protected_originals', 'saved_rows', 'no_spell_or_pet_cast', 'ui_clean'))
PRECISION_NAMES = ('all_six_offline', 'all_saved_state_unchanged', 'hunter_identity',
    'snapshot_rest_matches', 'exact_float32')
PARK_NAMES = ('original_character', 'original_saved_rows', 'native_worldserver', 'class_offline',
    'ordinary_logout', 'native_logout', 'delivered_logout', 'all_six_offline', 'protected_actors')
NORMALIZE_NAMES = ('exact_source', 'all_six_offline', 'creator_only', 'health_preserved', 'protected_actors')
CLEAN_NAMES = ('exact_source', 'all_six_offline', 'removed_new1462_only', 'exact_refund',
    'saved_inventory_preserved', 'protected_actors')
REENTRY_NAMES = ('exact_native1462_absent', 'saved_spell_baseline', 'saved_rows_baseline',
    'resource_baseline', 'refund_preserved', 'stock_future_row', 'protected_actors', 'public_clean')
PAUSE_NAMES = ('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration')
PACKET_NAMES = frozenset(('CMSG_TRAINER_BUY_SPELL', 'SMSG_TRAINER_BUY_FAILED',
    'SMSG_TRAINER_BUY_SUCCEEDED', 'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS',
    'CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD', 'SMSG_SEND_KNOWN_SPELLS',
    'SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT', 'CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE',
    'SMSG_UPDATE_ACTION_BUTTONS', 'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION', 'SMSG_TRAINER_LIST',
    'SMSG_ON_MONSTER_MOVE', 'SMSG_ON_MONSTER_MOVE_TRANSPORT', 'SMSG_MOVE_UPDATE_TELEPORT'))
TRACKING_MEMBERS = ('tracking/packets.jsonl', 'tracking/events.jsonl')
# The inspected storage implementation is unchanged from accepted UI169.
FLOAT_SOURCES = {
    'src/server/database/Database/Field.cpp': 'eed8ddfa345c74109afa258db9f72c1d7e828e069c4ca1caf7e4ea0275e7b662',
    'src/server/database/Database/QueryResult.cpp': '56ac195234501b795956949846de208c8e5ab2fdaeeee29a56291a404ce6bdc1',
    'src/server/database/Database/MySQLPreparedStatement.cpp': '11dcd2db84b932850149ce4bad4107ba717c07d96c495e58577a91eec5bd4553',
    'sql/base/characters_database.sql': '880d4c7a92c600dd1cbdb4f3a1f388a4631de0cc08a34e176e078a6d8ea03be9'}
REST_CONFIG_SHA256 = 'c41c11b4c6f38113a0cbf355fa80f279d0c70b6469c1a6f8392e9123412e75f7'
REST_FORMULA_SHA256 = 'ca09174ed5c4c2afaa5aeaf188c52282a622da11e19fd0059cdd77b0748771f3'
FORMULA_SNIPPETS = ['float bubble0 = 0.031f;',
    'bubble0*sWorld->getRate(RATE_REST_OFFLINE_IN_WILDERNESS)',
    'SetRestBonus(GetRestBonus() + time_diff*((float)GetUInt32Value(PLAYER_NEXT_LEVEL_XP) / 72000)*bubble);']


def packet_key(value):
    return tuple(value.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


def accepted(value, phase=None):
    require(isinstance(value, dict), 'whole episode must be a JSON object')
    require(value.get('completed') is True and value.get('failure') is None and
        value.get('recovery_only') is not True and value.get('failed_whole_excluded') is not True and
        value.get('settlement_only') is not True and value.get('failed_repair_excluded') is not True and
        all(type(value.get(k)) in (int, float) and math.isfinite(value[k]) for k in ('started_at', 'finished_at')) and
        value['started_at'] < value['finished_at'] and (phase is None or value.get('phase') == phase),
        'whole successful episode phase or interval differs')
    return value


class Sources:
    """Resolve immutable references by exact archive path, or a carried digest."""
    def __init__(self, data, digests, local=False):
        self.data, self.digests, self.local = data, digests, local
        self.ancestry = [v for v in data.values() if isinstance(v, dict) and
            v.get('schema') == 'client442_hunter_learn_ancestry_v1']

    def get(self, ref, successful=True):
        require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and isinstance(ref['path'], str) and
            re.fullmatch('[0-9a-f]{64}', ref.get('sha256', '')), 'complete source reference is required')
        path = Path(ref['path'])
        require(path.is_absolute() and path.is_relative_to(lab.ROOT / 'evidence'), 'source is outside private evidence')
        member = str(path.relative_to(lab.ROOT))
        if member not in self.data and self.local:
            value = linked(ref) if successful and path.name == 'episode.json' else private_json(path, False)
            require(bound(path) == ref, 'source JSON digest changed')
            self.data[member], self.digests[member] = value, ref['sha256']
        matches = [name for name, digest in self.digests.items() if digest == ref['sha256'] and name in self.data]
        key = member if member in self.data and self.digests.get(member) == ref['sha256'] else None
        if key is None:
            require(len(self.ancestry) == 1, 'carried source requires its exact ancestry manifest')
            rows = [r for r in self.ancestry[0].get('sources', []) if
                r.get('original_path') == ref['path'] and r.get('sha256') == ref['sha256']]
            require(len(rows) == 1, 'source is missing or ambiguous in the immutable ancestry manifest')
            copy = Path(rows[0].get('copy_path', ''))
            require(copy.is_absolute() and copy.is_relative_to(lab.ROOT / 'evidence'), 'carried source copy is outside private evidence')
            key = str(copy.relative_to(lab.ROOT))
            require(key in matches, 'carried source copy differs from its actual archived digest')
        value = self.data[key]
        return accepted(value) if successful else value


def checks(value, key, names):
    require(set(value.get(key, {})) == set(names), 'exact ' + key + ' schema differs')
    whole(value, key, len(names))


def precision_proof(value, source, snapshot):
    accepted(value, 'hunter_learn_rest_precision_complete')
    require(value.get('query') == PRECISION_QUERY and value.get('source') == source and
        value.get('before') == value.get('after') == snapshot and value.get('input_sent') is False and
        value.get('mutation_sent') is False and value.get('qualification_added') is False,
        'exact read-only rest precision source differs')
    checks(value, 'checks', PRECISION_NAMES)
    precision(value['row'], snapshot)
    binding = value.get('rest_sources', value.get('rest_formula_sources', {}))
    require(binding.get('rate') == 1 and type(binding.get('rate')) in (int, float) and
        binding.get('formula_snippets') == FORMULA_SNIPPETS and
        binding.get('config_source', {}).get('path') == str(lab.ROOT / 'config/worldserver.conf') and
        binding.get('config_source', {}).get('sha256') == REST_CONFIG_SHA256 and
        binding.get('native_formula_source', {}).get('path') == str(lab.REPO / FORMULA_SOURCE) and
        binding.get('native_formula_source', {}).get('sha256') == REST_FORMULA_SHA256,
        'configured native wilderness rest formula differs')
    refs = binding.get('native_float_storage_sources', [])
    require(len(refs) == 4 and {str(Path(r.get('path', '')).relative_to(lab.REPO)): r.get('sha256')
        for r in refs if Path(r.get('path', '')).is_relative_to(lab.REPO)} == FLOAT_SOURCES and
        all(re.fullmatch('[0-9a-f]{64}', r.get('sha256', '')) for r in
            [binding['config_source'], binding['native_formula_source']]), 'native FLOAT storage sources differ')
    return value['row'], binding


def prerequisite(value):
    data = {k: v for k, v in value.items() if k != 'sha256'}
    spell = value.get('spell', [])
    require(value.get('sha256') == fingerprint(data) and value.get('dbc_hashes') == DBC_HASHES and
        len(spell) == 1 and len(spell[0]) == 48 and spell[0][:3] == [SPELL, 65536, 132096] and
        not spell[0][1] & 0x40 and not spell[0][2] & 0x80000000 and
        value.get('effects') == [EFFECT] and value.get('abilities') == [ABILITY] and
        value.get('matching_criteria') == [] and value.get('trainer') == [TRAINER_ROW] and
        value.get('lesson') == [[40, 1462, 680, 0, 0, 0, 0, 0, 10]] and
        set(value.get('relations', {})) == {'learn', 'required', 'pet', 'linked'} and
        not any(value['relations'].values()), 'direct native1462 prerequisite fingerprint differs')


def login_ids(packet):
    body = bytes.fromhex(packet['body'])
    require(len(body) >= 5, 'native known-spell body is truncated')
    initial, count = struct.unpack_from('<BH', body)
    require(initial in (0, 1) and 0 < count <= 16000 and len(body) >= 5 + count * 6,
        'native known-spell header differs')
    ids = [struct.unpack_from('<Ih', body, 3 + i * 6)[0] for i in range(count)]
    cooldowns, = struct.unpack_from('<H', body, 3 + count * 6)
    require(len(body) == 5 + count * 6 + cooldowns * 18 and len(ids) == len(set(ids)),
        'complete native known-spell body differs')
    return initial, ids


def pet_reload(value, entry, rows=None):
    claimed = [value['packet'], *value['update_packets']]
    require(len({packet_key(p) for p in claimed}) == len(claimed), 'pet reload packets are duplicated')
    pets = entry['learn_offline_baseline']['6']['pets']
    baseline_pet = next(p for p in pets if p['id'] == 16)
    derived = reload_proof(claimed if rows is None else rows, entry['native_session'],
        entry['started_at'], entry['finished_at'], baseline_pet)
    canonical = lambda v: json.dumps(json.loads(json.dumps(v)), sort_keys=True, separators=(',', ':'))
    require(canonical(derived) == canonical(value), 'complete exact ordinary pet creation/scaling/reload proof differs')
    return claimed


def logout(park, entry):
    accepted(park, 'await_original_selection_review')
    checks(park, 'checks', PARK_NAMES)
    packets = park.get('logout_packets', [])
    names = [('to_native', 'CMSG_LOGOUT_REQUEST'), ('from_native', 'SMSG_LOGOUT_COMPLETE'),
        ('to_client', 'SMSG_LOGOUT_COMPLETE')]
    selected = [[p for p in packets if (p.get('direction'), p.get('name')) == name] for name in names]
    require(all(len(rows) == 1 for rows in selected), 'one complete ordinary native/client logout is required')
    ordered = [rows[0] for rows in selected]
    require(all(p.get('session') == entry['native_session'] for p in ordered) and
        [p.get('body') for p in ordered] == ['', '', '00'] and
        park['started_at'] <= ordered[0]['time'] <= ordered[1]['time'] <= ordered[2]['time'] <= park['finished_at'] and
        ordered[2]['time'] - ordered[1]['time'] < 2, 'ordered owned ordinary logout packets differ')
    return ordered


def normalized(store, role, refs, before, park, exact, entry):
    snapshot = exact['after']
    wolf = next(p for p in snapshot['6']['pets'] if p['id'] == 16)
    if wolf['CreatedBySpell'] == 13481:
        require(role not in refs, 'unneeded creator normalization must not be borrowed')
        return snapshot
    require(role in refs, 'native pet creator reload requires its separate offline normalization')
    value = store.get(refs[role])
    accepted(value, 'hunter_learn_creator_normalized')
    checks(value, 'checks', NORMALIZE_NAMES)
    require(value.get('source') == refs['first_park' if role == 'first_normalization' else 'final_park'] and
        value.get('precision_source') == refs['first_precision' if role == 'first_normalization' else 'final_precision'] and
        value.get('before') == snapshot and value.get('after') == value.get('expected_after') ==
        creator_expected(before, snapshot, entry['native_pet_reload']) and value.get('input_sent') is False and
        value.get('qualification_added') is False, 'exact separate creator normalization differs')
    require(exact['finished_at'] < value['started_at'], 'creator normalization precedes precision closure')
    return value['after']


def screen_review(store, episode, source, control, fixture_ref):
    screen = episode.get('screen_review', {})
    require(set(screen) == {'path', 'sha256', 'frame'}, 'complete owned screen review reference differs')
    review = store.get({k: screen[k] for k in ('path', 'sha256')}, False)
    frame = screen['frame']
    require(review.get('reviewed') is True and review.get('control') == control and
        review.get('frame') == frame and review.get('fixture_source_sha256') == fixture_ref['sha256'] and
        (source is None or review.get('source') == source), 'exact reviewed control and source caption differs')
    if source is not None:
        require(store.get(source).get('frame') == frame, 'reviewed exact frame differs from its source episode')
    monitor = frame.get('monitor', {})
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == episode['runtime']['client']['pid'] and
        monitor.get('input_isolation', {}).get('actor') == 'scout' and
        monitor.get('input_isolation', {}).get('host_activation_sent') is False,
        'reviewed owned game window or private second-monitor input differs')
    if not store.local:
        sha = frame.get('sha256', '')
        require(re.fullmatch('[0-9a-f]{64}', sha) and any(
            name.endswith('/' + frame.get('file', '')) and digest == sha for name, digest in store.digests.items()),
            'reviewed frame is missing from the complete actual remote PNG manifest')
    return review


def previous_remote(store, preparation):
    require(preparation.get('remote_source', {}).get('sha256') == REMOTE_SHA256 and
        preparation.get('accepted_previous_sources') and len(preparation['accepted_previous_sources']) == 4,
        'accepted normalized UI169 authority is absent')
    remote = store.get(preparation['remote_source'], False)
    require(remote.get('actual_remote_verified') is True and remote.get('complete_json_png_verified') is True and
        remote.get('pointer') == POINTER and remote.get('archive_sha256') == ARCHIVE_SHA256 and
        remote.get('bytes') == ARCHIVE_BYTES and remote.get('proof', {}).get('operation') == 'pets.revive' and
        remote.get('proof', {}).get('qualification_added') is False, 'carried actual UI169 remote proof differs')
    prior = [store.get(ref) for ref in preparation['accepted_previous_sources']]
    accepted(prior[0], 'await_owned_class_lobby_review')
    accepted(prior[1], 'owned_revive_fixture_normalized')
    accepted(prior[2], 'owned_revive_parked_boundary')
    accepted(prior[3], 'parked_scout_resource_paused')
    whole(prior[2], 'checks', 21)
    whole(prior[3], 'checks', 8)
    require(prior[1].get('after') == prior[2].get('all_offline_snapshot') == prior[3].get('before') ==
        prior[3].get('after') == preparation['learn_offline_baseline'] and
        prior[3].get('source') == preparation['accepted_previous_sources'][2] and
        prior[2].get('primary_stop_source') == preparation.get('primary_stop_source'),
        'accepted normalized-close-pause baseline differs')
    resume = store.get(preparation['sources'][0])
    restored = store.get(preparation['sources'][1])
    whole(resume, 'checks', 7)
    whole(restored, 'checks', 3)
    require(resume.get('schema') == 'client442_hunter_learn_scout_resume_v1' and
        resume.get('sources') == preparation['accepted_previous_sources'] and
        resume.get('remote_source') == preparation['remote_source'] and
        resume.get('primary_stop_source') == preparation['primary_stop_source'] and
        resume.get('offline_baselines') == preparation['learn_offline_baseline'] and
        resume.get('runtime') == restored.get('runtime') == preparation['runtime'] and
        restored.get('phase') == 'hunter_learn_scout_original_restored' and
        restored.get('actor') == preparation['origin_actor'] and
        resume.get('restoration_source') == preparation['sources'][1] and
        resume.get('previous_runtime') == prior[3]['runtime'] and
        resume['runtime']['client'] != resume['previous_runtime']['client'] and
        resume['launch_finished_at'] < restored['started_at'] < restored['finished_at'] <=
        resume['finished_at'] < preparation['started_at'], 'fresh scout continuation source roles or chronology differ')
    require(resume.get('checkpoint_source', {}).get('sha256') == CHECKPOINT_SHA256,
        'pinned UI169 checkpoint receipt is absent')
    checkpoint = store.get(resume['checkpoint_source'], False)
    require(checkpoint.get('file', '') + '.dvc' == POINTER and checkpoint.get('sha256') == ARCHIVE_SHA256 and
        checkpoint.get('bytes') == ARCHIVE_BYTES and checkpoint.get('cloud_verified') is True,
        'carried UI169 checkpoint receipt differs')
    for ref in preparation['accepted_previous_sources']:
        member = str(Path(ref['path']).relative_to(lab.ROOT))
        matches = [row for row in checkpoint.get('file_manifest', []) if row.get('path') == member]
        require(len(matches) == 1 and matches[0].get('sha256') == ref['sha256'],
            'carried normalized UI169 source differs from its actual accepted remote manifest')


def lifecycle(store, refs):
    require(set(refs) >= set(ROLES) and set(refs) <= set(ROLES + OPTIONAL_ROLES), 'complete closure source roles differ')
    rows = {name: store.get(refs[name]) for name in ROLES}
    old, purchase, restored, parked, exact, cleaned, reentry, final, final_exact, finish = [rows[k] for k in ROLES]
    accepted(old, 'await_owned_class_lobby_review')
    accepted(purchase, 'hunter_learn_transition_complete')
    accepted(restored, 'hunter_learn_online_restored')
    accepted(cleaned, 'hunter_learn_offline_cleaned')
    accepted(reentry, 'hunter_learn_reentry_verified')
    baseline = old['learn_offline_baseline']
    hunter = untrained_boundary(baseline)
    previous_remote(store, old)
    runtime, origin, actor = old['runtime'], old['origin_actor'], old['class_actor']
    require(origin.get('guid') == 2 and tuple(actor.get(k) for k in ('guid', 'account_id', 'character_name', 'race', 'class', 'level')) ==
        (6, 2, 'Harnesshunt', 1, 3, 10) and old.get('actor') == origin,
        'original and Hunter actor identities differ')
    entry_ref = purchase['entry_source']
    entry = store.get(entry_ref)
    accepted(entry, 'owned_class_entered')
    selected_ref = purchase['purchase_source']
    selected = store.get(selected_ref)
    accepted(selected, 'hunter_learn_lesson_selected')
    trainer_view_ref = selected['source']
    trainer_view = store.get(trainer_view_ref)
    exposed = trainer_view if trainer_view.get('phase') == 'hunter_learn_trainer_exposed' else None
    opened_ref = exposed['source'] if exposed is not None else trainer_view_ref
    opened = store.get(opened_ref)
    accepted(opened, 'hunter_learn_trainer_open')
    staged_ref = opened['source']
    staged = store.get(staged_ref)
    accepted(staged, 'hunter_learn_trainer_staged')
    untrained_ref = staged['source']
    untrained = store.get(untrained_ref)
    phases = ('hunter_learn_untrained_reconciled', 'hunter_learn_trainer_staged',
        'hunter_learn_trainer_open', 'hunter_learn_lesson_selected')
    for value, phase in zip((untrained, staged, opened, selected), phases): accepted(value, phase)
    if exposed is not None:
        accepted(exposed, 'hunter_learn_trainer_exposed')
        require(all(exposed.get(k) == opened.get(k) for k in ('actor', 'runtime', 'native_session',
            'fixture_source', 'entry_source', 'baseline', 'login_known_spell_ids', 'book_layout_baseline',
            'native_catalog', 'pose_fixture')) and opened['finished_at'] <= exposed['started_at'] <
            exposed['finished_at'] <= selected['started_at'], 'one exact source-bound trainer exposure differs')
    first_baseline_ref = entry['rest_baseline_source']
    before_precision = store.get(first_baseline_ref)
    first_row, first_bindings = precision_proof(before_precision, refs['preparation'], baseline)
    learned_saved = {**hunter['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
    b = purchase['baseline']
    require(b['snapshot'] == baseline and b['saved'] == hunter['saved'] and
        b['resources'].get('money') == MONEY and b['entry_source'] == entry_ref and
        b['rest_baseline_source'] == first_baseline_ref and b['native_pet_reload'] == entry['native_pet_reload'] and
        untrained['baseline'] == b and untrained['entry_source'] == entry_ref,
        'immutable untrained purchase baseline differs')
    prerequisite(b['prerequisite_fingerprint'])
    identity = opened.get('trainer_identity')
    require(isinstance(identity, dict) and identity.get('spawn_source') == SPAWN_SOURCE and
        store.get(SPAWN_SOURCE, False) == identity.get('spawn') and
        identity.get('native_session') == entry['native_session'] and
        identity.get('source_interval', [None, None])[0] == entry['started_at'] and
        opened['started_at'] <= identity['source_interval'][1] <= opened['finished_at'] and
        opened['started_at'] <= identity.get('native_catalog', {}).get('packet', {}).get('time', 0),
        'fresh frozen trainer proof is not bound to its owned entry and pinned unique spawn')
    for value in (opened, *([exposed] if exposed is not None else []), selected, purchase):
        require(value.get('trainer_identity') == identity and value.get('entry_source') == entry_ref and
            value.get('native_session') == entry['native_session'], 'immutable trainer identity changed through purchase')
        validate_trainer_identity(identity, value.get('state', {}).get('target', {}),
            value.get('native_catalog'), value['runtime'], entry_ref)
    require(purchase.get('trainer_identity_checked_at') == purchase['purchase_started_at'] and
        identity['source_interval'][1] <= purchase['trainer_identity_checked_at'],
        'current frozen trainer identity was not checked immediately before Train')
    pet_reload(entry['native_pet_reload'], entry)
    require(book_row(untrained['future_probe'], False) == untrained['future_row'] and
        book_row(purchase['learned_probe'], True) == purchase['learned_row'] and
        SPELL not in purchase['login_known_spell_ids'] and
        purchase['login_known_spell_ids'] == untrained['login_known_spell_ids'], 'stock future/learned caption authority differs')
    actual_saved = purchase['after_saved']
    addition = addition_guard(hunter['saved']['actions'], actual_saved['actions'], purchase['purchase_packets'],
        purchase['native_session'], purchase['purchase_started_at'], purchase['purchase_finished_at'],
        b['active_spec'], purchase['public_actionbar_after'])
    require(purchase.get('auto_action_placement') == addition and
        purchase.get('actionbar_restoration_required') is (addition is not None),
        'automatic action placement evidence or restoration requirement differs')
    if addition is None:
        require(actual_saved == learned_saved and not restored.get('action_cleanup_source'), 'purchase changed unrelated saved state')
    else:
        require(actual_saved == {**learned_saved, 'actions': addition['after_actions']} and
            addition['before_actions'] == hunter['saved']['actions'],
            'only exact accepted1462 automatic action placement is allowed')
        bars = store.get(restored['action_cleanup_source'])
        accepted(bars, 'hunter_learn_auto_action_restored')
        require(bars.get('source') == refs['purchase'] and bars.get('purchase_source') == refs['purchase'] and
            bars.get('auto_action_placement') == addition and bars.get('before_saved') == actual_saved and
            bars.get('after_saved') == learned_saved and
            bars.get('before_resources') == bars.get('after_resources') == purchase['after_resources'] and
            bars.get('actor') == actor and bars.get('runtime') == runtime and
            bars.get('native_session') == purchase['native_session'] and bars.get('qualification_added') is False and
            bars.get('restoration_checks') and all(v is True for v in bars['restoration_checks'].values()),
            'automatic Beast Lore action placement lacks complete original bar restoration')
        cleared = clear_guard(addition, bars['after_saved']['actions'], bars['clear_packets'], bars['native_session'],
            bars['clear_started_at'], bars['clear_finished_at'], bars['public_after'])
        early = clear_guard(addition, bars['after_saved']['actions'], bars['clear_packets'], bars['native_session'],
            bars['clear_started_at'], bars['clear_finished_at'], bars['public_after_clear'])
        require(bars.get('clear_proof') == cleared and bars.get('actionbar_restored') is True and
            bars.get('clear_request_proof') == {k: early[k] for k in ('modern', 'native', 'button')} and
            bars.get('stock_pickup_sources') == [PICKUP_SOURCE, BINDING_SOURCE] and
            not bars.get('cursor_before_clear') and not bars.get('cursor_after_cancel') and
            isinstance(bars.get('cursor_before_cancel'), list) and
            bars['cursor_before_cancel'] and bars['cursor_before_cancel'][0] == 'spell' and
            SPELL in bars['cursor_before_cancel'][1:] and
            len(bars.get('restoration_checks', {})) == 12 and
            bars['started_at'] <= bars['clear_started_at'] <= bars['clear_finished_at'] <= bars['finished_at'],
            'complete ordinary action clear/cursor/stock-source proof differs')
        clear_source = bars.get('capture_source') or refs['purchase']
        bar_review = screen_review(store, bars, clear_source, addition['button']['button'], refs['preparation'])
        drag, cancel = bars.get('bar_restore_input', {}), bars.get('cursor_cancel_input', {})
        review_ref = {k: bars['screen_review'][k] for k in ('path', 'sha256')}
        require(drag.get('kind') == 'shift_drag' and drag.get('slot0') == addition['slot0'] and
            drag.get('spell') == SPELL and drag.get('source') == cancel.get('source') == review_ref and
            drag.get('start') == bar_review.get('point') and drag.get('end') == bar_review.get('empty_point') and
            drag.get('start') != drag.get('end') and drag.get('reviewed_frame') == bars['screen_review']['frame'] and
            cancel.get('kind') == 'click' and cancel.get('button') == 3 and cancel.get('value') == drag['end'] and
            bars.get('geometry_proof', {}).get('exact_pixels') is True and
            bars.get('input_sent') is True and bars.get('clear_input_sent') is True,
            'one source-bound reviewed ordinary Shift pickup and cursor cancellation differs')
        require(purchase['finished_at'] < bars['started_at'] < bars['finished_at'] <= restored['started_at'],
            'automatic bar clear is outside its original learn/restoration interval')
    derived = learned_checks(purchase['purchase_packets'], hunter['saved']['spells'], actual_saved['spells'],
        b['resources'], purchase['after_resources'], purchase['native_session'],
        purchase['purchase_started_at'], purchase['purchase_finished_at'])
    require(all(v is True for v in derived.values()) and all(purchase.get('purchase_checks', {}).get(k) is True for k in derived),
        'exact native1462 learn, persistence or cost differs')
    checks(purchase, 'purchase_checks', PURCHASE_NAMES)
    require(purchase['started_at'] <= purchase['purchase_started_at'] <=
        purchase['purchase_finished_at'] <= purchase['finished_at'], 'ordinary purchase interval differs')
    require(purchase.get('purchase_input_sent') is True and purchase.get('input_sent') is True and
        not purchase.get('state', {}).get('lua_errors') and not purchase.get('state', {}).get('blocked_actions') and
        sorted(reconciled_known(purchase['login_known_spell_ids'], purchase['purchase_packets'], purchase['purchase_checks'])) ==
        purchase['reconciled_known_spell_ids'] and purchase['reconciled_known_spell_ids'] ==
        sorted(set(purchase['login_known_spell_ids']) | {SPELL}), 'single ordinary new learned authority differs')
    for value in (opened, selected):
        catalog = value['native_catalog']
        require(catalog.get('guid') == TRAINER_GUID and
            [r for r in catalog.get('rows', []) if r[0] == SPELL] == [[1462, 1, 646, 0, 0, 0, 0, 0, 0, 0]],
            'exact existing available trainer catalog differs')
    require(selected.get('state', {}).get('trainer', {}).get('service', {}).get('name') == 'Beast Lore',
        'selected ordinary Beast Lore service is absent')
    screen_review(store, opened, staged_ref, 'Benjamin Foxworthy', refs['preparation'])
    screen_review(store, selected, trainer_view_ref, 'Beast Lore', refs['preparation'])
    screen_review(store, purchase, selected_ref, 'Train', refs['preparation'])
    require(restored.get('purchase_source') == refs['purchase'] and
        all(restored['book_layout_restored'].get(k) == purchase['book_layout_baseline'].get(k)
            for k in ('book_type', 'skill_line', 'pages', 'page')), 'original stock spellbook layout differs')
    pose = restored['pose_restoration']
    require(pose.get('restored') == pose.get('fixture', {}).get('before') ==
        [hunter['native'][k] for k in POSE_KEYS] and
        pose.get('removed') == [r[0] for r in pose['fixture']['rows']] and
        pose.get('checks') and all(v is True for v in pose['checks'].values()), 'original exact pose or fixture removal differs')
    require(parked.get('source') == refs['restoration'] and parked.get('entry_source') == entry_ref,
        'first parking source differs')
    logout(parked, entry)
    parked_snapshot = parked['all_offline_snapshot']
    after_row, bindings = precision_proof(exact, refs['first_park'], parked_snapshot)
    require(bindings == first_bindings, 'first native rest formula/configuration identity changed')
    first_rest = parked_preservation(baseline, parked_snapshot, entry, first_row, after_row,
        MONEY - PRICE, learned_saved)
    normalized_first = normalized(store, 'first_normalization', refs, baseline, parked, exact, entry)
    checks(cleaned, 'checks', CLEAN_NAMES)
    require(cleaned.get('before') == normalized_first and cleaned.get('after') == cleaned.get('expected_after') ==
        cleanup_expected(baseline, normalized_first) and cleaned.get('input_sent') is False and
        cleaned.get('qualification_added') is False and
        cleaned.get('preparation_source') == refs['preparation'] and cleaned.get('purchase_source') == refs['purchase'] and
        cleaned.get('restoration_source') == refs['restoration'] and cleaned.get('park_source') == refs['first_park'] and
        cleaned.get('precision_source') == refs['first_precision'] and
        cleaned.get('creator_normalization_source') == refs.get('first_normalization') and
        cleaned.get('removed_spell') == SPELL and cleaned.get('refunded_copper') == PRICE,
        'exact offline direct1462 removal/refund differs')
    if cleaned.get('settled_commit_only') is True:
        failed = store.get(cleaned['cleanup_failed_source'], False)
        declared = ('before', 'expected_after', 'preparation_source', 'purchase_source',
            'restoration_source', 'park_source', 'precision_source', 'creator_normalization_source',
            'native_rest_accrual_preserved', 'refunded_copper', 'removed_spell', 'runtime', 'actor')
        require(cleaned.get('mutation_sent') is False and cleaned.get('original_mutation_sent') is True and
            cleaned.get('transaction_committed') is True and cleaned.get('commit_attempted') is False and
            failed.get('completed') is False and isinstance(failed.get('failure'), str) and failed['failure'] and
            failed.get('phase') == 'hunter_learn_offline_cleanup_started' and
            failed.get('mutation_sent') is True and failed.get('commit_attempted') is True and
            cleaned.get('sources') == failed.get('sources', []) + [cleaned['cleanup_failed_source']] and
            all(failed.get(k) == cleaned.get(k) for k in declared) and
            failed['started_at'] < failed['finished_at'] <= cleaned['started_at'],
            'read-only cleanup settlement lacks the exact attempted committed transaction source')
    else:
        require(cleaned.get('mutation_sent') is True, 'ordinary cleanup must record its exact offline mutation')
    if 'first_normalization' in refs:
        require(store.get(refs['first_normalization'])['finished_at'] <= cleaned['started_at'],
            'cleanup precedes its separate creator normalization')
    cleaned_snapshot = cleaned['after']
    untrained_boundary(cleaned_snapshot)
    reentry_entry_ref = reentry['entry_source']
    entered_again = store.get(reentry_entry_ref)
    accepted(entered_again, 'owned_class_entered')
    reentry_preparation_ref = entered_again['fixture_source']
    reentry_preparation = store.get(reentry_preparation_ref)
    accepted(reentry_preparation, 'await_owned_class_lobby_review')
    require(reentry_preparation.get('learning_reentry_only') is True and
        reentry_preparation.get('learn_offline_baseline') == cleaned_snapshot and
        reentry.get('cleaned_source') == refs['cleaned'] and
        reentry.get('baseline', {}).get('snapshot') == cleaned_snapshot and
        reentry['baseline'].get('saved') == cleaned_snapshot['6']['saved'] and
        reentry['baseline'].get('resources', {}).get('money') == MONEY and
        SPELL not in reentry['login_known_spell_ids'] and
        book_row(reentry['future_probe'], False) == reentry['future_row'], 'restored untrained stock reentry differs')
    checks(reentry, 'checks', REENTRY_NAMES)
    prerequisite(reentry['baseline']['prerequisite_fingerprint'])
    original_finish = store.get(reentry_preparation['original_finish_source'])
    whole(original_finish, 'checks', 5)
    require(reentry_preparation.get('previous_preparation_source') == refs['preparation'] and
        reentry_preparation.get('cleaned_source') == refs['cleaned'] and
        original_finish.get('actor') == origin and original_finish.get('runtime') == runtime and
        original_finish.get('fixture_source') == refs['preparation'] and
        cleaned['finished_at'] <= original_finish['started_at'] < original_finish['finished_at'] <= reentry_preparation['started_at'],
        'restored reentry lacks its separately reviewed original parked selection')
    first_selection = screen_review(store, original_finish, None, 'Harnesstwo', refs['preparation'])
    require(first_selection.get('selected_character') == 'Harnesstwo' and first_selection.get('selected_level') == 1,
        'first original selection reviewed identity differs')
    second_baseline_ref = entered_again['rest_baseline_source']
    second_precision = store.get(second_baseline_ref)
    second_row, second_bindings = precision_proof(second_precision, reentry_preparation_ref, cleaned_snapshot)
    pet_reload(entered_again['native_pet_reload'], entered_again)
    require(final.get('source') == refs['reentry'] and final.get('entry_source') == reentry_entry_ref,
        'final parking source differs')
    logout(final, entered_again)
    final_snapshot = final['all_offline_snapshot']
    final_row, final_bindings = precision_proof(final_exact, refs['final_park'], final_snapshot)
    require(second_bindings == final_bindings == bindings, 'native rest formula/configuration identity changed during reentry')
    final_rest = parked_preservation(cleaned_snapshot, final_snapshot, entered_again, second_row, final_row,
        MONEY, cleaned_snapshot['6']['saved'])
    after = normalized(store, 'final_normalization', refs, cleaned_snapshot, final, final_exact, entered_again)
    untrained_boundary(after)
    whole(finish, 'checks', 5)
    require(finish.get('actor') == origin and finish.get('fixture_source') == reentry_preparation_ref and
        finish.get('qualified_scope', '').startswith('Original parked character, saved rows and selected identity restored;'),
        'original Harnesstwo selection restoration is absent')
    selection_review = screen_review(store, finish, None, 'Harnesstwo', reentry_preparation_ref)
    require(selection_review.get('selected_character') == 'Harnesstwo' and
        selection_review.get('selected_level') == 1, 'reviewed original selection identity differs')
    if 'final_normalization' in refs:
        require(store.get(refs['final_normalization'])['finished_at'] <= finish['started_at'],
            'final original selection precedes its offline creator normalization')
    current = [entry, untrained, staged, opened, selected, purchase, restored, parked, reentry_preparation,
        entered_again, reentry, final, finish]
    if exposed is not None:
        current.append(exposed)
    require(all(value.get('native_session') == entry['native_session'] for value in
        (untrained, staged, opened, selected, purchase, restored, parked)) and
        all(value.get('native_session') == entered_again['native_session'] for value in (reentry, final)),
        'purchase/restoration and reentry do not belong to their exact owned native login')
    for value in current:
        require(value.get('runtime') == runtime and value.get('model') is None and value.get('controller') == 'code' and
            value.get('custom_script_permission') == 'blocked_by_user' and
            value.get('softTargetInteract') == {'original': '0', 'current_stock_disabled': '1', 'original_restored': False} and
            value.get('actor') == (origin if value is reentry_preparation or value is finish else actor),
            'same owned runtime, actor, ordinary controller or script boundary differs')
    require(all(value.get('qualification_added', False) is False for value in [*rows.values(), *current]) and
        all(after[str(g)] == baseline[str(g)] for g in range(1, 6)), 'qualification or protected actors changed')
    for value in (before_precision, exact, cleaned, second_precision, final_exact):
        require(value.get('runtime') == runtime, 'read-only/offline source runtime identity differs')
    for snapshot in (parked_snapshot, normalized_first, cleaned_snapshot, final_snapshot, after):
        require(set(snapshot['6']['native']) == set(hunter['native']) and len(snapshot['6']['pets']) == 2,
            'Hunter native row or pet cardinality differs')
    order = [old, before_precision, entry, untrained, staged, opened, selected, purchase, restored, parked,
        exact, cleaned, reentry_preparation, second_precision, entered_again, reentry, final, final_exact, finish]
    if exposed is not None:
        order.insert(order.index(selected), exposed)
    for left, right in zip(order, order[1:]):
        require(left['finished_at'] <= right['started_at'], 'whole learn lifecycle chronology differs')
    stop = store.get(old['primary_stop_source'])
    accepted(stop, 'user_requested_primary_client_stopped')
    whole(stop, 'checks', 8)
    require(stop.get('before') == stop.get('after') == baseline['1'], 'original primary stop/preservation differs')
    return {'operation': 'spellbook.learn_spell', 'owner': 6, 'spell': SPELL, 'trainer': TRAINER,
        'price': PRICE, 'native_purchases': 1, 'native_learn_events': 1, 'modern_learn_events': 1,
        'purchase_checks': len(PURCHASE_NAMES), 'closure_checks': len(CLOSURE_NAMES), 'restored_untrained_reentry': True,
        'cleanup_removed_spell': SPELL, 'cleanup_refund': PRICE, 'named_pet_preserved': 4,
        'living_pet_preserved': 16, 'ordinary_login_count': 2, 'ordinary_logout_count': 2,
        'all_six_offline': True, 'primary_stopped': True, 'qualification_added': False,
        'first_rest': first_rest, 'final_rest': final_rest}, after, current


def closure_checks(value):
    accepted(value, PHASE)
    require(value.get('schema') == SCHEMA and value.get('input_sent') is False and
        value.get('mutation_sent') is False and value.get('qualification_added') is False and
        value.get('actor', {}).get('guid') == 2 and value.get('primary_stop_source') and
        set(value.get('sources', {})) >= set(ROLES) and
        set(value.get('sources', {})) <= set(ROLES + OPTIONAL_ROLES), 'distinct complete learning closure differs')
    checks(value, 'checks', CLOSURE_NAMES)
    untrained_boundary(value['all_offline_snapshot'])
    p = value.get('proof', {})
    expected = {'operation': 'spellbook.learn_spell', 'owner': 6, 'spell': SPELL,
        'native_purchases': 1, 'native_learn_events': 1, 'modern_learn_events': 1,
        'cleanup_removed_spell': SPELL, 'cleanup_refund': PRICE, 'restored_untrained_reentry': True,
        'all_six_offline': True, 'primary_stopped': True, 'qualification_added': False,
        'closure_checks': len(CLOSURE_NAMES)}
    require(all(type(p.get(k)) is type(v) and p[k] == v for k, v in expected.items()), 'complete closure semantic proof differs')
    return value['checks']


def tracking_state():
    return {'packets': [], 'events': [], 'members': set()}


def collect(member, lines, data, tracking):
    """Collect bounded actual journals; never infer packets from receipt claims."""
    closures = [e for e in data.values() if isinstance(e, dict) and e.get('phase') == PHASE]
    require(len(closures) == 1, 'one distinct learning closure must precede tracking')
    source = Sources(data, tracking['digests'])
    closure = closures[0]
    old = source.get(closure['sources']['preparation'])
    since, until = old['started_at'], closure['finished_at']
    tracking['members'].add(member)
    destination = tracking['packets' if member == TRACKING_MEMBERS[0] else 'events']
    require(member in TRACKING_MEMBERS, 'unknown learning tracking stream')
    for row in lines:
        if since <= row.get('time', 0) <= until and (row.get('name') in PACKET_NAMES or
            member == TRACKING_MEMBERS[1] and row.get('event') == 'instance_authenticated'):
            destination.append(row)
            require(len(destination) <= 20000, 'learning tracking journal exceeds its bounded semantic window')


def actual_packets(purchase, entries, tracking, known_receipts=()):
    require(tracking.get('members') == set(TRACKING_MEMBERS), 'both actual archived packet and metadata journals are required')
    wire, events = tracking['packets'], tracking['events']
    session = purchase['native_session']
    require(session == entries[0]['native_session'] and all(type(e.get('native_session')) is str and
        e['native_session'] for e in entries), 'purchase does not belong to its exact owned native login session')
    owned = [p for p in wire if p.get('session') == session]
    direct = {('to_native', 'CMSG_TRAINER_BUY_SPELL'), ('from_native', 'SMSG_LEARNED_SPELL'),
        ('to_client', 'SMSG_LEARNED_SPELLS')}
    learns = [p for p in owned if (p.get('direction'), p.get('name')) in direct]
    recorded = [p for p in purchase['purchase_packets'] if (p.get('direction'), p.get('name')) in direct]
    require(len(learns) == len(recorded) == 3 and {packet_key(p) for p in learns} == {packet_key(p) for p in recorded},
        'actual archived single1462 purchase and learn delivery differ from receipts')
    require(not any(p.get('name') in ('CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS') and
        p.get('session') == entries[1]['native_session'] and p.get('time', 0) >= entries[1]['started_at'] for p in wire),
        'restored reentry contains another learn/purchase')
    require(not any(p.get('session') in {e['native_session'] for e in entries} and
        p.get('name') == 'SMSG_TRAINER_BUY_FAILED' for p in wire), 'actual archive contains a native purchase failure')
    successes = [p for p in owned if p.get('direction') == 'from_native' and p.get('name') == 'SMSG_TRAINER_BUY_SUCCEEDED']
    require(len(successes) <= 1 and all(p.get('body') == struct.pack('<QI', TRAINER_GUID, SPELL).hex()
        for p in successes), 'actual native trainer completion differs')
    require(not any(p.get('session') in {e['native_session'] for e in entries} and
        p.get('direction') == 'to_native' and p.get('name') in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in wire),
        'cast-free learning lifecycle contains a native cast')
    modern = [p for p in owned if p.get('direction') == 'from_client' and p.get('name') == 'CMSG_TRAINER_BUY_SPELL']
    require(len(modern) == 1 and any(packet_key(p) == packet_key(modern[0]) for p in purchase['purchase_packets']),
        'one exact actual ordinary modern Train request is required')
    reader = Reader(bytes.fromhex(modern[0]['body']))
    guid = reader.guid()
    trainer, spell = reader.unpack('ii')
    reader.end()
    expected_guid = (TRAINER_GUID & 0xffffffff,
        (8 << 58) | (1 << 42) | (((TRAINER_GUID >> 32) & 0xfffff) << 6))
    require(guid == expected_guid and trainer == TRAINER and spell == SPELL and
        modern[0]['time'] <= learns[0]['time'] and learns[0]['time'] - modern[0]['time'] < 2,
        'actual modern Beast Lore trainer identity/body/order differs')
    identity = purchase.get('trainer_identity')
    require(isinstance(identity, dict) and purchase.get('entry_source') == identity.get('entry_source') and
        identity.get('source_interval', [None, None])[0] == entries[0]['started_at'] and
        purchase.get('trainer_identity_checked_at') == purchase.get('purchase_started_at') and
        purchase['trainer_identity_checked_at'] <= learns[0]['time'],
        'actual purchase lacks the source-bound current frozen trainer proof')
    validate_trainer_identity(identity, identity['target'], purchase.get('native_catalog'),
        purchase.get('runtime'), purchase['entry_source'], wire=wire, observed_until=learns[0]['time'])
    instances = []
    for number, entry in enumerate(entries):
        session = entry['native_session']
        found = {e.get('session') for e in events if e.get('event') == 'instance_authenticated' and
            e.get('account_id') == 2 and entry['started_at'] <= e.get('time', 0) <= entry['finished_at']}
        require(len(found) == 1, 'one fresh actual owned physical instance is required per login')
        physical = next(iter(found))
        require(type(physical) is str and physical, 'actual owned physical instance identity is invalid')
        instances.append(physical)
        for claimed in [*entry['login_packets'], *pet_reload(entry['native_pet_reload'], entry, wire)]:
            require(any(packet_key(p) == packet_key(claimed) for p in wire), 'ordinary login or pet reload absent from actual archive')
        known = [p for p in wire if p.get('session') == session and p.get('direction') == 'from_native' and
            p.get('name') == 'SMSG_SEND_KNOWN_SPELLS' and entry['started_at'] <= p.get('time', 0) <= entry['finished_at']]
        require(len(known) == 1 and login_ids(known[0])[0] == 1 and SPELL not in login_ids(known[0])[1],
            'actual untrained native-known login differs')
        if known_receipts:
            receipt = known_receipts[number]
            initial, ids = login_ids(known[0])
            observation = receipt.get('native_known_spell_packet', {})
            require(sorted(ids) == receipt['login_known_spell_ids'] and observation.get('ids') == ids and
                observation.get('body_sha256') == hashlib.sha256(bytes.fromhex(known[0]['body'])).hexdigest() and
                observation.get('session') == session and observation.get('time') == known[0]['time'] and
                observation.get('initial_login') == initial, 'receipt login authority differs from exact actual native-known packet')
    require(len(set(instances)) == 2, 'restored reentry did not establish a fresh physical instance')
    for packet in [modern[0], *learns, *identity['wire_packets']]:
        event_session = packet['session'] if packet['direction'] in ('from_native', 'to_native') else instances[0]
        metadata = [e for e in events if e.get('session') == event_session and e.get('name') == packet['name'] and
            e.get('direction') == packet['direction'] and e.get('bytes') == len(bytes.fromhex(packet['body'])) and
            0 <= packet['time'] - e.get('time', 0) < .1]
        require(len(metadata) == 1 and metadata[0].get('event') ==
            ('native_packet' if packet['direction'] in ('from_native', 'to_native') else 'modern_packet'),
            'actual purchase/learn metadata attribution differs')
    return learns


def proof(data, digests, tracking):
    store = Sources(data, digests)
    require(len(store.ancestry) == 1, 'one complete carried ancestry manifest is required')
    mapped = store.ancestry[0].get('sources', [])
    require(isinstance(mapped, list) and mapped and
        len({r.get('original_path') for r in mapped}) == len(mapped), 'complete carried ancestry mapping differs')
    for row in mapped:
        require(set(row) == {'original_path', 'sha256', 'copy_path', 'bytes'}, 'ancestry member schema differs')
        original, copy = Path(row['original_path']), Path(row['copy_path'])
        require(original.is_absolute() and original.is_relative_to(lab.ROOT / 'evidence') and
            copy.is_absolute() and copy.is_relative_to(lab.ROOT / 'evidence') and
            copy.name == row['sha256'] + '.json' and type(row['bytes']) is int and row['bytes'] > 0,
            'private carried ancestry path or complete size differs')
        member = str(copy.relative_to(lab.ROOT))
        require(digests.get(member) == row['sha256'] and
            tracking.get('manifest', {}).get(member, {}).get('bytes') == row['bytes'],
            'carried ancestry JSON differs from actual complete remote manifest bytes/SHA256')
    closures = [e for e in data.values() if isinstance(e, dict) and e.get('phase') == PHASE]
    pauses = [e for e in data.values() if isinstance(e, dict) and e.get('phase') == 'hunter_learn_scout_resource_paused']
    require(len(closures) == len(pauses) == 1, 'one distinct learning closure and shutdown are required')
    closure, pause = closures[0], pauses[0]
    closure_checks(closure)
    result, snapshot, current = lifecycle(store, closure['sources'])
    require(closure['proof'] == result and closure['all_offline_snapshot'] == snapshot and
        closure['runtime'] == current[0]['runtime'], 'closure proof differs from archived lifecycle')
    accepted(pause, 'hunter_learn_scout_resource_paused')
    checks(pause, 'checks', PAUSE_NAMES)
    require(store.get(pause['source']) == closure and pause.get('runtime') == closure['runtime'] and
        pause.get('actor') == closure['actor'] and pause.get('primary_stop_source') == closure['primary_stop_source'] and
        pause.get('before') == pause.get('after') == snapshot and
        pause.get('input_sent') is False and pause.get('qualification_added') is False and
        pause.get('action') == 'stop_parked_scout_after_learning_restoration' and
        pause.get('controller') == 'code' and pause.get('model') is None and
        pause.get('custom_script_permission') == 'blocked_by_user' and
        pause.get('game_before', {}).get('pid', 0) > 0 and pause.get('game_before', {}).get('start_ticks', 0) > 0 and
        closure['finished_at'] < pause['started_at'], 'complete immutable scout shutdown differs')
    purchase = store.get(closure['sources']['purchase'])
    reentry = store.get(closure['sources']['reentry'])
    entries = [store.get(purchase['entry_source']), store.get(reentry['entry_source'])]
    require(entries[0]['finished_at'] < entries[1]['started_at'],
        'ordinary restored reentry must have a separate later native login interval')
    actual_packets(purchase, entries, tracking, (current[1], reentry))
    placement = purchase.get('auto_action_placement')
    expected_actions = []
    if placement is not None:
        restored = store.get(closure['sources']['restoration'])
        bars = store.get(restored['action_cleanup_source'])
        expected_actions = [placement['modern'], placement['native'], *bars['clear_packets']]
    actual_actions = [p for p in tracking['packets'] if p.get('session') in {e['native_session'] for e in entries} and
        p.get('name') == 'CMSG_SET_ACTION_BUTTON']
    require(len(actual_actions) == len(expected_actions) and
        {packet_key(p) for p in actual_actions} == {packet_key(p) for p in expected_actions},
        'actual complete action journal differs from the sole allowed placement and ordinary clear')
    for role in ('first_park', 'final_park'):
        park = store.get(closure['sources'][role])
        entry = entries[0 if role == 'first_park' else 1]
        for packet in logout(park, entry):
            require(any(packet_key(p) == packet_key(packet) for p in tracking['packets']),
                'ordinary logout absent from actual archived packets')
    result.update(shutdown_checks=8, both_owned_clients_stopped=True, actual_packet_journals_verified=True)
    return result


def close(source_paths, output):
    """Write a local semantic closure; actual remote proof remains a later step."""
    output = Path(output).resolve()
    require(output.name == 'episode.json' and output.is_relative_to(lab.ROOT / 'evidence') and not output.exists(),
        'requires a new private learning closure episode')
    refs = {name: bound(Path(path)) for name, path in source_paths.items()}
    data = {str(Path(ref['path']).relative_to(lab.ROOT)): closed(Path(ref['path'])) for ref in refs.values()}
    digests = {str(Path(ref['path']).relative_to(lab.ROOT)): ref['sha256'] for ref in refs.values()}
    store = Sources(data, digests, local=True)
    started = time.time()
    result, snapshot, current = lifecycle(store, refs)
    old = store.get(refs['preparation'])
    value = {'schema': SCHEMA, 'phase': PHASE, 'started_at': started, 'finished_at': time.time(),
        'completed': True, 'failure': None, 'runtime': old['runtime'], 'actor': old['origin_actor'],
        'sources': refs, 'primary_stop_source': old['primary_stop_source'], 'all_offline_snapshot': snapshot,
        'proof': result, 'checks': {k: True for k in sorted(CLOSURE_NAMES)}, 'input_sent': False,
        'mutation_sent': False, 'qualification_added': False, 'controller': 'code', 'model': None}
    closure_checks(value)
    lab.private_write(output, json.dumps(value, indent=2) + '\n')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['close'])
    parser.add_argument('--output', type=Path, required=True)
    for name in ROLES + OPTIONAL_ROLES:
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=name in ROLES)
    args = parser.parse_args()
    result = close({name: getattr(args, name) for name in ROLES + OPTIONAL_ROLES if getattr(args, name)}, args.output)
    print(json.dumps({'completed': result['completed'], 'phase': result['phase'],
        'closure_checks': len(result['checks']), 'qualification_added': False}), flush=True)


if __name__ == '__main__':
    main()
