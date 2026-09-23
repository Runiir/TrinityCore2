"""Verdict-based acceptance with a fake scoreboard; synthetic fixtures, not raid evidence."""
import copy
import sys
import types

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import graph_acceptance as acceptance
from tests.test_development_graph import case, claimed, put, reach, receipt  # noqa: F401

SCENARIO = 'fixture_10n_fixture'


def make_verdict(label='batch1', actor1='pass', actor2='pass', overall='pass', ratio=1.02):
    row = lambda spec, role, status: {'spec': spec, 'role': role, 'n': 3, 'mean_dps': 102.0, 'sd_dps': 1.5,
                                      'target_dps': 100.0, 'ratio': ratio, 'status': status}
    return {'schema': 'raid_target_verdict_v1', 'scenario': SCENARIO, 'label': label, 'kills': 3,
            'target_path': 'experiments/configs/raid_targets/' + SCENARIO + '.json',
            'actors': {'1': row('blood_death_knight', 'tank', actor1), '2': row('holy_paladin', 'healer', actor2)},
            'encounter': {'n': 3, 'clears': 3, 'mean_party_dps': 900.0, 'mean_duration_sec': 310.0,
                          'boss_window_deaths': 0, 'status': overall},
            'status': overall}


@pytest.fixture
def scoreboard(monkeypatch):
    """Stand-in for tools.raid_program.scoreboard.evaluate_target (owned elsewhere)."""
    batches = {'batch1': make_verdict()}
    module = types.ModuleType('tools.raid_program.scoreboard')
    module.evaluate_target = lambda root, scenario, label=None: copy.deepcopy(batches[label]) | {'scenario': scenario}
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', module)
    return batches


@pytest.fixture
def assessing(case):
    """A class_native unit for actor_1 and the encounter, validated with a scoreboard batch."""
    root, state, evidence = case
    g = state['development_graph']
    g['requirements']['encounter'] = {'status': 'open', 'needs_raid': True, 'needs_performance': True, 'needs_all_actors': True}
    g['unit']['requirements'] = ['setup', 'actor_1', 'encounter']
    root, state, evidence = reach((root, state, evidence), 'validate')
    state = graph.reduce(root, state, receipt(root, state, evidence, scoreboard_label='batch1'))
    assert state['development_graph']['run']['scoreboard_label'] == 'batch1'
    return root, state, evidence


def assessment(root, state, evidence, verdict, **changes):
    """Minimal verdict adapter: no baseline, comparison, actor reviews or manual flags."""
    fields = {'verdict': verdict, 'encounter_clear': True, 'accepted_requirements': ['actor_1', 'encounter'], **changes}
    event = receipt(root, state, evidence, **fields)
    r = graph.read(root/event['receipt']['path'])
    for key in ('baseline', 'comparison', 'actor_reviews', 'repair_accepted', 'performance_accepted'):
        if key not in changes:
            r.pop(key)
    event['receipt'] = put(root/event['receipt']['path'], r)
    return event


def test_passing_verdict_accepts_actor_and_encounter_and_records_it(assessing, scoreboard):
    root, state, evidence = assessing
    put(root/graph.STATE_PATH, state)
    written = acceptance.write_verdict(root, 'batch1')
    assert written['acceptable_unit_requirements'] == ['actor_1', 'encounter']
    state = graph.reduce(root, state, assessment(root, state, evidence, written['verdict']))
    g = state['development_graph']
    assert g['pending_acceptance'] == ['actor_1', 'encounter'] and g['outcomes']['verdict_status'] == 'pass'
    state = claimed(root, state)
    state = graph.reduce(root, state, receipt(root, state, evidence))
    g = state['development_graph']
    graph.check_graph(g)
    actor = g['requirements']['actor_1']
    assert actor['status'] == 'accepted' and actor['verdict']['receipt'] == written['verdict']
    assert (actor['verdict']['label'], actor['verdict']['kills'], actor['verdict']['ratio']) == ('batch1', 3, 1.02)
    assert g['requirements']['encounter']['verdict']['ratios'] == {'1': 1.02, '2': 1.02}
    assert g['requirements']['setup']['status'] == 'open'


@pytest.mark.parametrize('actor1,overall,key,match', [
    ('fail', 'fail', 'actor_1', 'verdict is fail'),
    ('no_reference', 'fail', 'actor_1', 'reference work, never acceptance'),
    ('insufficient_kills', 'insufficient_kills', 'actor_1', 'not pass'),
    ('pass', 'fail', 'encounter', 'verdict is fail'),
])
def test_non_passing_verdict_keeps_requirement_open(assessing, scoreboard, actor1, overall, key, match):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(actor1=actor1, overall=overall)
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, assessment(root, state, evidence, ref, accepted_requirements=[key]))


