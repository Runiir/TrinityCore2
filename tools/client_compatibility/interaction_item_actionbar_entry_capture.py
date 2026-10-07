"""Capture a fresh screen after excluded pre-drag cleanup and observer repair.

The original entry remains immutable. This command observes only; it neither
reloads the interface nor opens a bag or consumes a gameplay attempt.
"""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import subprocess
import time

from . import interaction_item_actionbar as op
from .item_actionbar_contract import (ACTION, GRID_SOURCE, require, finite, strict_equal,
    public_assignments, native_replay, forbidden_packets, login_packets)
from .item_actionbar_preservation import online_preservation
from .item_actionbar_sources import reference

PHASE = 'item_actionbar_entry_screen_captured'
RELOAD_PHASE = 'item_actionbar_passive_observer_loaded'
LAYOUT_CHECKS = frozenset(('public_bar', 'bags', 'panels', 'target', 'pose', 'afk',
    'position', 'cursor_empty', 'ui_clean'))
PROTECTED_CHECKS = frozenset(('protected_1', 'protected_3', 'protected_4', 'protected_5',
    'protected_6', 'owner_inventory', 'owner_pets', 'owner_position'))
ATTEMPT_FIELDS = ('drag_attempt_source', 'clear_attempt_source', 'drag_intent', 'clear_intent',
    'drag_started_at', 'clear_started_at', 'placement', 'clear_request_proof')
MODULES = ('interaction_item_actionbar_entry_capture.py', 'interaction_item_actionbar.py',
    'item_actionbar_evidence.py', 'interaction_item_actionbar_pre_recon_recovery.py',
    'interaction_item_actionbar_observer_reload.py', 'interaction_retained_class_reentry.py')
ISOLATED_OPERATION_SHA = '8ed9dcd456195f687e61243bb0c6169b6702c956378592b5d970fb6d662a2970'
RENEWAL_MODULE = 'interaction_item_actionbar_idle_renewal.py'
RESTORATION_CHECKS = LAYOUT_CHECKS | {'full_saved_baseline', 'full_resources_baseline', 'protected_actors', 'zero_native_mutation'}


