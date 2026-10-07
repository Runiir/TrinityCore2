"""Source-specific proof of UI170's paid purchase with a flyout observer failure."""
from copy import deepcopy
import math
import struct

from . import lab_runtime as lab
from .hunter_learn_contract import require, SPELL, NAME, BASE_SPELLS, TRAINER_GUID, TRAINER, PRICE, MONEY, learned_checks
from .hunter_learn_autobar import addition_guard
from .hunter_learn_trainer import validate_trainer_identity, replay as trainer_replay
from .world.buffer import Reader

SCHEMA = 'client442_hunter_learn_observation_reconciliation_v1'
FAILED_SOURCE = {'path': str(lab.ROOT / 'evidence/client_interactions_20261007_ui170/hunter_learning_purchase01/episode.json'),
    'sha256': '942ef7f3360fd00ff0c98f60422036da0369db340ac99f1f06f358e84f08b065'}
FAILURE = 'RuntimeError: RuntimeError: public action assignment differs from exact saved rows'
CASE_ERROR = 'RuntimeError: public action assignment differs from exact saved rows'
ACTIONS = [[0, 0, 3044, 0], [0, 9, 59752, 0], [0, 10, 9, 48], [0, 11, 982, 0]]
PROTECTED = {'actor_' + str(g) + '_unchanged': True for g in range(1, 6)}
PURCHASE_NAMES = frozenset(('one_exact_native_purchase', 'owned_ordered_learn_delivery', 'no_purchase_failure',
    'saved_direct_spell_only', 'exact_charge_resources', 'ordinary_train', 'protected_originals', 'saved_rows',
    'no_spell_or_pet_cast', 'ui_clean'))
FACT_FIELDS = ('actor', 'runtime', 'native_session', 'fixture_source', 'entry_source', 'baseline',
    'login_known_spell_ids', 'book_layout_baseline', 'pose_fixture', 'trainer_identity', 'native_catalog',
    'screen_review', 'purchase_source', 'source', 'trainer_identity_checked_at')