def test_actor_pass_can_close_while_encounter_stays_open(assessing, scoreboard):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(actor2='fail', overall='fail')
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    g = graph.reduce(root, state, assessment(root, state, evidence, ref, accepted_requirements=['actor_1']))['development_graph']
    assert g['pending_acceptance'] == ['actor_1'] and g['outcomes']['performance_accepted'] is False


@pytest.mark.parametrize('mutate,match', [
    (lambda v: v.update(label='batch0'), 'scoreboard_label'),
    (lambda v: v.update(scenario='other_10n_boss'), 'scenario differs'),
    (lambda v: v['actors']['1'].update(ratio=1.5), 'differs from the scoreboard recomputation'),
    (lambda v: v['actors']['1'].update(spec='fire_mage'), 'differs from the scoreboard recomputation'),
])
def test_verdict_must_be_this_runs_fresh_batch(assessing, scoreboard, mutate, match):
    root, state, evidence = assessing
    cited = copy.deepcopy(scoreboard['batch1']) | {'scenario': SCENARIO}
    mutate(cited)
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, assessment(root, state, evidence, put(root/'verdict.json', cited)))


def test_verdict_spec_must_match_roster_actor(assessing, scoreboard):
    root, state, evidence = assessing
    scoreboard['batch1']['actors']['1']['spec'] = 'fire_mage'
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match='spec differs'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, accepted_requirements=['actor_1']))


def test_run_without_label_cannot_use_a_verdict(case, scoreboard):
    root, state, evidence = case
    state['development_graph']['unit']['requirements'] = ['actor_1']
    root, state, evidence = reach((root, state, evidence), 'assess')
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match='scoreboard_label'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, accepted_requirements=['actor_1']))


def test_verdict_path_rejects_manual_performance_and_unattributable_runs(assessing, scoreboard):
    root, state, evidence = assessing
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match='omit performance_accepted'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, performance_accepted=True))
    state['development_graph']['run']['terminal_reason'] = 'infrastructure_loss'
    with pytest.raises(graph.GraphError, match='unattributable'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, encounter_clear=False, accepted_requirements=['actor_1']))


def test_missing_scoreboard_is_an_error_not_acceptance(assessing, monkeypatch):
    root, state, evidence = assessing
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', None)
    ref = put(root/'verdict.json', make_verdict() | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match='scoreboard unavailable'):
        graph.reduce(root, state, assessment(root, state, evidence, ref))


def test_verdict_does_not_close_other_requirements_without_repair(assessing, scoreboard):
    root, state, evidence = assessing
    ref = put(root/'verdict.json', scoreboard['batch1'] | {'scenario': SCENARIO})
    with pytest.raises(graph.GraphError, match='repair acceptance'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, accepted_requirements=['setup']))
    g = graph.reduce(root, state, assessment(root, state, evidence, ref, repair_accepted=True,
                     accepted_requirements=['setup', 'actor_1']))['development_graph']
    assert g['pending_acceptance'] == ['setup', 'actor_1'] and set(g['pending_verdict']) == {'actor_1'}


def test_raid_target_requirement_needs_the_target_file(case):
    root, state, evidence = case
    g = state['development_graph']
    g['requirements']['raid_target'] = {'status': 'open', 'target_path': 'fixture'}
    g['unit']['requirements'] = ['raid_target']
    root, state, evidence = reach((root, state, evidence), 'assess')
    with pytest.raises(graph.GraphError, match='raid target file missing'):
        graph.reduce(root, state, receipt(root, state, evidence, accepted_requirements=['raid_target']))
    put(root/'experiments/configs/raid_targets'/(SCENARIO + '.json'), {'schema': 'raid_target_v1', 'scenario': SCENARIO})
    result = graph.reduce(root, state, receipt(root, state, evidence, accepted_requirements=['raid_target']))
    assert result['development_graph']['pending_acceptance'] == ['raid_target']


def test_finish_line_and_print_only_verdict(assessing, scoreboard):
    root, state, evidence = assessing
    put(root/graph.STATE_PATH, state)
    finish = acceptance.finish_line(root, state['development_graph'])
    assert finish['scenario'] == SCENARIO and finish['target_present'] is False
    assert finish['open_actor_requirements'] == ['actor_1', 'actor_2'] and finish['open_encounter_requirements'] == ['encounter']
    shown = acceptance.write_verdict(root, 'batch1', write=False)
    assert 'verdict' not in shown and shown['actors']['1']['ratio'] == 1.02
    assert not (root/acceptance.VERDICT_DIR).exists()