def complete(value, *, failed=False):
    require(type(value) is dict and finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'], 'one honest closed source interval is required')
    require((value.get('completed') is False and type(value.get('failure')) is str and bool(value['failure']))
        if failed else (value.get('completed') is True and value.get('failure') is None),
        'closed successful or immutable failed source status differs')
    return value


def typed_checks(value, key, expected):
    found = value.get(key)
    require(type(found) is dict and set(found) == set(expected) and all(v is True for v in found.values()),
        'complete exact typed ' + key + ' checks are required')


def unconsumed(entry_ref):
    reference(entry_ref)
    path = Path(entry_ref['path'])
    require(op.bound(path) == entry_ref, 'immutable original entry changed')
    for kind in ('drag', 'clear'):
        marker = path.parent / ('item_actionbar_' + kind + '_attempt.json')
        require(not marker.exists() and not marker.is_symlink(),
            'fresh entry screen refuses every consumed drag or clear attempt')


def clean_state(state, entry, version=None):
    require(type(state) is dict and all(type(state.get(k)) is type(v) and state[k] == v for k, v in
        {'player': 'Harnesstwo', 'level': 1, 'xp': 0, 'xp_max': 400}.items()) and
        state.get('guid') == entry['state']['guid'] and
        type(state.get('xp_exhaustion')) is int and
        state['xp_exhaustion'] == 2 * entry['native_owner_proof']['rest_threshold'] and
        strict_equal(state.get('world_position'), entry['state'].get('world_position')) and
        strict_equal(state.get('target'), entry['state'].get('target')) and
        not any(state.get(k) for k in ('bags', 'panels', 'cursor_info', 'item_cursor', 'spell_targeting',
            'chat_edit_open', 'lua_errors', 'blocked_actions')) and
        (version is None or type(state.get('observer_version')) is int and state['observer_version'] == version),
        'fresh original level1 screen, rest, pose, target or observer version differs')


def code_sources(value):
    rows = value.get('committed_sources')
    require(type(rows) is list and 3 <= len(rows) <= 100 and
        len({r.get('path') for r in rows if type(r) is dict}) == len(rows),
        'bounded unique committed repair source identities are required')
    for row in rows:
        reference(row)
        require(Path(row['path']).is_relative_to(op.lab.REPO), 'repair code source is outside the current checkout')
    required = {str(op.lab.REPO / 'tools/client_compatibility' / name) for name in MODULES}
    require(required <= {r['path'] for r in rows}, 'capture, operation and proof source identities are required')
    return deepcopy(rows)


def restoration(recovery, base, refs):
    complete(recovery)
    require(recovery.get('phase') == 'item_actionbar_restored' and recovery.get('pre_recon_recovery') is True and
        recovery.get('source') == recovery.get('first_failure_source') == refs['failed'] and
        recovery.get('preparation_source') == recovery.get('fixture_source') == refs['preparation'] and
        recovery.get('entry_source') == refs['entry'] and strict_equal(recovery.get('baseline'), base) and
        recovery.get('recovery_only') is True and recovery.get('failed_whole_excluded') is True and
        recovery.get('gameplay_input_replayed') is False and recovery.get('drag_input_sent') is False and
        recovery.get('clear_input_sent') is False and recovery.get('actionbar_restored') is True and
        recovery.get('placement_absent') is True and strict_equal(recovery.get('after_saved'), base['saved']) and
        strict_equal(recovery.get('after_resources'), base['resources']) and
        strict_equal(recovery.get('after_native_state'), base['native_state']) and recovery.get('cases') == [],
        'exact successful excluded pre-recon recovery is required')
    typed_checks(recovery, 'layout_restoration_checks', LAYOUT_CHECKS)
    typed_checks(recovery, 'restoration_checks', RESTORATION_CHECKS)
    typed_checks(recovery, 'protected_checks', PROTECTED_CHECKS)


def repair_ancestors(recovery, refs, resolver=None):
    if recovery.get('idle_renewal') is not True:
        require(not any(k in recovery for k in ('prior_restoration_source', 'failed_observer_source')),
            'ordinary first cleanup cannot invent an idle-renewal ancestry')
        return {}
    def linked(ref, successful):
        require(op.bound(Path(ref['path'])) == ref, 'immutable repair ancestor bytes changed')
        return op.closed(Path(ref['path']), successful=successful)
    resolver = resolver or linked
    result = {}
    for name, successful in (('prior_restoration', True), ('failed_observer', False)):
        source = recovery.get(name + '_source')
        reference(source)
        refs[name] = source
        result[name] = resolver(source, successful)
    return result


def validate_repair(ready, entry, failed, recovery, reload, refs, ancestors=None):
    """Pure source-bound repair authority; excluded failures remain excluded."""
    ancestors = {} if ancestors is None else ancestors
    renewed = recovery.get('idle_renewal') is True
    extra = {'prior_restoration', 'failed_observer'} if renewed else set()
    require(type(refs) is dict and set(refs) == {'preparation', 'entry', 'failed', 'recovery', 'reload'} | extra and
        type(ancestors) is dict and set(ancestors) == extra,
        'complete original-entry repair source roles are required')
    for ref in refs.values():
        reference(ref)
    complete(ready); complete(entry); complete(failed, failed=True); complete(recovery); complete(reload)
    require(ready.get('phase') == 'item_actionbar_scout_ready' and entry.get('phase') == 'item_actionbar_entered' and
        entry.get('preparation_source') == refs['preparation'] and
        entry.get('all_offline_snapshot') == ready.get('all_offline_snapshot'), 'original entry preparation differs')
    actor, runtime, session = entry['actor'], entry['runtime'], entry['native_session']
    old_commit, new_commit = entry.get('code_commit'), reload.get('code_commit')
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{40}', v) for v in (old_commit, new_commit)) and
        ready.get('code_commit') == old_commit and failed.get('code_commit') == old_commit,
        'original entry and first failure code identity must remain unchanged')
    for value in (ready, failed, recovery, reload, *ancestors.values()):
        require(value.get('actor') == actor and value.get('runtime') == runtime and
            value.get('native_session') == session and value.get('qualification_added') is False and
            value.get('mutation_sent') is False and value.get('model') is None and value.get('revision') is None,
            'one unchanged owned runtime, session and excluded setup identity is required')
        require(value.get('controller') in ('code', 'code_diagnostic_ordinary_inputs'),
            'repair inputs require the exact code controller identity')
    base = failed.get('baseline', {})
    op.baseline_authority(base, entry, ready)
    require(base.get('entry_source') == refs['entry'] and failed.get('entry_source') == refs['entry'] and
        failed.get('preparation_source') == failed.get('fixture_source') == refs['preparation'] and
        failed.get('phase') is None and failed.get('input_sent') is True and failed.get('cases') == [] and
        failed.get('cleanup') == [] and failed.get('failure') == 'RuntimeError: actionbars diagnostic did not become visible' and
        all(k not in failed for k in ATTEMPT_FIELDS) and
        all(failed.get(k, False) is False for k in ('drag_input_sent', 'clear_input_sent')),
        'only the immutable pre-drag open-backpack timeout may precede fresh capture')
    raw = failed.get('raw_stage_failure', {})
    require(strict_equal(raw.get('saved'), base['saved']) and strict_equal(raw.get('resources'), base['resources']) and
        strict_equal(raw.get('native_state'), base['native_state']) and raw.get('input_replayed') is False and
        raw.get('state', {}).get('bags') == [0] and not any(raw.get('state', {}).get(k) for k in
            ('panels', 'cursor_info', 'spell_targeting', 'chat_edit_open', 'lua_errors', 'blocked_actions')),
        'first failed receipt must retain its unchanged inventory, native state and open backpack')
    restoration(recovery, base, refs)
    if renewed:
        prior, observer = ancestors['prior_restoration'], ancestors['failed_observer']
        restoration(prior, base, refs)
        complete(observer, failed=True)
        require(prior.get('idle_renewal') is not True and recovery.get('prior_restoration_source') == refs['prior_restoration'] and
            recovery.get('failed_observer_source') == refs['failed_observer'] and
            recovery.get('prior_input_sources') == {kind + '_attempt_source': prior.get(kind + '_attempt_source') for kind in ('escape', 'stand', 'afk')} and
            observer.get('source') == observer.get('restoration_source') == refs['prior_restoration'] and
            observer.get('first_failure_source') == refs['failed'] and observer.get('entry_source') == refs['entry'] and
            observer.get('preparation_source') == observer.get('fixture_source') == refs['preparation'] and
            observer.get('phase') == 'item_actionbar_passive_observer_prepared' and
            observer.get('failure') == 'RuntimeError: native baseline changed before ordinary reload' and
            observer.get('input_sent') is False and observer.get('ordinary_inputs') == [] and
            'reload_attempt_source' not in observer and all(k not in observer for k in ATTEMPT_FIELDS) and
            observer.get('recovery_only') is True and observer.get('failed_whole_excluded') is True and
            observer.get('gameplay_input_replayed') is False and observer.get('drag_input_sent') is False and
            observer.get('clear_input_sent') is False and observer.get('cases') == [] and
            strict_equal(observer.get('baseline'), base) and observer.get('before_saved') == base['saved'] and
            observer.get('before_resources') == base['resources'] and observer.get('before_native_state') == base['native_state'] and
            op.public_same(observer.get('before_public', {}), entry['public']),
            'idle renewal requires the exact unchanged A restoration and failed B observer before any input')
        b_sources = deployment_sources(observer)
        b_transition = {'previous_code_commit': old_commit, 'restoration_code_commit': prior['code_commit'],
            'code_commit': observer['code_commit'], 'entry_source': refs['entry'], 'first_failure_source': refs['failed'],
            'restoration_source': refs['prior_restoration'], 'committed_sources': b_sources}
        require(observer.get('previous_code_commit') == old_commit and
            observer.get('restoration_code_commit') == prior['code_commit'] and
            observer.get('repair_code_transition') == b_transition and
            prior['finished_at'] <= observer['started_at'] < observer['finished_at'] <= recovery['started_at'],
            'truthful completed A, failed B and fresh C renewal code/times differ')
    require(reload.get('phase') == RELOAD_PHASE and reload.get('source') == reload.get('restoration_source') == refs['recovery'] and
        reload.get('first_failure_source') == refs['failed'] and reload.get('entry_source') == refs['entry'] and
        reload.get('preparation_source') == reload.get('fixture_source') == refs['preparation'] and
        strict_equal(reload.get('baseline'), base) and reload.get('recovery_only') is True and
        reload.get('failed_whole_excluded') is True and reload.get('gameplay_input_replayed') is False and
        reload.get('drag_input_sent') is False and reload.get('clear_input_sent') is False and
        reload.get('cases') == [] and strict_equal(reload.get('after_saved'), base['saved']) and
        strict_equal(reload.get('after_resources'), base['resources']) and
        strict_equal(reload.get('after_native_state'), base['native_state']) and
        op.public_same(reload.get('after_public', {}), entry['public']),
        'source-bound successful excluded observer repair differs')
    typed_checks(reload, 'layout_restoration_checks', LAYOUT_CHECKS)
    typed_checks(reload, 'protected_checks', PROTECTED_CHECKS)
    clean_state(reload.get('after_state'), entry, 146)
    sources = deployment_sources(reload)
    if renewed:
        require(str(op.lab.REPO / 'tools/client_compatibility' / RENEWAL_MODULE) in {r['path'] for r in sources},
            'committed idle-renewal guard identity is required')
    restoration_commit = recovery.get('code_commit')
    require(type(restoration_commit) is str and re.fullmatch('[0-9a-f]{40}', restoration_commit) and
        reload.get('restoration_code_commit') == restoration_commit, 'truthful excluded restoration code identity differs')
    expected_transition = {'previous_code_commit': old_commit, 'restoration_code_commit': restoration_commit, 'code_commit': new_commit,
        'entry_source': refs['entry'], 'first_failure_source': refs['failed'],
        'restoration_source': refs['recovery'], 'committed_sources': sources}
    require(reload.get('previous_code_commit') == old_commit and
        strict_equal(reload.get('repair_code_transition'), expected_transition), 'explicit immutable repair code transition differs')
    sequence = (ready, entry, failed, recovery, reload)
    require(all(a['finished_at'] <= b['started_at'] for a, b in zip(sequence, sequence[1:])),
        'original entry, failure, excluded recovery and observer repair chronology differs')
    return deepcopy(expected_transition)


