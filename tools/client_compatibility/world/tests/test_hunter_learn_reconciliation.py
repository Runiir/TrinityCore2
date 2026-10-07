"""Only the pinned observation failure can join a successful native purchase."""
from copy import deepcopy
import struct

import pytest

from tools.client_compatibility import hunter_learn_reconciliation as reconciliation
from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_hunter_learn_trainer import trainer_fixture


def failed_case(target, time=1011.89):
    before = {'player': 'Harnesshunt', 'money': 8708, 'target': deepcopy(target), 'lua_errors': {},
        'guid': 'Player-1-00000006', 'level': 10, 'world_position': [-9464.400390625, 120.40000152588, 0, 0],
        'player_stats': {'health': 209},
        'blocked_actions': {}, 'trainer': {'service': {'name': 'Beast Lore', 'state': 'available', 'cost': 646}}}
    return {'id': 'spellbook.learn_spell.train1462', 'status': 'infrastructure_failure',
        'error': reconciliation.CASE_ERROR, 'selected': 'button_0', 'selection_source': 'code',
        'request': None, 'response': None, 'input_transport': [], 'time': time,
        'input': {'kind': 'click', 'value': [210, 491], 'hold': .15,
            'description': 'Click visible Button Train. Row: Benjamin Foxworthy.'},
        'before': before, 'after': {**deepcopy(before), 'money': 8062},
        'after_frame': {'movement': {'health_percent': 100, 'dead': False, 'in_combat': False, 'speed': 0}}}


def navigation_case(time=1013.5, action='beast_mastery'):
    state = {'player': 'Harnesshunt', 'level': 10, 'money': 8062, 'lua_errors': {}, 'blocked_actions': {},
        'panels': ['SpellBookFrame']}
    descriptions = {'open': 'Click visible Button SpellbookMicroButton. Row: 1.',
        'beast_mastery': 'Click visible CheckButton SpellBookSkillLineTab2.',
        'page1': 'Click visible Button SpellBookPrevPageButton.'}
    return {'id': 'hunter_learn_reconciled.' + action,
        'status': 'spellbook_open_pass' if action == 'open' else 'spellbook_navigation_pass',
        'input': {'kind': 'click', 'value': [10, 20], 'description': descriptions[action]}, 'time': time,
        'before': {**deepcopy(state), 'panels': [] if action == 'open' else ['SpellBookFrame']}, 'after': deepcopy(state)}


