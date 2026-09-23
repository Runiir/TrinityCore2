"""Supersede, defer/reopen and the scenario finish line; synthetic workflow fixtures."""
import json
import sys
import types

import pytest

from tools.raid_program import development_graph as graph
from tests.test_development_graph import case, claimed, put, reach, receipt  # noqa: F401

SCENARIO = 'fixture_10n_fixture'


@pytest.fixture
def scoreboard(monkeypatch):
    labels = {'r3-fixture': 6, 'empty': 0}
    module = types.ModuleType('tools.raid_program.scoreboard')
    module.evaluate_target = lambda root, scenario, label=None: {'schema': 'raid_target_verdict_v1', 'scenario': scenario,
                                                                'label': label, 'kills': labels[label], 'status': 'fail'}
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', module)


def head(root):
    return graph.git(root, 'rev-parse', 'HEAD')


def supersede(g, root, **changes):
    event = {'action': 'supersede', 'revision': g['revision'], 'unit_id': g['unit']['id'],
             'reason': 'stop/export patch reviewed and verified outside the graph',
             'superseded_by': {'commits': [head(root)], 'scoreboard_label': 'r3-fixture'}}
    return event | changes


def route(g, **unit):
    return {'action': 'route', 'revision': g['revision'], 'unit_id': g['unit']['id'], 'reason': 'largest verdict gap',
            'unit': {'id': 'tuning_01', 'edge': 'owner_blood_wcl_dps_gap', 'owner_skill': 'raid-role-implementation',
                     'requirements': ['actor_1'], 'next_action': 'follow the raid-tuning-playbook'} | unit}


def park(g, action='defer', **requirements):
    return {'action': action, 'revision': g['revision'], 'unit_id': g['unit']['id'], 'requirements': requirements}


DUMMY = {'reason': 'dummy-era calibration item', 'belongs_to': 'isolated dummy calibration / phase-8 class qualification'}


def test_supersede_closes_a_stale_unit_without_a_failure_and_routes_fresh_work(case, scoreboard):
    root, state, evidence = reach(case, 'publish')
    state = graph.reduce(root, claimed(root, state), receipt(root, claimed(root, state), evidence))
    state = graph.reduce(root, state, route(state['development_graph'], id='stale', edge='stale_edge', requirements=['actor_2'],
                                            next_action='review the saved stop/export patch'))
    g = state['development_graph']
    assert g['stage'] == 'diagnose' and graph.latest_assessment(g)
    state = graph.reduce(root, state, supersede(g, root))
    g = state['development_graph']
    assert g['stage'] == 'route' and g['failures'].get('stale_edge', 0) == 0
    graph.check_graph(g)
    state = graph.reduce(root, state, route(g))
    put(root/graph.STATE_PATH, state)
    resumed = graph.resume(root)
    assert resumed['unit']['id'] == 'tuning_01' and resumed['unit']['next_action'] == 'follow the raid-tuning-playbook'
    assert resumed['latest_assessment'] is None  # the superseding evidence replaces it
    assert resumed['superseded']['unit_id'] == 'stale' and resumed['superseded']['scoreboard_label'] == 'r3-fixture'
    assert resumed['recent_attempts'][-1]['action'] == 'supersede'


@pytest.mark.parametrize('evidence,match', [
    ({'evidence': []}, 'commits and/or scoreboard_label'),
    ({'commits': ['abc1234']}, 'full commit'),
    ({'scoreboard_label': 'empty'}, 'no recorded kills'),
    ({'commits': 'HEAD'}, 'commits and/or scoreboard_label'),
])
def test_supersede_needs_real_evidence(case, scoreboard, evidence, match):
    root, state, _ = case
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, supersede(state['development_graph'], root, superseded_by=evidence))


def test_supersede_rejects_commits_outside_this_history(case, scoreboard):
    root, state, _ = case
    orphan = graph.git(root, 'commit-tree', 'HEAD^{tree}', '-m', 'unrelated')
    with pytest.raises(graph.GraphError, match='not in the current history'):
        graph.reduce(root, state, supersede(state['development_graph'], root, superseded_by={'commits': [orphan]}))


def test_supersede_of_a_claimed_operation_needs_reconciliation_and_is_not_allowed_after_a_run(case, scoreboard):
    root, state, evidence = reach(case, 'implement')
    g = state['development_graph']
    event = supersede(g, root, claim_token=g['claim']['token'])
    with pytest.raises(graph.GraphError, match='receipt requires'):
        graph.reduce(root, state, event)
    event['receipt'] = put(root/'reconcile.json', {'ownership_checked': True, 'active_operation': False,
                                                   'operation_id': g['claim']['operation_id']})
    assert graph.reduce(root, state, event)['development_graph']['stage'] == 'route'
    root, state, evidence = reach((root, state, evidence), 'assess')
    with pytest.raises(graph.GraphError, match='invalid action'):
        graph.reduce(root, state, supersede(state['development_graph'], root))