def deployment_sources(reload):
    new_commit = reload.get('code_commit')
    require(type(new_commit) is str and re.fullmatch('[0-9a-f]{40}', new_commit), 'truthful observer deployment commit is required')
    deployment = reload.get('observer_deployment', {})
    files = deployment.get('source')
    require(type(files) is dict and files and deployment.get('installed') == files and
        deployment.get('version') == 146 and type(deployment.get('version')) is int and
        deployment.get('code_commit') == new_commit and
        deployment.get('load_on') == 'ordinary /reload' and
        all(type(n) is str and Path(n).name == n and type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha)
            for n, sha in files.items()) and 'ClientInteractions.lua' in files,
        'actual complete source and installed observer146 identities are required')
    reference(deployment.get('installer_source'))
    sources = code_sources(reload)
    require(deployment.get('committed_sources') == sources,
        'actual deployment source list differs from the explicit committed repair identity')
    installer = str(op.lab.REPO / 'tools/client_compatibility/interaction_retained_class_reentry.py')
    require(deployment['installer_source'] in sources and deployment['installer_source']['path'] == installer,
        'actual installer code source differs from its committed repair identity')
    raw_install = reload.get('parked_observer_installation', {})
    require(type(raw_install) is dict and set(raw_install) == {'version', 'before', 'after', 'source', 'input_sent', 'load_on'} and
        type(raw_install.get('version')) is int and raw_install['version'] == 146 and
        raw_install.get('input_sent') is False and raw_install.get('source') == raw_install.get('after') == files and
        raw_install.get('load_on') == 'next ordinary owned class entry' and type(raw_install.get('before')) is dict,
        'unaltered raw installer receipt and complete installed addon map are required')
    addon = op.lab.REPO / 'tools/client_compatibility/observation/addon/ClientMovementHarness'
    committed_addon = {Path(r['path']).name: r['sha256'] for r in sources if Path(r['path']).parent == addon}
    require(committed_addon == files, 'installed observer map must bind every committed addon file')
    observer = str(op.lab.REPO / 'tools/client_compatibility/observation/addon/ClientMovementHarness/ClientInteractions.lua')
    require(any(r == {'path': observer, 'sha256': files['ClientInteractions.lua']} for r in sources),
        'installed scheduler digest differs from the committed observer source')
    return sources


def validate_code_bytes(value, sources):
    rows = value.get('code_source_bytes')
    require(type(rows) is list and len(rows) == len(sources) and
        len({r.get('path') for r in rows if type(r) is dict}) == len(rows),
        'actual bounded committed repair source bytes are required')
    raw_size = 0
    for row, source in zip(rows, sources):
        require(type(row) is dict and set(row) == {'path', 'sha256', 'raw_hex'} and
            {k: row[k] for k in ('path', 'sha256')} == source and type(row['raw_hex']) is str and
            0 < len(row['raw_hex']) <= 800_000 and len(row['raw_hex']) % 2 == 0 and
            re.fullmatch('[0-9a-f]+', row['raw_hex']), 'exact raw source identity or size differs')
        raw = bytes.fromhex(row['raw_hex'])
        raw_size += len(raw)
        require(raw_size <= 2_000_000 and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'portable actual repair source bytes differ from their frozen SHA256')
    return rows


