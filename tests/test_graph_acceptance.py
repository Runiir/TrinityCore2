"""Verdict-based acceptance with a fake scoreboard; synthetic fixtures, not raid evidence."""
import copy
import json
import sys
import types

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import graph_acceptance as acceptance
from tests.test_development_graph import case, claimed, put, reach, receipt  # noqa: F401

SCENARIO = 'fixture_10n_fixture'
TARGET = 'experiments/configs/raid_targets/' + SCENARIO + '.json'
MANIFEST = 'experiments/configs/cata_raid_encounters/fixture/boss_wcl_dps_reference_v1.json'
BINARY = 'b'*64  # the fixture build adapter's worldserver hash
LATER = '2099-01-01T00:00:0{}Z'


def write(root, path, value):
    (root/path).parent.mkdir(parents=True, exist_ok=True)
    (root/path).write_text(json.dumps(value))
    return graph.digest((root/path).read_bytes())


def kill(n, *, binary=BINARY, recorded=None, counted=True, clear=True):
    return {'kill_id': f'k{n}', 'recorded_at': recorded or LATER.format(n), 'worldserver_sha256': binary,
            'source_commit': 'c'*40, 'evidence_dvc_pointer': 'kill-evidence.json', 'native_clear': clear,
            'counted': counted, 'exclusion_reason': None if counted else 'not a native clear'}


def make_verdict(root, label='batch1', actor1='pass', actor2='pass', overall='pass', encounter=None,
                 ratio=1.02, kills=None, roster=None):
    row = lambda spec, role, status: {'spec': spec, 'role': role, 'n': 3, 'mean_dps': 102.0, 'sd_dps': 1.5,
                                      'target_dps': 100.0, 'ratio': ratio, 'status': status}
    kills = kills or [kill(1), kill(2), kill(3)]
    binaries = {k['worldserver_sha256'] for k in kills if k['counted']}
    return {'schema': 'raid_target_verdict_v1', 'scenario': SCENARIO, 'label': label, 'kills': len(kills),
            'target_path': TARGET, 'target_sha256': graph.digest((root/TARGET).read_bytes()),
            'wcl_manifest_sha256': graph.digest((root/MANIFEST).read_bytes()), 'wcl_timelines_sha256': None,
            'worldserver_sha256': binaries.pop() if len(binaries) == 1 else None,
            'source_commits': ['c'*40], 'kills_detail': kills,
            'first_recorded_at': min(k['recorded_at'] for k in kills), 'last_recorded_at': max(k['recorded_at'] for k in kills),
            'roster': roster or {'expected': ['1', '2'], 'missing': []},
            'actors': {'1': row('blood_death_knight', 'tank', actor1), '2': row('holy_paladin', 'healer', actor2)},
            'encounter': {'n': 3, 'clears': 3, 'mean_party_dps': 900.0, 'mean_duration_sec': 310.0,
                          'boss_window_deaths': 0, 'status': encounter or overall},
            'status': overall, 'reasons': []}


@pytest.fixture
def scoreboard(monkeypatch):
    """Stand-in for tools.raid_program.scoreboard.evaluate_target (owned elsewhere)."""
    batches = {}
    module = types.ModuleType('tools.raid_program.scoreboard')
    module.evaluate_target = lambda root, scenario, label=None: copy.deepcopy(batches[label])
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', module)
    return batches


@pytest.fixture
def assessing(case, scoreboard):
    """A class_native unit for actor_1 and the encounter, validated with scoreboard batch 'batch1'."""
    root, state, evidence = case
    write(root, MANIFEST, {'references': ['wcl']})
    write(root, TARGET, {'schema': 'raid_target_v1', 'scenario': SCENARIO, 'wcl_reference_manifest': MANIFEST})
    (root/'kill-evidence.json').write_text('{"dvc": "pointer stand-in"}')
    g = state['development_graph']
    g['requirements']['encounter'] = {'status': 'open', 'needs_raid': True, 'needs_performance': True, 'needs_all_actors': True}
    g['unit']['requirements'] = ['setup', 'actor_1', 'encounter']
    root, state, evidence = reach((root, state, evidence), 'validate')
    assert state['development_graph']['claim']['claimed_at']
    scoreboard['batch1'] = make_verdict(root)
    state = graph.reduce(root, state, receipt(root, state, evidence, scoreboard_label='batch1'))
    assert state['development_graph']['run']['scoreboard_label'] == 'batch1'
    return root, state, evidence