def test_deferred_requirements_leave_the_critical_path_but_stay_visible(case):
    root, state, evidence = reach(case, 'publish')
    state = graph.reduce(root, claimed(root, state), receipt(root, claimed(root, state), evidence))
    g = state['development_graph']
    assert g['requirements']['setup']['status'] == 'accepted' and g['stage'] == 'route'
    with pytest.raises(graph.GraphError, match='open requirements prevent completion'):
        graph.reduce(root, state, {'action': 'complete', 'revision': g['revision'], 'unit_id': g['unit']['id']})
    state = graph.reduce(root, state, park(g, actor_1=DUMMY, actor_2=DUMMY))
    g = state['development_graph']
    assert g['requirements']['actor_1']['deferred'] == {**DUMMY, 'revision': g['revision'] - 1}
    graph.check_graph(g)
    with pytest.raises(graph.GraphError, match='closed or unknown'):
        graph.reduce(root, state, route(g))
    put(root/graph.STATE_PATH, state)
    resumed = graph.resume(root)
    assert resumed['open_requirements'] == {} and set(resumed['deferred_requirements']) == {'actor_1', 'actor_2'}
    state = graph.reduce(root, state, {'action': 'complete', 'revision': g['revision'], 'unit_id': g['unit']['id']})
    put(root/graph.STATE_PATH, state)
    resumed = graph.resume(root)
    assert resumed['parent_objective_complete'] is True and set(resumed['deferred_requirements']) == {'actor_1', 'actor_2'}


def test_reopen_returns_a_deferred_requirement_to_the_open_set(case):
    root, state, _ = case
    state['development_graph']['unit']['requirements'] = ['setup']
    state = graph.reduce(root, state, park(state['development_graph'], actor_2=DUMMY))
    state = graph.reduce(root, state, park(state['development_graph'], 'reopen', actor_2={'reason': 'raid needs it again'}))
    requirement = state['development_graph']['requirements']['actor_2']
    assert requirement['status'] == 'open' and requirement['reopened']['was_deferred']['belongs_to'] == DUMMY['belongs_to']
    graph.check_graph(state['development_graph'])


@pytest.mark.parametrize('requirements,match', [
    ({'setup': DUMMY}, 'route the current unit away'),
    ({'actor_2': {'reason': 'x'}}, 'belongs_to'),
    ({'actor_2': {'belongs_to': 'x'}}, 'reason required'),
    ({'missing': DUMMY}, 'unknown requirement'),
])
def test_defer_validation(case, requirements, match):
    root, state, _ = case
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, park(state['development_graph'], **requirements))


def test_defer_is_only_between_units_and_cannot_be_forged(case):
    root, state, evidence = reach(case, 'implement')
    g = state['development_graph']
    with pytest.raises(graph.GraphError, match='invalid action'):
        graph.reduce(root, state, park(g, actor_2=DUMMY) | {'claim_token': g['claim']['token']})
    g['requirements']['actor_2'].update(status='deferred', deferred={**DUMMY, 'revision': 0})
    with pytest.raises(graph.GraphError, match='recorded defer transition'):
        graph.check_graph(g)


def test_legacy_dps_gate_hidden_once_the_scenario_has_a_raid_target(case):
    from tools.raid_program.evidence_task import progress_view
    root, state, _ = case
    put(root/graph.STATE_PATH, state)
    resumed = graph.resume(root)
    assert resumed['finish_line']['target_present'] is False and resumed['dps_acceptance']['minimum_reference_ratio'] == 0.95
    assert 'dps_acceptance' in progress_view(resumed, root, 'requirements')
    target = root/'experiments/configs/raid_targets'/(SCENARIO + '.json')
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({'schema': 'raid_target_v1', 'scenario': SCENARIO}))
    resumed = graph.resume(root)
    assert 'dps_acceptance' not in resumed
    assert all('dps_acceptance' not in progress_view(resumed, root, section) for section in ('summary', 'unit', 'requirements'))


def test_workloop_status_does_not_reemit_legacy_descriptor_fields(case):
    from tools.raid_program.raid_workloop import active_work_unit_status
    root, state, _ = case
    state.update(schema='cata_raid_active_work_unit_v1', first_broken_edge='stale legacy edge', next_action='stale legacy action')
    put(root/graph.STATE_PATH, state)
    status = active_work_unit_status(root)
    assert 'first_broken_edge' not in status and 'development_graph' not in status
    assert 'stale legacy action' not in status['next_action'] and status['work_unit'] == 'u1'