def reconciliation_fixture(monkeypatch):
    """Supply synthetic source bytes/facts; the production source pin is tested separately."""
    identity, rows = trainer_fixture(with_facing=True)
    session = identity['native_session']
    selected_ref = {'path': str(reconciliation.lab.ROOT / 'evidence/synthetic/selected/episode.json'), 'sha256': 'a' * 64}
    failed_ref = {'path': str(reconciliation.lab.ROOT / 'evidence/synthetic/failed_purchase/episode.json'), 'sha256': 'b' * 64}
    monkeypatch.setattr(reconciliation, 'FAILED_SOURCE', failed_ref)
    baseline = {'saved': {'spells': deepcopy(contract.BASE_SPELLS), 'actions': deepcopy(reconciliation.ACTIONS),
        'skills': [[50, 50, 50]], 'quests': []}, 'resources': {'money': 8708, 'equipment': [0],
        'backpack': [{'guid': 123, 'id': 6948, 'count': 1}], 'bags': [[], [], [], []]}, 'active_spec': 0}
    selected = {'completed': True, 'failure': None, 'phase': 'hunter_learn_lesson_selected',
        'finished_at': 1011.45, 'actor': {'guid': 6}, 'runtime': identity['runtime'], 'native_session': session,
        'fixture_source': {'path': str(reconciliation.lab.ROOT / 'evidence/synthetic/preparation/episode.json'), 'sha256': 'c' * 64},
        'entry_source': identity['entry_source'], 'baseline': baseline, 'login_known_spell_ids': [1515, 79682],
        'book_layout_baseline': {'book_type': 'spell', 'page': 1}, 'pose_fixture': {},
        'trainer_identity': identity, 'native_catalog': identity['native_catalog'],
        'controller': 'code_diagnostic_ordinary_inputs', 'model': None,
        'custom_script_permission': 'blocked_by_user',
        'softTargetInteract': {'original': '0', 'current_stock_disabled': '1', 'original_restored': False},
        'frame': {'file': 'selected.png', 'sha256': 'd' * 64}}
    public = {'active_spec': 1, 'frames': {'MainMenuBar': True}, 'power': 100, 'power_type': 2, 'actions': [
        {'button': 'ActionButton' + str(i), 'slot': i, 'visible': True} for i in range(1, 13)]}
    for slot, ident, kind in ((0, 3044, 'spell'), (9, 59752, 'spell'), (10, 9, 'flyout'), (11, 982, 'spell')):
        public['actions'][slot].update(kind=kind, id=ident)
    high = (8 << 58) | (1 << 42) | (((contract.TRAINER_GUID >> 32) & 0xfffff) << 6)
    bodies = [('from_client', 'CMSG_TRAINER_BUY_SPELL', Writer().guid(contract.TRAINER_GUID & 0xffffffff, high).pack('ii', 40, 1462).finish(), 1011.9),
        ('to_native', 'CMSG_TRAINER_BUY_SPELL', struct.pack('<QII', contract.TRAINER_GUID, 40, 1462), 1012),
        ('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', 1462, 0), 1012.1),
        ('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, 1462, 0), 1012.2),
        ('from_native', 'SMSG_TRAINER_BUY_SUCCEEDED', struct.pack('<QI', contract.TRAINER_GUID, 1462), 1012.21)]
    packets = [{'session': session, 'direction': direction, 'name': name, 'body': body.hex(), 'time': t}
        for direction, name, body, t in bodies]
    saved = {**deepcopy(baseline['saved']), 'spells': sorted(contract.BASE_SPELLS + [[1462, 1, 0]])}
    resources = {**deepcopy(baseline['resources']), 'money': 8062}
    state = {'target': deepcopy(identity['target']), 'lua_errors': {}, 'blocked_actions': {},
        'player': 'Harnesshunt', 'level': 10, 'money': 8062, 'guid': 'Player-1-00000006',
        'world_position': [-9464.400390625, 120.40000152588, 0, 0], 'player_stats': {'health': 209}}
    frame = {'movement': {'health_percent': 100, 'dead': False, 'in_combat': False, 'speed': 0}}
    failed = {k: deepcopy(v) for k, v in selected.items() if k not in ('completed', 'failure', 'phase', 'finished_at', 'frame')}
    failed.update(completed=False, failure=reconciliation.FAILURE, phase='hunter_learn_purchase_started',
        started_at=1011.8, finished_at=1013, source=selected_ref, purchase_source=selected_ref,
        screen_review={'path': str(reconciliation.lab.ROOT / 'evidence/synthetic/selected/review.json'),
            'sha256': 'e' * 64, 'frame': deepcopy(selected['frame'])},
        purchase_started_at=1011.8, purchase_finished_at=1012.3, trainer_identity_checked_at=1011.8,
        purchase_input_sent=True, input_sent=True, qualification_added=False, purchase_packets=packets,
        cases=[failed_case(identity['target'])], after_saved=deepcopy(saved), after_resources=deepcopy(resources),
        protected_checks=deepcopy(reconciliation.PROTECTED), public_actionbar_after=deepcopy(public))
    rows.extend(packets)
    proof = reconciliation.observation_reconciliation(failed, failed_ref, selected, selected_ref, saved=saved,
        resources=resources, protected_checks=deepcopy(reconciliation.PROTECTED), public=public, state=state,
        frame=frame, rows=rows, observed_until=1013.8)
    receipt = {k: deepcopy(failed[k]) for k in reconciliation.FACT_FIELDS}
    receipt.update(completed=True, failure=None, phase='hunter_learn_transition_complete', started_at=1013.1,
        finished_at=1013.9, qualification_added=False, source=selected_ref, purchase_source=selected_ref,
        controller='code_diagnostic_ordinary_inputs', model=None, custom_script_permission='blocked_by_user',
        softTargetInteract=deepcopy(selected['softTargetInteract']),
        observation_settlement_source=failed_ref, original_purchase_interval=[1011.8, 1012.3],
        original_case=deepcopy(failed['cases'][0]), original_purchase_input_sent=True,
        input_sent=True, gameplay_input_sent=False, purchase_input_sent=False, train_input_replayed=False, book_navigation_input_sent=True,
        observation_only=True, mutation_sent=False, purchase_started_at=1011.8, purchase_finished_at=1012.3,
        purchase_packets=deepcopy(packets), observation_reconciliation=proof, purchase_checks=proof['purchase_checks'],
        after_saved=saved, after_resources=resources, protected_checks=deepcopy(reconciliation.PROTECTED),
        public_actionbar_after=public, state=state, frame=frame, auto_action_placement=None, actionbar_restoration_required=False,
        cases=[navigation_case()])
    return receipt, failed, selected, rows