def cleanup_attempts(retained, failed, recovery, refs, entry, ancestors=None, complete_rows=None):
    by_ref = lambda ref: next((r['value'] for r in retained if r['source'] == ref), None)
    expected = []
    renewed = recovery.get('idle_renewal') is True
    for kind in (('stand', 'afk') if renewed else ('escape', 'stand', 'afk')):
        ref = recovery.get(kind + '_attempt_source')
        require((ref is not None) == (recovery.get('bag_close_input_sent') is True if kind == 'escape'
            else recovery.get(kind + '_cleanup_started_at') is not None), 'cleanup attempt source and actual input flag differ')
        if ref is None:
            continue
        reference(ref); expected.append(ref)
        marker = by_ref(ref)
        intent = recovery['bag_close_input'] if kind == 'escape' else marker.get('input_intent') if type(marker) is dict else None
        marker_path = (Path(refs['failed_observer']['path']).parent /
            ('item_actionbar_idle_renewal_' + refs['failed_observer']['sha256'] + '_' + kind + '_attempt.json') if renewed else
            Path(refs['entry']['path']).parent / ('item_actionbar_pre_recon_' + kind + '_attempt.json'))
        schema = 'client442_item_actionbar_idle_renewal_consumed_input_v1' if renewed else 'client442_item_actionbar_pre_recon_consumed_input_v1'
        require(Path(ref['path']) == marker_path and
            type(marker) is dict and marker.get('schema') == schema and
            marker.get('kind') == kind and marker.get('entry_source') == refs['entry'] and
            marker.get('preparation_source') == refs['preparation'] and marker.get('first_failure_source') == refs['failed'] and
            marker.get('actor') == recovery['actor'] and marker.get('runtime') == recovery['runtime'] and
            marker.get('native_session') == recovery['native_session'] and marker.get('operation_output') == refs['recovery']['path'] and
            marker.get('input_replay_allowed') is False and finite(marker.get('created_at')) and
            recovery['started_at'] <= marker['created_at'] <= recovery['finished_at'],
            'exact source-bound exclusive pre-recon cleanup attempt differs')
        if renewed:
            require(marker.get('prior_restoration_source') == refs['prior_restoration'] and
                marker.get('failed_observer_source') == refs['failed_observer'] and
                marker.get('code_commit') == recovery['code_commit'], 'fresh renewal attempt must retain actual A, failed B and current C authority')
        if kind == 'escape':
            require(intent == marker.get('input_intent') == {'kind': 'key', 'value': 'Escape'}, 'only the original bag-close Escape is permitted')
        else:
            require(marker['created_at'] <= recovery[kind + '_cleanup_started_at'] <= recovery['finished_at'],
                'ordinary pose/AFK cleanup must follow its durable attempt')
            if kind == 'afk':
                require(intent == {'kind': 'chat', 'value': '/afk'}, 'only exact observed AFK cleanup is permitted')
            else:
                keys = entry.get('public', {}).get('keys', {}).get('SITORSTAND')
                require(type(intent) is dict and set(intent) == {'kind', 'value', 'hold'} and intent['kind'] == 'key' and
                    type(keys) is list and bool(keys) and type(keys[0]) is str and
                    re.fullmatch('[A-Za-z]', keys[0]) and intent['value'] == keys[0].lower() and intent['hold'] == .4,
                    'only the immutable original entry standing binding is permitted')
    idle = recovery.get('pre_recon_idle_observation', {})
    require(idle.get('original') == recovery['baseline']['native_state'] and idle.get('qualification_added') is False and
        type(idle.get('mismatch_observed')) is bool, 'honest source-retained pre-recon idle observation is required')
    if idle['mismatch_observed'] and not renewed:
        from .interaction_item_actionbar_pre_recon_recovery import stand_chain
        from .item_actionbar_contract import records, body, INDEX
        original = recovery['baseline']['native_state']
        require(original['pose']['stand'] == 0 and original['afk'] is False and
            idle.get('native_before_observation') == {**original, 'pose': {**original['pose'], 'stand': 1}, 'afk': True} and
            idle.get('label') == 'unattributed_observed_post_failure_idle_state_mismatch' and
            idle.get('since') == failed['finished_at'] and finite(idle.get('until')) and
            idle['since'] <= idle['until'] <= recovery['finished_at'],
            'only the exact unattributed observed seated/AFK mismatch is permitted')
        quartet = stand_chain(idle.get('observed_stand_packets', []), 1)
        packet = idle.get('observed_owner_flags_packet', {})
        require(packet.get('name') == 'SMSG_UPDATE_OBJECT' and packet.get('direction') == 'from_native' and
            packet.get('session') == recovery['native_session'] and finite(packet.get('time')) and
            quartet[2]['time'] <= packet['time'] < quartet[2]['time'] + 2 and
            all(p.get('session') == recovery['native_session'] and idle['since'] <= p.get('time', 0) <= idle['until']
                for p in [*quartet, packet]) and any(r.get('guid') == 2 and
                r.get('fields', {}).get(INDEX['UNIT_FIELD_BYTES_1']) == 1 and
                r.get('fields', {}).get(INDEX['PLAYER_FLAGS']) == 2 for r in records(body(packet))),
            'actual owner seated/AFK update and observed sit quartet differ')
        if recovery.get('stand_attempt_source'):
            restored = stand_chain(recovery.get('stand_cleanup_packets', []), 0)
            require(all(p.get('session') == recovery['native_session'] and
                recovery['stand_cleanup_started_at'] <= p['time'] <= recovery['finished_at'] for p in restored),
                'ordinary standing restoration quartet differs')
    elif not renewed:
        require(idle.get('native_before_observation') == idle['original'] and
            recovery.get('stand_attempt_source') is None and recovery.get('afk_attempt_source') is None,
            'exact original idle state permits no pose or AFK cleanup attempt')
    if renewed:
        from .interaction_item_actionbar_idle_renewal import idle_packets
        from .interaction_item_actionbar_pre_recon_recovery import stand_chain
        prior, observer = ancestors['prior_restoration'], ancestors['failed_observer']
        original = recovery['baseline']['native_state']
        movement = idle.get('frame', {}).get('movement', {})
        require(idle.get('mismatch_observed') is True and original['pose']['stand'] == 0 and original['afk'] is False and
            idle.get('native_before_observation') == {**original, 'pose': {**original['pose'], 'stand': 1}, 'afk': True} and
            idle.get('label') == 'unattributed_observed_post_restoration_idle_state_mismatch' and
            idle.get('prior_restoration_source') == refs['prior_restoration'] and idle.get('failed_observer_source') == refs['failed_observer'] and
            idle.get('since') == prior['finished_at'] and finite(idle.get('until')) and
            observer['finished_at'] <= idle['until'] <= recovery['finished_at'] and
            movement.get('speed') == 0 and all(movement.get(k) is False for k in ('dead', 'in_combat', 'on_taxi')),
            'only the fresh source-bound post-A seated AFK mismatch is permitted')
        proof = idle_packets(complete_rows, recovery['native_session'], idle['since'], idle['until'], observer['finished_at'])
        require(all(idle.get(k) == proof[k] for k in proof) and
            idle.get('native_lifecycle_events') == [] and type(idle.get('native_metadata_rows_checked')) is int and
            idle['native_metadata_rows_checked'] >= 4, 'fresh renewal sparse native replay or realm lifetime differs')
        require(recovery.get('stand_attempt_source') is not None and
            'escape_attempt_source' not in recovery and recovery.get('bag_close_input_sent', False) is False,
            'fresh idle renewal permits only distinct ordinary stand and AFK cleanup')
        restored = stand_chain(recovery.get('stand_cleanup_packets', []), 0)
        require(all(row.get('session') == recovery['native_session'] and
            recovery['stand_cleanup_started_at'] <= row['time'] <= recovery['finished_at'] for row in restored),
            'fresh renewal standing restoration quartet differs')
        inputs = recovery.get('ordinary_inputs')
        require(type(inputs) is list and len(inputs) in (1, 2) and [r.get('kind') for r in inputs] == ['stand', 'afk'][:len(inputs)] and
            (recovery.get('afk_attempt_source') is not None) == (len(inputs) == 2) and
            all(r.get('input') == by_ref(recovery[r['kind'] + '_attempt_source']).get('input_intent') and
                r.get('started_at') == recovery[r['kind'] + '_cleanup_started_at'] and finite(r.get('finished_at')) and
                r['started_at'] <= r['finished_at'] <= recovery['finished_at'] and r.get('input_replayed') is False for r in inputs) and
            (len(inputs) == 1 or inputs[0]['finished_at'] <= inputs[1]['started_at']),
            'renewal retains the exact once-only stand then necessary AFK inputs')
        preflights = recovery.get('renewal_input_preflights')
        require(type(preflights) is list and len(preflights) == len(inputs), 'every renewal input needs its fresh full preflight')
        for preflight, action in zip(preflights, inputs):
            kind = action['kind']
            current = preflight.get('native_state', {})
            require(set(preflight) == {'kind', 'state', 'frame', 'native_state', 'saved', 'resources', 'protected_checks', 'observed_at'} and
                preflight.get('kind') == kind and preflight.get('saved') == recovery['baseline']['saved'] and
                preflight.get('resources') == recovery['baseline']['resources'] and finite(preflight.get('observed_at')) and
                recovery['started_at'] <= preflight['observed_at'] <= by_ref(recovery[kind + '_attempt_source'])['created_at'] and
                {k: v for k, v in current.items() if k not in ('pose', 'afk')} ==
                {k: v for k, v in original.items() if k not in ('pose', 'afk')} and
                current.get('pose') == {**original['pose'], 'stand': 1 if kind == 'stand' else 0} and
                type(current.get('afk')) is bool and (kind == 'stand' or current['afk'] is True),
                'fresh renewal command changed resources, target, native state or marker chronology')
            typed_checks(preflight, 'protected_checks', PROTECTED_CHECKS)
            clean_state(preflight.get('state'), entry)
            movement = preflight.get('frame', {}).get('movement', {})
            require(movement.get('speed') == 0 and all(movement.get(k) is False for k in ('dead', 'in_combat', 'on_taxi')),
                'fresh renewal input needs its observed idle owned frame')
    return expected