def cite(root, verdict, name='verdict.json'):
    return put(root/name, verdict)


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


def publish(root, state, evidence):
    state = claimed(root, state)
    return graph.reduce(root, state, receipt(root, state, evidence))


def test_passing_verdict_accepts_actor_and_encounter_and_pins_inputs(assessing, scoreboard):
    root, state, evidence = assessing
    put(root/graph.STATE_PATH, state)
    written = acceptance.write_verdict(root, 'batch1')
    assert written['acceptable_unit_requirements'] == ['actor_1', 'encounter'] and 'binding_error' not in written
    state = graph.reduce(root, state, assessment(root, state, evidence, written['verdict']))
    assert state['development_graph']['pending_acceptance'] == ['actor_1', 'encounter']
    g = publish(root, state, evidence)['development_graph']
    graph.check_graph(g)
    actor = g['requirements']['actor_1']
    assert actor['status'] == 'accepted' and actor['verdict']['receipt'] == written['verdict']
    assert (actor['verdict']['label'], actor['verdict']['ratio'], actor['verdict']['encounter_status']) == ('batch1', 1.02, 'pass')
    assert actor['verdict']['kill_ids'] == ['k1', 'k2', 'k3'] and actor['verdict']['worldserver_sha256'] == BINARY
    assert actor['verdict']['target_sha256'] == graph.digest((root/TARGET).read_bytes())
    assert actor['verdict']['wcl_manifest_sha256'] == graph.digest((root/MANIFEST).read_bytes())
    assert g['requirements']['encounter']['verdict']['roster'] == {'expected': ['1', '2'], 'missing': []}
    actor['verdict']['encounter_status'] = 'fail'  # defense in depth in the graph check
    with pytest.raises(graph.GraphError, match='verdict is not pass'):
        graph.check_graph(g)


@pytest.mark.parametrize('changes,key,match', [
    ({'actor1': 'fail', 'overall': 'fail'}, 'actor_1', 'verdict is fail'),
    ({'actor1': 'no_reference', 'overall': 'fail'}, 'actor_1', 'reference work, never acceptance'),
    ({'actor1': 'insufficient_kills', 'overall': 'insufficient_kills'}, 'actor_1', 'not pass'),
    ({'overall': 'fail'}, 'encounter', 'verdict is fail'),
    ({'overall': 'fail', 'encounter': 'fail'}, 'actor_1', 'encounter verdict is fail'),
    ({'roster': {'expected': ['1', '2'], 'missing': ['2']}}, 'encounter', 'roster must cover'),
    ({'roster': {'expected': ['1'], 'missing': []}}, 'encounter', 'roster must cover'),
])
def test_non_passing_verdict_keeps_requirement_open(assessing, scoreboard, changes, key, match):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(root, **changes)
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, assessment(root, state, evidence, cite(root, scoreboard['batch1']), accepted_requirements=[key]))


def test_actor_pass_can_close_while_encounter_requirement_stays_open(assessing, scoreboard):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(root, actor2='fail', overall='fail', encounter='pass')
    g = graph.reduce(root, state, assessment(root, state, evidence, cite(root, scoreboard['batch1']),
                                             accepted_requirements=['actor_1']))['development_graph']
    assert g['pending_acceptance'] == ['actor_1'] and g['outcomes']['performance_accepted'] is False


