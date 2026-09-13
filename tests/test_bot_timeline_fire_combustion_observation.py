"""Root native Fire observations survive existing cached-mask timeline/HTML paths."""
from copy import deepcopy

import pytest

from tools.raid_program.bot_timeline import _diagnosis_events, build_timeline_from_rows
from tools.raid_program.bot_timeline_html import render_timeline_html
from tests.test_bot_timeline import _bound, _embedded_model, _report


def payload():
    return {'cohort_id': 'raid', 'server_epoch': 11, 'attempt_id': 2,
            'exported_at_ms': 9000, 'bots': [{'identity': {'bot_guid': 7}, 'snapshot': {
                'runtime': {'last_decision_tick_ms': 1200}, 'policy': {'valid_action_mask_json': {
                    'schema': 'bot_valid_action_mask_v2',
                    'evaluation': {'started_at_ms': 1000, 'actor_guid': 7, 'target_guid': 76, 'target_entry': 42347,
                                   'scope': {'attempt_id': 2, 'instance_id': 2}},
                    'observation': {'schema': 'fire_combustion_candidate_observation_v1',
                                    'evaluation_started_at_ms': 1000, 'observed_at_ms': 1002,
                                    'actor_guid': 7, 'target_guid': 76, 'target_entry': 42347,
                                    'owned_auras': {'ignite_effect0_amount': 9999},
                                    'estimate_kind': 'derived_candidate_state_not_observed_outcome',
                                    'gate': {'ignite_below_10000': True}},
                    'actions': [{'spell_id': 11129, 'valid': False, 'reject_reason': 'combustion_dot_window_not_ready'}]}}}}]}


def mask(value):
    return value['bots'][0]['snapshot']['policy']['valid_action_mask_json']


def contexts(events):
    return [e for e in events if e['kind'] == 'diagnosis_decision_context']


def test_observation_native_identity_clocks_and_html_retention():
    value = payload()
    before = deepcopy(value)
    direct = contexts(_diagnosis_events([value]))
    model, _ = build_timeline_from_rows([_bound('diagnosis', value)], _report())
    built = contexts(model['events'])
    embedded = contexts(_embedded_model(render_timeline_html(model))['events'])
    for events in (direct, built, embedded):
        assert len(events) == 1
        event = events[0]
        compact = event['valid_action_mask']
        obs = compact['observation']
        assert obs == mask(value)['observation']
        for field in ('actor_guid', 'target_guid', 'target_entry'):
            assert obs[field] == compact['evaluation'][field]
        assert obs['evaluation_started_at_ms'] == event['at_ms'] == 1000
        assert obs['observed_at_ms'] == 1002 != value['exported_at_ms']
        assert event['stale_relative_to_export'] is True
        assert not ({'submission', 'finish', 'land', 'cast_id'} & set(obs))
    assert value == before


def test_changed_observation_participates_in_context_dedup_without_retimestamping():
    first = payload()
    second = deepcopy(first)
    mask(second)['observation']['owned_auras']['ignite_effect0_amount'] = 10000
    mask(second)['observation']['gate']['ignite_below_10000'] = False
    second['exported_at_ms'] = 10000
    events = contexts(_diagnosis_events([first, first, second, second]))
    assert len(events) == 2
    assert [e['at_ms'] for e in events] == [1000, 1000]
    assert [e['valid_action_mask']['observation']['owned_auras']['ignite_effect0_amount'] for e in events] == [9999, 10000]


@pytest.mark.parametrize('bad', [None, [], 'bad', 7])
def test_malformed_observation_is_empty(bad):
    value = payload()
    mask(value)['observation'] = bad
    assert contexts(_diagnosis_events([value]))[0]['valid_action_mask']['observation'] == {}


def test_missing_and_frost_observations_keep_existing_contract():
    value = payload()
    del mask(value)['observation']
    assert contexts(_diagnosis_events([value]))[0]['valid_action_mask']['observation'] == {}
    mask(value)['observation'] = {'schema': 'frost', 'proc': True}
    assert contexts(_diagnosis_events([value]))[0]['valid_action_mask']['observation'] == mask(value)['observation']