def validate_housekeeping(value, failed, recovery, reload, refs, entry, ancestors=None):
    """Retain every actual A/C attempt and the sole latest ordinary reload."""
    ancestors = {} if ancestors is None else ancestors
    retained = value.get('housekeeping_attempts')
    require(type(retained) is list and 1 <= len(retained) <= 6 and
        all(type(r) is dict and set(r) == {'source', 'value'} for r in retained) and
        len({r['source']['path'] for r in retained}) == len(retained), 'complete distinct housekeeping attempt bytes are required')
    by_ref = lambda ref: next((r['value'] for r in retained if r['source'] == ref), None)
    expected = []
    if ancestors:
        prior_refs = {**refs, 'recovery': refs['prior_restoration']}
        expected += cleanup_attempts(retained, failed, ancestors['prior_restoration'], prior_refs, entry)
    expected += cleanup_attempts(retained, failed, recovery, refs, entry, ancestors, value.get('capture_packets'))
    ref = reload.get('reload_attempt_source')
    reference(ref); expected.append(ref)
    marker = by_ref(ref)
    inputs = reload.get('ordinary_inputs')
    require(type(inputs) is list and 1 <= len(inputs) <= 2 and inputs[0].get('input') == {'kind': 'chat', 'value': '/reload'} and
        all(r.get('input_sent') is True and r.get('input_replayed') is False and finite(r.get('started_at')) and
            finite(r.get('finished_at')) and reload['started_at'] <= r['started_at'] <= r['finished_at'] <= reload['finished_at'] for r in inputs) and
        (len(inputs) == 1 or recovery['baseline']['native_state']['afk'] is True and
            inputs[1].get('input') == {'kind': 'chat', 'value': '/afk'} and inputs[0]['finished_at'] <= inputs[1]['started_at']),
        'observer repair retains only one ordinary reload and necessary source AFK restoration')
    require(Path(ref['path']) == Path(refs['recovery']['path']).parent / 'item_actionbar_observer_reload_attempt.json' and
        type(marker) is dict and marker.get('schema') == 'client442_item_actionbar_observer_reload_attempt_v1' and
        marker.get('consumed') is True and marker.get('input_replay_allowed') is False and
        marker.get('input') == reload.get('reload_intent') == inputs[0]['input'] and
        marker.get('restoration_source') == refs['recovery'] and marker.get('entry_source') == refs['entry'] and
        marker.get('first_failure_source') == refs['failed'] and marker.get('code_commit') == reload['code_commit'] and
        marker.get('actor') == reload['actor'] and marker.get('runtime') == reload['runtime'] and
        marker.get('native_session') == reload['native_session'] and marker.get('operation_output') == refs['reload']['path'] and
        finite(marker.get('created_at')) and reload['started_at'] <= marker['created_at'] <= inputs[0]['started_at'] and
        sorted(r['source']['path'] for r in retained) == sorted(r['path'] for r in expected),
        'exact durable sole ordinary reload and housekeeping source set are required')