def test_production_source_pin_is_exact_and_source_specific():
    assert reconciliation.FAILED_SOURCE['sha256'] == '942ef7f3360fd00ff0c98f60422036da0369db340ac99f1f06f358e84f08b065'
    assert reconciliation.FAILED_SOURCE['path'].endswith('client_interactions_20261007_ui170/hunter_learning_purchase01/episode.json')


def test_original_failed_case_and_original_input_window_remain_honest(monkeypatch):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    old = deepcopy(failed)
    result = reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)
    assert failed == old and failed['cases'][0]['status'] == 'infrastructure_failure'
    assert result['purchase_checks'] == {k: True for k in reconciliation.PURCHASE_NAMES}
    assert receipt['purchase_input_sent'] is False and receipt['original_purchase_input_sent'] is True
    assert receipt['purchase_finished_at'] < receipt['started_at']
    assert receipt['original_case'] == failed['cases'][0]
    assert reconciliation.validate_observation_reconciliation(receipt, failed, selected) == result


def test_real_stock_caption_control_descriptions_and_panels_are_preserved(monkeypatch):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    receipt['cases'] = [navigation_case(1013.2, 'open'), navigation_case(1013.5), navigation_case(1013.7, 'page1')]
    assert reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)


@pytest.mark.parametrize('action', ['open', 'beast_mastery', 'page1'])
@pytest.mark.parametrize('fault', ['missing_description', 'gameplay_control', 'wrong_kind_description', 'closed_after'])
def test_caption_case_label_cannot_cover_other_control_or_closed_book(monkeypatch, action, fault):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    c = navigation_case(1013.6, action)
    receipt['cases'] = [navigation_case(1013.5), c]
    if fault == 'missing_description':
        c['input'].pop('description')
    elif fault == 'gameplay_control':
        c['input']['description'] = 'Click visible Button Train. Row: Benjamin Foxworthy.'
    elif fault == 'wrong_kind_description':
        c['input']['description'] = c['input']['description'].replace('Button ', 'CheckButton ', 1)
    else:
        c['after']['panels'] = []
    with pytest.raises(RuntimeError, match='non-caption input'):
        reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)


@pytest.mark.parametrize('action', ['beast_mastery', 'page1'])
def test_caption_tab_and_page_clicks_require_an_already_visible_spellbook(monkeypatch, action):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    c = navigation_case(1013.6, action)
    c['before']['panels'] = []
    receipt['cases'] = [navigation_case(1013.5), c]
    with pytest.raises(RuntimeError, match='non-caption input'):
        reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)


@pytest.mark.parametrize('fault', ['source', 'failure', 'failed_completed', 'failed_phase', 'original_case_status',
    'original_case_error', 'original_case_input', 'original_case_cost', 'original_case_money', 'original_case_lua',
    'original_frame', 'selected_failed', 'selected_runtime', 'selected_controller', 'original_checks', 'actions',
    'saved', 'resources', 'protected', 'public_flyout', 'purchase_packet', 'missing_packet', 'modern_guid', 'modern_suffix',
    'current_ui', 'current_target', 'current_owner', 'current_level', 'current_money', 'current_guid', 'current_pose',
    'current_health', 'current_power', 'current_power_type', 'current_frame_health', 'current_frame_dead', 'new_train_case', 'new_input',
    'missing_navigation', 'bad_navigation', 'failed_navigation', 'navigation_owner', 'navigation_time',
    'new_original_case', 'new_start', 'new_interval',
    'claimed_checks', 'qualification', 'recovery', 'settlement', 'new_runtime', 'new_source', 'bar_restoration'])