@pytest.mark.parametrize('kills,match', [
    ([kill(1), kill(2, binary='e'*64), kill(3)], "unit's binary"),
    ([kill(1, binary='e'*64), kill(2, binary='e'*64), kill(3, binary='e'*64)], "unit's binary"),
    ([kill(1, recorded='2000-01-01T00:00:00Z'), kill(2), kill(3)], 'before the unit'),
    ([kill(1, counted=False, clear=False)], 'counts no kills'),
])
def test_verdict_kills_must_belong_to_the_units_run(assessing, scoreboard, kills, match):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(root, kills=kills)
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, assessment(root, state, evidence, cite(root, scoreboard['batch1'])))


def test_uncounted_foreign_kill_does_not_block(assessing, scoreboard):
    root, state, evidence = assessing
    scoreboard['batch1'] = make_verdict(root, kills=[kill(1), kill(2), kill(3), kill(4, binary='e'*64, counted=False)])
    graph.reduce(root, state, assessment(root, state, evidence, cite(root, scoreboard['batch1'])))


def test_changed_target_or_wcl_manifest_invalidates_the_verdict(assessing, scoreboard):
    root, state, evidence = assessing
    ref = cite(root, scoreboard['batch1'])
    (root/MANIFEST).write_text('{"references": ["changed"]}')
    with pytest.raises(graph.GraphError, match='wcl_manifest_sha256'):
        graph.reduce(root, state, assessment(root, state, evidence, ref))
    write(root, TARGET, {'schema': 'raid_target_v1', 'scenario': SCENARIO, 'wcl_reference_manifest': MANIFEST, 'edited': 1})
    with pytest.raises(graph.GraphError, match='target_sha256'):
        graph.reduce(root, state, assessment(root, state, evidence, ref))


def test_label_used_by_an_earlier_acceptance_is_rejected(assessing, scoreboard):
    root, state, evidence = assessing
    g = copy.deepcopy(state['development_graph'])
    g['requirements']['actor_2'].update(status='accepted', verdict={'label': 'batch1', 'status': 'pass'})
    with pytest.raises(graph.GraphError, match='already accepted actor_2'):
        acceptance.verify_verdict(root, g, cite(root, scoreboard['batch1']))


def test_verdict_that_changes_before_publication_is_rejected(assessing, scoreboard):
    root, state, evidence = assessing
    state = graph.reduce(root, state, assessment(root, state, evidence, cite(root, scoreboard['batch1'])))
    scoreboard['batch1']['kills_detail'].append(kill(4))  # a kill appended to the label after assessment
    with pytest.raises(graph.GraphError, match='differs from the scoreboard recomputation'):
        publish(root, state, evidence)


@pytest.mark.parametrize('mutate,match', [
    (lambda v: v.update(label='batch0'), 'scoreboard_label'),
    (lambda v: v.update(scenario='other_10n_boss'), 'scenario differs'),
    (lambda v: v['actors']['1'].update(ratio=1.5), 'differs from the scoreboard recomputation'),
])
def test_verdict_must_be_this_runs_fresh_batch(assessing, scoreboard, mutate, match):
    root, state, evidence = assessing
    cited = copy.deepcopy(scoreboard['batch1'])
    mutate(cited)
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, assessment(root, state, evidence, cite(root, cited)))


def test_run_without_label_cannot_use_a_verdict(case, scoreboard):
    root, state, evidence = case
    state['development_graph']['unit']['requirements'] = ['actor_1']
    root, state, evidence = reach((root, state, evidence), 'assess')
    with pytest.raises(graph.GraphError, match='scoreboard_label'):
        graph.reduce(root, state, assessment(root, state, evidence, put(root/'verdict.json', {'schema': 'raid_target_verdict_v1',
            'scenario': SCENARIO, 'label': 'batch1'}), accepted_requirements=['actor_1']))