def restoration_runtime_source(recovery, retained=None):
    isolation = recovery.get('runtime_source_isolation')
    if isolation is None:
        require(retained is None, 'ordinary cleanup cannot invent runtime source isolation')
        return None
    source = isolation.get('operation_source', {})
    require(type(isolation) is dict and set(isolation) == {'code_commit', 'operation_source', 'loaded_from', 'working_candidate_inputs_used'} and
        isolation.get('code_commit') == recovery['code_commit'] and isolation.get('loaded_from') == 'git_object_bytes' and
        isolation.get('working_candidate_inputs_used') is False and
        source == {'path': str(op.lab.REPO / 'tools/client_compatibility/interaction_item_actionbar.py'),
            'sha256': ISOLATED_OPERATION_SHA}, 'cleanup runtime isolation must pin the exact approved original operation bytes')
    if retained is not None:
        validate_code_bytes({'code_source_bytes': [retained]}, [source])
        return retained
    raw = subprocess.check_output(['git', 'show', recovery['code_commit'] + ':' +
        str(Path(source['path']).relative_to(op.lab.REPO))], cwd=op.lab.REPO)
    require(hashlib.sha256(raw).hexdigest() == ISOLATED_OPERATION_SHA,
        'actual isolated cleanup Git object differs from the reviewed original operation')
    return {**source, 'raw_hex': raw.hex()}


def ending_native(rows, expected):
    from .item_actionbar_contract import records, body, INDEX
    fields = {}
    for packet in rows:
        if packet.get('direction') == 'from_native' and packet.get('name') == 'SMSG_UPDATE_OBJECT':
            for record in records(body(packet)):
                if record.get('guid') == 2:
                    fields.update(record.get('fields', {}))
    get = lambda name: fields.get(INDEX[name], 0)
    pair = lambda name: get(name) | fields.get(INDEX[name] + 1, 0) << 32
    actual = {'pose': {'stand': get('UNIT_FIELD_BYTES_1') & 255, 'sheath': get('UNIT_FIELD_BYTES_2') & 255},
        'afk': bool(get('PLAYER_FLAGS') & 2), 'selection': pair('UNIT_FIELD_TARGET'),
        'health': get('UNIT_FIELD_HEALTH'), 'max_health': get('UNIT_FIELD_MAXHEALTH'),
        'power': get('UNIT_FIELD_POWER1'), 'xp': get('PLAYER_XP'), 'next_xp': get('PLAYER_NEXT_LEVEL_XP'),
        'summon': pair('UNIT_FIELD_SUMMON')}
    require(actual == expected, 'sealed capture ending native pose, AFK, target or resources differ from its actual snapshot')
    return actual


def validate_capture(value, ready, entry, failed, recovery, reload, refs, ancestors=None):
    complete(value)
    ancestors = {} if ancestors is None else ancestors
    transition = validate_repair(ready, entry, failed, recovery, reload, refs, ancestors)
    require(value.get('phase') == PHASE and value.get('entry_source') == refs['entry'] and
        value.get('preparation_source') == value.get('fixture_source') == refs['preparation'] and
        value.get('first_failure_source') == refs['failed'] and value.get('pre_recon_recovery_source') == refs['recovery'] and
        value.get('observer_reload_source') == refs['reload'] and value.get('source') == refs['reload'] and
        value.get('actor') == entry['actor'] and value.get('runtime') == entry['runtime'] and
        value.get('native_session') == entry['native_session'] and value.get('code_commit') == reload['code_commit'] and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        value.get('input_sent') is False and value.get('mutation_sent') is False and value.get('qualification_added') is False and
        value.get('recovery_only') is not True and value.get('failed_whole_excluded') is not True and
        strict_equal(value.get('repair_code_transition'), transition) and
        value.get('committed_sources') == transition['committed_sources'] and
        reload['finished_at'] <= value['started_at'], 'fresh passive entry screen must consume the exact repair chain')
    base = failed['baseline']
    require(strict_equal(value.get('saved'), base['saved']) and strict_equal(value.get('resources'), base['resources']) and
        strict_equal(value.get('native_state'), base['native_state']) and op.public_same(value.get('public', {}), entry['public']) and
        value.get('active_spec') == entry['active_spec'], 'fresh entry screen changed original saved, native or public baseline')
    clean_state(value.get('state'), entry, 146)
    validate_code_bytes(value, transition['committed_sources'])
    validate_housekeeping(value, failed, recovery, reload, refs, entry, ancestors)
    isolated = ancestors.get('prior_restoration', recovery)
    if ancestors:
        require(value.get('prior_restoration_source') == refs['prior_restoration'] and
            value.get('failed_observer_source') == refs['failed_observer'], 'fresh capture must retain the original A and failed B sources')
        validate_code_bytes({'code_source_bytes': value.get('failed_observer_code_source_bytes')},
            deployment_sources(ancestors['failed_observer']))
        sources = transition['committed_sources']
        expected = [next(r for r in sources if Path(r['path']).name == name) for name in
            (RENEWAL_MODULE, 'interaction_item_actionbar_pre_recon_recovery.py', 'interaction_item_actionbar.py')]
        require(recovery.get('renewal_code_sources') == expected and
            recovery.get('renewal_runtime_source') == {'code_commit': recovery['code_commit'], 'operation_source': expected[2],
                'loaded_from': 'committed_working_bytes', 'working_candidate_inputs_used': False} and
            recovery['code_commit'] == reload['code_commit'] and 'runtime_source_isolation' not in recovery,
            'fresh renewal must use the actual current committed C operation and guards')
    else:
        require(not any(k in value for k in ('prior_restoration_source', 'failed_observer_source', 'failed_observer_code_source_bytes')),
            'ordinary first repair cannot invent a prior restoration or failed observer')
    if isolated.get('runtime_source_isolation') is not None:
        require(value.get('restoration_runtime_source_bytes') is not None, 'portable original isolated operation bytes are required')
        restoration_runtime_source(isolated, value['restoration_runtime_source_bytes'])
    else:
        require(value.get('restoration_runtime_source_bytes') is None, 'cleanup cannot invent runtime isolation authority')
    public_assignments(value['public'], entry['saved']['actions'], entry['active_spec'])
    preserved = online_preservation(ready['all_offline_snapshot'], value.get('all_online_snapshot'))
    require(value.get('online_preservation') == preserved, 'complete six-actor preservation proof differs')
    typed_checks(value, 'protected_checks', PROTECTED_CHECKS)
    rows = value.get('capture_packets')
    since, until, session = entry['started_at'], value['finished_at'], entry['native_session']
    forbidden_packets(rows, session, since, until)
    require(not any(p.get('name') == ACTION for p in rows), 'fresh capture refuses any prior action-bar request')
    login = login_packets(rows, session, entry['started_at'], entry['finished_at'])
    require([login[k] for k in ('modern', 'request', 'verify', 'delivered')] == entry['login_packets'] and
        len([r for r in rows if r.get('name') in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')]) == 4,
        'fresh screen must retain the one original sealed ordinary login')
    replay = native_replay(rows, session, since, until, rest_threshold=entry['native_owner_proof']['rest_threshold'])
    ending_native(replay['packets'], value['native_state'])
    require(value.get('native_owner_proof') == replay and value.get('owner_packets') == replay['packets'],
        'fresh screen must prove every native owner state from original creation')
    return transition


def verify_current_sources(reload):
    """Bind observed code to the actual committed bytes, never a proposed hash."""
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=op.lab.REPO, text=True).strip()
    require(commit == reload['code_commit'], 'current committed repair code differs from its closed observer reload')
    contents = []
    for row in code_sources(reload):
        path = Path(row['path'])
        require(path.is_file() and not path.is_symlink() and all(not p.is_symlink() for p in path.parents),
            'repair source file must be an ordinary checkout file')
        raw = subprocess.check_output(['git', 'show', commit + ':' + str(path.relative_to(op.lab.REPO))], cwd=op.lab.REPO)
        require(path.read_bytes() == raw and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'actual working and committed repair source bytes differ')
        contents.append({**row, 'raw_hex': raw.hex()})
    target = op.lab.ROOT / 'actors/scout/client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness'
    for name, sha in reload['observer_deployment']['installed'].items():
        path = target / name
        require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == sha,
            'actual installed observer146 file differs from its immutable repair receipt')
    validate_code_bytes({'code_source_bytes': contents}, code_sources(reload))
    cleanup = next(r for r in code_sources(reload) if Path(r['path']).name == 'interaction_item_actionbar_pre_recon_recovery.py')
    prior = subprocess.check_output(['git', 'show', reload['restoration_code_commit'] + ':' +
        str(Path(cleanup['path']).relative_to(op.lab.REPO))], cwd=op.lab.REPO)
    require(hashlib.sha256(prior).hexdigest() == cleanup['sha256'],
        'excluded restoration code must be identical in its actual cleanup and repair commits')
    return contents