def test_specific_observer_error_never_admits_other_failure_or_rewritten_facts(monkeypatch, fault):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    c = failed['cases'][0]
    if fault == 'source': receipt['observation_settlement_source']['sha256'] = 'f' * 64
    elif fault == 'failure': failed['failure'] = 'RuntimeError: native purchase failed'
    elif fault == 'failed_completed': failed['completed'] = True
    elif fault == 'failed_phase': failed['phase'] = 'hunter_learn_transition_complete'
    elif fault == 'original_case_status': c['status'] = 'hunter_learning_pass'
    elif fault == 'original_case_error': c['error'] = 'different error'
    elif fault == 'original_case_input': c['input']['value'][0] += 1
    elif fault == 'original_case_cost': c['before']['trainer']['service']['cost'] += 1
    elif fault == 'original_case_money': c['after']['money'] += 1
    elif fault == 'original_case_lua': c['after']['lua_errors'] = ['fault']
    elif fault == 'original_frame': failed['screen_review']['frame']['file'] = 'other.png'
    elif fault == 'selected_failed': selected['completed'] = False
    elif fault == 'selected_runtime': selected['runtime']['worldserver']['pid'] += 1
    elif fault == 'selected_controller': selected['controller'] = 'model'
    elif fault == 'original_checks': failed['purchase_checks'] = {'ordinary_train': True}
    elif fault == 'actions': receipt['after_saved']['actions'].append([0, 1, 1462, 0])
    elif fault == 'saved': receipt['after_saved']['skills'][0][1] += 1
    elif fault == 'resources': receipt['after_resources']['backpack'][0]['count'] += 1
    elif fault == 'protected': receipt['protected_checks']['actor_1_unchanged'] = False
    elif fault == 'public_flyout': receipt['public_actionbar_after']['actions'][10]['id'] += 1
    elif fault == 'purchase_packet': failed['purchase_packets'][1]['body'] = '00'
    elif fault == 'missing_packet': rows.pop()
    elif fault in ('modern_guid', 'modern_suffix'):
        p = next(p for p in rows if p['direction'] == 'from_client')
        p['body'] = ('000028000000b6050000' if fault == 'modern_guid' else p['body'] + '00')
    elif fault == 'current_ui': receipt['state']['blocked_actions'] = ['cast']
    elif fault == 'current_target': receipt['state']['target']['guid'] = 'other'
    elif fault == 'current_owner': receipt['state']['player'] = 'Harnesstwo'
    elif fault == 'current_level': receipt['state']['level'] = 1
    elif fault == 'current_money': receipt['state']['money'] = 8708
    elif fault == 'current_guid': receipt['state']['guid'] = 'Player-1-00000002'
    elif fault == 'current_pose': receipt['state']['world_position'][0] += 1
    elif fault == 'current_health': receipt['state']['player_stats']['health'] -= 1
    elif fault == 'current_power': receipt['public_actionbar_after']['power'] -= 1
    elif fault == 'current_power_type': receipt['public_actionbar_after']['power_type'] = 0
    elif fault == 'current_frame_health': receipt['frame']['movement']['health_percent'] = 90
    elif fault == 'current_frame_dead': receipt['frame']['movement']['dead'] = True
    elif fault == 'new_train_case': receipt['cases'].append({'id': 'spellbook.learn_spell.train1462', 'status': 'hunter_learning_pass'})
    elif fault == 'new_input': receipt['purchase_input_sent'] = True
    elif fault == 'missing_navigation': receipt['cases'] = []
    elif fault == 'bad_navigation': receipt['cases'][0]['id'] = 'spellbook.learn_spell.train1462'
    elif fault == 'failed_navigation': receipt['cases'][0]['status'] = 'infrastructure_failure'
    elif fault == 'navigation_owner': receipt['cases'][0]['after']['player'] = 'Other'
    elif fault == 'navigation_time': receipt['cases'][0]['time'] = 1012
    elif fault == 'new_original_case': receipt['original_case']['status'] = 'hunter_learning_pass'
    elif fault == 'new_start': receipt['started_at'] = 1011.8
    elif fault == 'new_interval': receipt['purchase_started_at'] = receipt['started_at']
    elif fault == 'claimed_checks': receipt['purchase_checks']['ordinary_train'] = False
    elif fault == 'qualification': receipt['qualification_added'] = True
    elif fault == 'recovery': receipt['recovery_only'] = True
    elif fault == 'settlement': receipt['failed_repair_excluded'] = True
    elif fault == 'new_runtime': receipt['runtime']['worldserver']['start_ticks'] = 'other'
    elif fault == 'new_source': receipt['source']['sha256'] = 'f' * 64
    else: receipt['actionbar_restoration_required'] = True
    with pytest.raises((RuntimeError, ValueError)):
        reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)


@pytest.mark.parametrize('name', ['CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL', 'SMSG_TRAINER_BUY_FAILED',
    'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION'])
def test_complete_raw_interval_rejects_later_gameplay_before_fresh_observation(monkeypatch, name):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    rows.append({'session': failed['native_session'], 'direction': 'to_native', 'name': name,
        'body': '00', 'time': 1013.7})
    with pytest.raises(RuntimeError, match='later gameplay'):
        reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)


def test_pre_purchase_gameplay_on_the_owned_entry_is_also_refused(monkeypatch):
    receipt, failed, selected, rows = reconciliation_fixture(monkeypatch)
    rows.append({'session': failed['native_session'], 'direction': 'to_native', 'name': 'CMSG_CAST_SPELL',
        'body': '00', 'time': 1011.7})
    with pytest.raises(RuntimeError, match='later gameplay'):
        reconciliation.validate_observation_reconciliation(receipt, failed, selected, wire=rows)