NAMES = frozenset(('CMSG_TRAINER_BUY_SPELL', 'SMSG_TRAINER_BUY_SUCCEEDED', 'SMSG_TRAINER_BUY_FAILED',
    'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS', 'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def packet_key(p):
    return tuple(p.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


def clean(state):
    return isinstance(state, dict) and not state.get('lua_errors') and not state.get('blocked_actions')


def original_case(failed):
    cases = failed.get('cases')
    require(isinstance(cases, list) and len(cases) == 1 and isinstance(cases[0], dict),
        'pinned observation failure requires the sole original failed Train case')
    c = cases[0]
    service = c.get('before', {}).get('trainer', {}).get('service', {})
    require(c.get('id') == 'spellbook.learn_spell.train1462' and c.get('status') == 'infrastructure_failure' and
        c.get('error') == CASE_ERROR and c.get('selected') == 'button_0' and c.get('selection_source') == 'code' and
        c.get('request') is None and c.get('response') is None and c.get('input_transport') == [] and
        c.get('input') == {'kind': 'click', 'value': [210, 491], 'hold': .15,
            'description': 'Click visible Button Train. Row: Benjamin Foxworthy.'} and
        service.get('name') == NAME and service.get('state') == 'available' and service.get('cost') == PRICE and
        c.get('before', {}).get('player') == c.get('after', {}).get('player') == 'Harnesshunt' and
        c.get('before', {}).get('money') == MONEY and c.get('after', {}).get('money') == MONEY - PRICE and
        clean(c.get('before')) and clean(c.get('after')) and finite(c.get('time')) and
        failed['purchase_started_at'] <= c['time'] <= failed['purchase_finished_at'],
        'exact original failed Train case, ordinary input or clean rendered native outcome differs')
    return c


def observation_reconciliation(failed, failed_ref, selected, selected_ref, *, saved, resources,
        protected_checks, public, state, frame, rows, observed_until):
    require(failed_ref == FAILED_SOURCE and isinstance(failed, dict) and failed.get('completed') is False and
        failed.get('failure') == FAILURE and failed.get('phase') == 'hunter_learn_purchase_started' and
        failed.get('purchase_input_sent') is True and failed.get('input_sent') is True and
        failed.get('purchase_checks') is None and failed.get('qualification_added') is False and
        all(failed.get(k) is not True for k in ('recovery_only', 'failed_whole_excluded', 'settlement_only', 'failed_repair_excluded')),
        'only the exact immutable UI170 flyout observation failure can be reconciled')
    require(selected.get('completed') is True and selected.get('failure') is None and
        selected.get('phase') == 'hunter_learn_lesson_selected' and selected_ref == failed.get('source') == failed.get('purchase_source') and
        selected.get('finished_at', math.inf) <= failed.get('started_at', 0) and
        all(selected.get(k) == failed.get(k) for k in ('actor', 'runtime', 'native_session', 'fixture_source',
            'entry_source', 'baseline', 'login_known_spell_ids', 'book_layout_baseline', 'pose_fixture', 'trainer_identity', 'native_catalog')) and
        failed.get('screen_review', {}).get('frame') == selected.get('frame') and
        failed.get('controller') == selected.get('controller') == 'code_diagnostic_ordinary_inputs' and
        failed.get('model') is selected.get('model') is None and
        failed.get('custom_script_permission') == selected.get('custom_script_permission') == 'blocked_by_user' and
        failed.get('softTargetInteract') == selected.get('softTargetInteract') ==
            {'original': '0', 'current_stock_disabled': '1', 'original_restored': False},
        'original selected lesson, runtime, screen review or ordinary controller differs')
    since, until = failed['purchase_started_at'], failed['purchase_finished_at']
    require(all(finite(t) for t in (since, until, failed.get('started_at'), failed.get('finished_at'), observed_until)) and
        failed['started_at'] <= since < until <= failed['finished_at'] < observed_until and
        failed.get('trainer_identity_checked_at') == since and
        failed['baseline']['active_spec'] == 0 and failed['baseline']['saved']['actions'] == ACTIONS,
        'original paid input interval or exact four-row flyout baseline differs')
    case = original_case(failed)
    relevant_rows = [p for p in rows if p.get('session') == failed['native_session'] and p.get('name') in NAMES]
    require(all(finite(p.get('time')) for p in relevant_rows), 'owned gameplay packet time is invalid')
    packets = [p for p in relevant_rows if
        finite(p.get('time')) and failed['trainer_identity']['source_interval'][0] <= p['time'] <= observed_until and
        p.get('name') in NAMES]
    recorded = failed.get('purchase_packets', [])
    require(len(recorded) == len(packets) == 5 and len({packet_key(p) for p in packets}) == 5 and
        {packet_key(p) for p in packets} == {packet_key(p) for p in recorded} and
        all(since <= p['time'] <= until for p in packets),
        'complete original five purchase packets changed or later gameplay occurred')
    modern = [p for p in packets if (p.get('direction'), p.get('name')) == ('from_client', 'CMSG_TRAINER_BUY_SPELL')]
    success = [p for p in packets if (p.get('direction'), p.get('name')) == ('from_native', 'SMSG_TRAINER_BUY_SUCCEEDED')]
    require(len(modern) == len(success) == 1 and success[0]['body'] == struct.pack('<QI', TRAINER_GUID, SPELL).hex(),
        'one original modern Train and native purchase completion are required')
    r = Reader(bytes.fromhex(modern[0]['body']))
    guid = r.guid()
    trainer, spell = r.unpack('ii')
    r.end()
    require(guid == (TRAINER_GUID & 0xffffffff, (8 << 58) | (1 << 42) | (((TRAINER_GUID >> 32) & 0xfffff) << 6)) and
        trainer == TRAINER and spell == SPELL and case['time'] <= modern[0]['time'] <= success[0]['time'],
        'original ordinary Train request GUID, IDs or input ordering differs')
    baseline = failed['baseline']
    expected_saved = {**baseline['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
    expected_resources = {**baseline['resources'], 'money': MONEY - PRICE}
    require(failed.get('after_saved') == saved == expected_saved and
        failed.get('after_resources') == resources == expected_resources and protected_checks ==
        failed.get('protected_checks') == PROTECTED and all(v is True for v in protected_checks.values()),
        'full current saved/resources or protected actors differ from the original paid outcome')
    require(state.get('player') == 'Harnesshunt' and state.get('level') == 10 and state.get('money') == MONEY - PRICE,
        'fresh public observation does not belong to the paid level-ten owner')
    original_state = case['after']
    require(state.get('guid') == original_state.get('guid') == 'Player-1-00000006' and
        state.get('world_position') == original_state.get('world_position') and
        state.get('player_stats', {}).get('health') == original_state.get('player_stats', {}).get('health') == 209 and
        public.get('power') == failed['public_actionbar_after'].get('power') == 100 and
        public.get('power_type') == failed['public_actionbar_after'].get('power_type') == 2 and
        frame.get('movement', {}).get('health_percent') == case.get('after_frame', {}).get('movement', {}).get('health_percent') == 100 and
        frame.get('movement', {}).get('dead') is False and frame.get('movement', {}).get('in_combat') is False and
        frame.get('movement', {}).get('speed') == 0,
        'paid owner GUID, pose, health, power or idle frame differs from original native outcome')
    require(addition_guard(ACTIONS, saved['actions'], packets, failed['native_session'], since,
        observed_until, baseline['active_spec'], failed['public_actionbar_after']) is None and
        addition_guard(ACTIONS, saved['actions'], packets, failed['native_session'], since,
        observed_until, baseline['active_spec'], public) is None, 'observation reconciliation cannot restore or add action rows')
    validate_trainer_identity(failed['trainer_identity'], state.get('target', {}), failed['native_catalog'],
        failed['runtime'], failed['entry_source'], wire=rows, observed_until=observed_until)
    trainer_packets = trainer_replay(rows, failed['native_session'], failed['trainer_identity']['source_interval'][0],
        observed_until, failed['native_catalog'])[3]
    checks = learned_checks(packets, baseline['saved']['spells'], saved['spells'], baseline['resources'],
        resources, failed['native_session'], since, until)
    checks.update(ordinary_train=True, protected_originals=True, saved_rows=saved == expected_saved,
        no_spell_or_pet_cast=not any(p['name'] in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION', 'CMSG_SET_ACTION_BUTTON') for p in packets),
        ui_clean=clean(case['after']) and clean(state))
    require(set(checks) == PURCHASE_NAMES and all(v is True for v in checks.values()),
        'original paid native outcome lacks all ten independently derived checks')
    return deepcopy({'schema': SCHEMA, 'source': failed_ref, 'selected_source': selected_ref,
        'original_purchase_interval': [since, until], 'original_case': case, 'checked_at': observed_until,
        'packets': recorded, 'trainer_wire_packets': trainer_packets, 'purchase_checks': checks,
        'after_saved': saved, 'after_resources': resources,
        'protected_checks': protected_checks, 'public_actionbar_after': public, 'current_state': state, 'current_frame': frame})


def navigation_cases(receipt):
    allowed = {'hunter_learn_reconciled.open': 'spellbook_open_pass',
        'hunter_learn_reconciled.beast_mastery': 'spellbook_navigation_pass',
        'hunter_learn_reconciled.page1': 'spellbook_navigation_pass'}
    descriptions = {'hunter_learn_reconciled.open': (
        'Click visible Button SpellbookMicroButton.', 'Click visible Button SpellbookMicroButton. Row: 1.'),
        'hunter_learn_reconciled.beast_mastery': ('Click visible CheckButton SpellBookSkillLineTab2.',),
        'hunter_learn_reconciled.page1': ('Click visible Button SpellBookPrevPageButton.',)}
    cases = receipt.get('cases')
    require(isinstance(cases, list) and cases and
        any(c.get('id') == 'hunter_learn_reconciled.beast_mastery' for c in cases),
        'new observation receipt requires its actual stock caption navigation')
    for c in cases:
        require(c.get('id') in allowed and c.get('status') == allowed[c['id']] and not c.get('error') and
            c.get('input', {}).get('kind') == 'click' and finite(c.get('time')) and
            c.get('input', {}).get('description') in descriptions[c['id']] and
            'SpellBookFrame' in c.get('after', {}).get('panels', []) and
            (c['id'] == 'hunter_learn_reconciled.open' or 'SpellBookFrame' in c.get('before', {}).get('panels', [])) and
            receipt['started_at'] <= c['time'] <= receipt['finished_at'] and
            all(s.get('player') == 'Harnesshunt' and s.get('level') == 10 and s.get('money') == MONEY - PRICE and clean(s)
                for s in (c.get('before', {}), c.get('after', {}))),
            'new observation cases include unproven or non-caption input')


def validate_observation_reconciliation(receipt, failed, selected, *, wire=None):
    proof = receipt.get('observation_reconciliation', {})
    require(isinstance(proof, dict) and proof.get('schema') == SCHEMA and
        receipt.get('observation_settlement_source') == FAILED_SOURCE and receipt.get('source') ==
        receipt.get('purchase_source') == failed.get('purchase_source') and
        receipt.get('original_purchase_interval') == [failed['purchase_started_at'], failed['purchase_finished_at']] and
        receipt.get('original_case') == failed.get('cases', [None])[0] and
        receipt.get('original_purchase_input_sent') is True and receipt.get('purchase_input_sent') is False and
        receipt.get('input_sent') is True and receipt.get('gameplay_input_sent') is False and
        receipt.get('train_input_replayed') is False and receipt.get('observation_only') is True and
        receipt.get('mutation_sent') is False and receipt.get('controller') == failed.get('controller') and
        receipt.get('model') is None and receipt.get('custom_script_permission') == 'blocked_by_user' and
        receipt.get('softTargetInteract') == failed.get('softTargetInteract') and
        receipt.get('book_navigation_input_sent') is True and
        all(receipt.get(k) == failed.get(k) for k in FACT_FIELDS) and
        all(receipt.get(k) == failed.get(k) for k in ('purchase_started_at', 'purchase_finished_at', 'purchase_packets')) and
        receipt.get('completed') is True and receipt.get('failure') is None and
        receipt.get('phase') == 'hunter_learn_transition_complete' and receipt.get('qualification_added') is False and
        finite(receipt.get('started_at')) and finite(receipt.get('finished_at')) and finite(proof.get('checked_at')) and
        failed['finished_at'] < receipt['started_at'] <= proof['checked_at'] <= receipt['finished_at'] and
        not any(c.get('id') == 'spellbook.learn_spell.train1462' for c in receipt.get('cases', [])) and
        all(receipt.get(k) is not True for k in ('recovery_only', 'failed_whole_excluded', 'settlement_only', 'failed_repair_excluded')),
        'new source-specific observation receipt rewrites original input/case or conceals failed gameplay')
    navigation_cases(receipt)
    rows = [*proof.get('trainer_wire_packets', []), *proof.get('packets', [])] if wire is None else list(wire)
    expected = observation_reconciliation(failed, receipt['observation_settlement_source'], selected,
        receipt['purchase_source'], saved=receipt['after_saved'], resources=receipt['after_resources'],
        protected_checks=receipt['protected_checks'], public=receipt['public_actionbar_after'],
        state=receipt['state'], frame=receipt['frame'], rows=rows, observed_until=proof['checked_at'])
    require(proof == expected and receipt.get('purchase_checks') == expected['purchase_checks'] and
        receipt.get('auto_action_placement') is None and receipt.get('actionbar_restoration_required') is False,
        'source-bound observation proof differs from independently rederived paid facts')
    return proof