def previous_code_bytes(observer):
    rows = []
    for source in deployment_sources(observer):
        raw = subprocess.check_output(['git', 'show', observer['code_commit'] + ':' +
            str(Path(source['path']).relative_to(op.lab.REPO))], cwd=op.lab.REPO)
        rows.append({**source, 'raw_hex': raw.hex()})
    validate_code_bytes({'code_source_bytes': rows}, deployment_sources(observer))
    return rows


def stage_source(t, stage, ready, entry):
    """Keep the explicit code transition bound through later captures and input."""
    value = op.closed(Path(stage['entry_screen_source']['path']))
    require(op.bound(Path(stage['entry_screen_source']['path'])) == stage['entry_screen_source'],
        'fresh entry-screen bytes changed')
    refs = {'preparation': stage['preparation_source'], 'entry': stage['entry_source'],
        'failed': value['first_failure_source'], 'recovery': value['pre_recon_recovery_source'],
        'reload': value['observer_reload_source']}
    objects = {}
    for role in ('failed', 'recovery', 'reload'):
        ref = refs[role]
        require(op.bound(Path(ref['path'])) == ref, 'explicit repair predecessor bytes changed')
        objects[role] = op.closed(Path(ref['path']), successful=role != 'failed')
    ancestors = repair_ancestors(objects['recovery'], refs)
    validate_capture(value, ready, entry, objects['failed'], objects['recovery'], objects['reload'], refs, ancestors)
    require(stage.get('code_commit') == t.receipt.get('code_commit') == value['code_commit'] and
        all(stage.get(key) == value.get(key) for key in ('repair_code_transition', 'committed_sources',
            'first_failure_source', 'pre_recon_recovery_source', 'observer_reload_source',
            'prior_restoration_source', 'failed_observer_source')),
        'later item stage lost its exact explicit repair code transition')
    verify_current_sources(objects['reload'])


def screen_source(t, preparation, entry_path, ready, entry, path):
    """Validate a fresh review source without rewriting the original login."""
    value = op.closed(path)
    refs = {'preparation': op.bound(preparation), 'entry': op.bound(entry_path),
        'failed': value['first_failure_source'], 'recovery': value['pre_recon_recovery_source'],
        'reload': value['observer_reload_source']}
    unconsumed(refs['entry'])
    sources = {}
    for role in ('failed', 'recovery', 'reload'):
        ref = refs[role]
        require(op.bound(Path(ref['path'])) == ref, 'fresh-screen predecessor digest changed')
        sources[role] = op.closed(Path(ref['path']), successful=role != 'failed')
    ancestors = repair_ancestors(sources['recovery'], refs)
    validate_capture(value, ready, entry, sources['failed'], sources['recovery'], sources['reload'], refs, ancestors)
    require(value['finished_at'] <= t.receipt['started_at'] and
        t.receipt.get('code_commit') == value['code_commit'], 'fresh screen must precede the actual current committed recon')
    verify_current_sources(sources['reload'])
    rows = op.packet_rows(entry['native_session'], entry['started_at'], time.time())
    require(not any(p.get('name') == ACTION for p in rows), 'fresh recon refuses any prior action-bar input')
    forbidden_packets(rows, entry['native_session'], entry['started_at'], time.time())
    t.receipt.update(entry_screen_source=op.bound(path), first_failure_source=refs['failed'],
        pre_recon_recovery_source=refs['recovery'], observer_reload_source=refs['reload'],
        repair_code_transition=deepcopy(value['repair_code_transition']), committed_sources=deepcopy(value['committed_sources']))
    if ancestors:
        t.receipt.update(prior_restoration_source=refs['prior_restoration'], failed_observer_source=refs['failed_observer'])
    t.persist()
    return value