def test_verdict_path_rejects_manual_performance_and_unattributable_runs(assessing, scoreboard):
    root, state, evidence = assessing
    ref = cite(root, scoreboard['batch1'])
    with pytest.raises(graph.GraphError, match='omit performance_accepted'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, performance_accepted=True))
    state['development_graph']['run']['terminal_reason'] = 'infrastructure_loss'
    with pytest.raises(graph.GraphError, match='unattributable'):
        graph.reduce(root, state, assessment(root, state, evidence, ref, encounter_clear=False, accepted_requirements=['actor_1']))


def test_missing_scoreboard_is_an_error_not_acceptance(assessing, monkeypatch):
    root, state, evidence = assessing
    ref = cite(root, make_verdict(root))
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', None)
    with pytest.raises(graph.GraphError, match='scoreboard unavailable'):
        graph.reduce(root, state, assessment(root, state, evidence, ref))


def test_verdict_does_not_close_other_requirements_without_repair(assessing, scoreboard):
    root, state, evidence = assessing
    ref = cite(root, scoreboard['batch1'])
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
    write(root, TARGET, {'schema': 'raid_target_v1', 'scenario': SCENARIO})
    result = graph.reduce(root, state, receipt(root, state, evidence, accepted_requirements=['raid_target']))
    assert result['development_graph']['pending_acceptance'] == ['raid_target']


def validating(case, scoreboard):
    root, state, evidence = case
    write(root, MANIFEST, {'references': ['wcl']})
    write(root, TARGET, {'schema': 'raid_target_v1', 'scenario': SCENARIO, 'wcl_reference_manifest': MANIFEST})
    (root/'kill-evidence.json').write_text('{"dvc": "pointer stand-in"}')
    root, state, evidence = reach((root, state, evidence), 'validate')
    put(root/graph.STATE_PATH, state)
    return root, state


def test_run_receipt_command_writes_a_receipt_the_graph_accepts(case, scoreboard):
    root, state = validating(case, scoreboard)
    scoreboard['batch1'] = make_verdict(root)
    with pytest.raises(graph.GraphError, match='cleanup-verified'):
        acceptance.write_run_receipt(root, 'batch1', producer='coordinator', cleanup_verified=False)
    result = acceptance.write_run_receipt(root, 'batch1', producer='coordinator', cleanup_verified=True)
    assert result['dry_run'] == {'from_stage': 'validate', 'to_stage': 'assess'} and result['kills'] == 3
    written = graph.read(root/result['receipt']['path'])
    assert written['scoreboard_label'] == 'batch1' and written['kill_ids'] == ['k1', 'k2', 'k3']
    assert written['evidence'][0]['path'] == 'kill-evidence.json' and written['operation_id'] == state['development_graph']['claim']['operation_id']
    from tools.raid_program.completed_operation import completed_runs
    assert completed_runs(root, state['development_graph']) == [result['receipt']]  # discoverable before release/rework


@pytest.mark.parametrize('kills,match', [
    ([kill(1, binary='e'*64)], "unit's binary"),
    ([kill(1, recorded='2000-01-01T00:00:00Z')], 'before this validation claim'),
    ([kill(1), kill(2, clear=False, counted=False)], '--terminal-reason'),
])
def test_run_receipt_command_refuses_other_batches(case, scoreboard, kills, match):
    root, state = validating(case, scoreboard)
    scoreboard['batch1'] = make_verdict(root, kills=kills)
    with pytest.raises(graph.GraphError, match=match):
        acceptance.write_run_receipt(root, 'batch1', producer='coordinator', cleanup_verified=True)


def test_finish_line_and_print_only_verdict(assessing, scoreboard):
    root, state, evidence = assessing
    put(root/graph.STATE_PATH, state)
    finish = acceptance.finish_line(root, state['development_graph'])
    assert finish['scenario'] == SCENARIO and finish['target_present'] is True
    assert finish['open_actor_requirements'] == ['actor_1', 'actor_2'] and finish['open_encounter_requirements'] == ['encounter']
    shown = acceptance.write_verdict(root, 'batch1', write=False)
    assert 'verdict' not in shown and shown['actors']['1']['ratio'] == 1.02
    assert not (root/acceptance.VERDICT_DIR).exists()