def capture(t, preparation, entry_path, recovery_path, reload_path):
    ready, session = op.context(t, preparation)
    entry = op.entry_source(t, preparation, entry_path, ready, session)
    recovery, reload = op.closed(recovery_path), op.closed(reload_path)
    failed_ref = recovery['first_failure_source']
    failed = op.closed(Path(failed_ref['path']), successful=False)
    refs = {'preparation': op.bound(preparation), 'entry': op.bound(entry_path), 'failed': failed_ref,
        'recovery': op.bound(recovery_path), 'reload': op.bound(reload_path)}
    ancestors = repair_ancestors(recovery, refs)
    require(op.bound(Path(failed_ref['path'])) == failed_ref, 'immutable first failed recon changed')
    transition = validate_repair(ready, entry, failed, recovery, reload, refs, ancestors)
    require(t.receipt.get('code_commit') == reload['code_commit'] and reload['finished_at'] <= t.receipt['started_at'],
        'fresh capture requires the actual committed repair and later honest interval')
    unconsumed(refs['entry'])
    code_bytes = verify_current_sources(reload)
    isolated_bytes = restoration_runtime_source(ancestors.get('prior_restoration', recovery))
    attempts = []
    restorations = [ancestors['prior_restoration'], recovery] if ancestors else [recovery]
    attempt_refs = [restored.get(k + '_attempt_source') for restored in restorations for k in ('escape', 'stand', 'afk')]
    for source in attempt_refs + [reload.get('reload_attempt_source')]:
        if source is not None:
            reference(source)
            require(op.bound(Path(source['path'])) == source, 'durable housekeeping attempt bytes changed')
            from .item_actionbar_sources import private_json
            attempts.append({'source': source, 'value': private_json(Path(source['path']), False)})
    t.receipt.update(source=refs['reload'], first_failure_source=refs['failed'],
        preparation_source=refs['preparation'], fixture_source=refs['preparation'], entry_source=refs['entry'],
        native_session=session,
        pre_recon_recovery_source=refs['recovery'], observer_reload_source=refs['reload'],
        repair_code_transition=transition, committed_sources=transition['committed_sources'],
        code_source_bytes=code_bytes,
        housekeeping_attempts=attempts,
        restoration_runtime_source_bytes=isolated_bytes,
        baseline=deepcopy(failed['baseline']), phase='item_actionbar_entry_screen_capture_started',
        input_sent=False, mutation_sent=False, qualification_added=False)
    if ancestors:
        t.receipt.update(prior_restoration_source=refs['prior_restoration'], failed_observer_source=refs['failed_observer'],
            failed_observer_code_source_bytes=previous_code_bytes(ancestors['failed_observer']))
    t.persist()
    saved, resources, native, protected, state, frame = op.assert_live(failed['baseline'], session, entry['saved'],
        t=t, label='item_actionbar_fresh_entry_screen')
    clean_state(state, entry, 146)
    public = op.detail(t, 'item_actionbar_fresh_entry_bars')
    require(op.public_same(public, entry['public']) and native == failed['baseline']['native_state'],
        'fresh passive screen must preserve every original public action and native pose')
    now = op.snapshot()
    preserved = online_preservation(ready['all_offline_snapshot'], now)
    t.receipt.update(state=state, frame=frame, public=public, saved=saved, resources=resources,
        native_state=native, protected_checks=protected, all_online_snapshot=now,
        online_preservation=preserved, active_spec=entry['active_spec'])
    unconsumed(refs['entry'])
    require(verify_current_sources(reload) == code_bytes, 'committed repair source bytes changed while capturing')
    for key, path in (('preparation', preparation), ('entry', entry_path), ('failed', Path(failed_ref['path'])),
            ('recovery', recovery_path), ('reload', reload_path)):
        require(op.bound(path) == refs[key], 'immutable capture predecessor changed while observing')
    t.receipt.update(completed=True, phase=PHASE)
    return ready, entry, failed, recovery, reload, refs, ancestors


def run(t, preparation, entry_path, recovery_path, reload_path):
    chain = None
    try:
        chain = capture(t, preparation, entry_path, recovery_path, reload_path)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        if not isinstance(error, Exception):
            raise
    finally:
        until = time.time()
        t.receipt['finished_at'] = until
        if chain is not None and t.receipt.get('completed') is True:
            ready, entry, failed, recovery, reload, refs, ancestors = chain
            try:
                rows = op.packet_rows(entry['native_session'], entry['started_at'], until)
                replay = native_replay(rows, entry['native_session'], entry['started_at'], until,
                    rest_threshold=entry['native_owner_proof']['rest_threshold'])
                t.receipt.update(capture_packets=rows, native_owner_proof=replay, owner_packets=replay['packets'])
                validate_capture(t.receipt, ready, entry, failed, recovery, reload, refs, ancestors)
            except BaseException as error:
                t.receipt.update(completed=False, failure=type(error).__name__ + ': ' + str(error))
                if not isinstance(error, Exception):
                    t.persist()
                    raise
        if t.receipt.get('completed') is not True and t.receipt.get('baseline'):
            op.retain_raw(t, t.receipt['native_session'], t.receipt['started_at'], 'entry_capture_failure')
        t.persist()


def main():
    from .interaction_social import actor
    from .interaction_trial import Trial
    from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation', 'entry', 'recovery', 'observer-reload', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        trial = Trial(args.output, controller='code')
        trial.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            input_sent=False, mutation_sent=False, qualification_added=False)
        run(trial, args.preparation, args.entry, args.recovery, args.observer_reload)
        import json
        print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
