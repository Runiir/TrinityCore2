"""Risk-tier step enforcement; synthetic workflow fixtures, not native or raid evidence."""
import json
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import graph_tiers as tiers
from tests.test_development_graph import case, claimed, put, reach, receipt  # noqa: F401

REPO = Path(__file__).resolve().parents[1]


def commit(root, path, text):
    (root/path).parent.mkdir(parents=True, exist_ok=True)
    (root/path).write_text(text)
    graph.git(root, 'add', path)
    graph.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'edit ' + path)


def step(root, state, evidence, **changes):
    state = claimed(root, state)
    return graph.reduce(root, state, receipt(root, state, evidence, **changes))


def prior_build(root, source=None):
    """A recorded build adapter from an earlier unit, as saved under artifacts/."""
    source = source or graph.git(root, 'rev-parse', 'HEAD')
    policy = put(root/'policy.json', json.loads((REPO/'experiments/configs/cata_raid_build_resource_policy_host12_v1.json').read_text()))
    native = put(root/'prior-native.json', {'commit': source, 'exit_code': 0, 'source_identity_stable': True, 'test_mode': False,
        'output_artifacts': [{'kind': 'worldserver_elf', 'sha256': 'c'*64, 'produced_by_ticket': True}]})
    return put(root/'prior-build.json', {'authority': 'coordinator_attestation', 'kind': 'build', 'unit_id': 'older-unit',
        'producer': 'coordinator', 'evidence': [native], 'source_commit': source, 'binary_sha256': 'c'*64,
        'build_receipt': native, 'policy': policy})


def profile_plan(root, state, evidence, owned, reuse=True):
    """Plan a profile unit owning one committed file, then change and commit it."""
    commit(root, owned, 'v1')
    extra = {'risk_tier': 'profile', 'owned_files': [owned]}
    if reuse:
        extra['reuse_build'] = prior_build(root, graph.git(root, 'rev-parse', 'HEAD~1'))
    state = step(root, state, evidence, **extra)
    commit(root, owned, 'v2')
    return state


def advances(g):
    return [(h['from'], h['to']) for h in g['history'] if h['event']['action'] == 'advance']


def test_profile_unit_needs_only_tests_and_one_measurement(case):
    root, state, evidence = case
    state = profile_plan(root, state, evidence, 'sql/custom/world/rotation.sql')
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['sql/custom/world/rotation.sql']))
    g = state['development_graph']
    assert g['stage'] == 'validate' and g['build_identity']['binary_sha256'] == 'c'*64
    for _ in range(3):  # run, assessment, publication
        state = step(root, state, evidence)
    g = state['development_graph']
    graph.check_graph(g)
    assert advances(g) == [('diagnose', 'implement'), ('implement', 'validate'), ('validate', 'assess'),
                           ('assess', 'publish'), ('publish', 'route')]
    assert g['revision'] == 8 and g['requirements']['setup']['status'] == 'accepted'
    assert {h['risk_tier'] for h in g['history']} == {'profile'}


def test_profile_unit_with_native_diff_is_raised_to_class_native(case):
    root, state, evidence = case
    owned = 'src/server/game/Bots/Profile.cpp'
    state = profile_plan(root, state, evidence, owned)
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, [owned]))
    g = state['development_graph']
    assert g['stage'] == 'review' and tiers.tier_of(g) == 'class_native'
    assert g['tier_raised']['from'] == 'profile' and owned in g['tier_raised']['reason']
    assert 'build_identity' not in g  # no reuse: the raised unit must build
    graph.check_graph(g)
    put(root/graph.STATE_PATH, state)
    shown = graph.resume(root)['tier']
    assert shown['risk_tier'] == 'class_native' and shown['tier_raised'] == g['tier_raised']
    assert shown['remaining_steps'][:3] == ['review', 'build', 'validate']
    for expected in ('build', 'validate'):
        state = step(root, state, evidence, file_hashes=graph.snapshot(root, [owned]))
        assert state['development_graph']['stage'] == expected


def test_profile_builds_without_review_when_native_changed_outside_its_diff(case):
    root, state, evidence = case
    reuse = prior_build(root)
    commit(root, 'src/server/game/Bots/Other.cpp', 'landed by another change')
    commit(root, 'rotation.sql', 'v1')
    state = step(root, state, evidence, risk_tier='profile', owned_files=['rotation.sql'], reuse_build=reuse)
    commit(root, 'rotation.sql', 'v2')
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    g = state['development_graph']
    assert g['stage'] == 'build' and tiers.tier_of(g) == 'profile' and 'tier_raised' not in g
    assert 'native source changed since the reused build' in g['build_reason']
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    assert state['development_graph']['stage'] == 'validate'


def test_profile_without_reusable_build_builds(case):
    root, state, evidence = case
    state = profile_plan(root, state, evidence, 'rotation.sql', reuse=False)
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    assert state['development_graph']['stage'] == 'build'
    assert state['development_graph']['build_reason'] == 'plan has no reuse_build'


def test_queue_receipt_of_binary_on_disk_can_be_reused(case):
    root, state, evidence = case
    queue = put(root/'queue-receipt.json', {'ticket_id': 'raid-build-x', 'commit': graph.git(root, 'rev-parse', 'HEAD'),
        'exit_code': 0, 'source_identity_stable': True, 'test_mode': False,
        'output_artifacts': [{'kind': 'worldserver_elf', 'sha256': 'd'*64, 'produced_by_ticket': True}]})
    commit(root, 'rotation.sql', 'v1')
    state = step(root, state, evidence, risk_tier='profile', owned_files=['rotation.sql'], reuse_build=queue)
    commit(root, 'rotation.sql', 'v2')
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    g = state['development_graph']
    assert g['stage'] == 'validate' and g['build_identity']['binary_sha256'] == 'd'*64


def test_unverifiable_reuse_fails_at_plan_and_falls_back_to_build_later(case, monkeypatch):
    from tools.raid_program import queued_build
    root, state, evidence = case
    reuse = prior_build(root)
    def stale(path, policy, allow_test_mode):
        raise ValueError('current CMake cache hash differs from receipt')
    commit(root, 'rotation.sql', 'v1')
    with monkeypatch.context() as patch:
        patch.setattr(queued_build, 'verify_receipt', stale)
        with pytest.raises(graph.GraphError, match='CMake cache'):
            step(root, state, evidence, risk_tier='profile', owned_files=['rotation.sql'], reuse_build=reuse)
    state = step(root, state, evidence, risk_tier='profile', owned_files=['rotation.sql'], reuse_build=reuse)
    commit(root, 'rotation.sql', 'v2')
    monkeypatch.setattr(queued_build, 'verify_receipt', stale)
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    g = state['development_graph']
    assert g['stage'] == 'build' and 'no longer verifies' in g['build_reason']


def test_reused_build_rejects_source_changed_after_tests(case):
    root, state, evidence = case
    state = profile_plan(root, state, evidence, 'rotation.sql')
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    commit(root, 'rotation.sql', 'v3 untested')
    state = claimed(root, state)
    with pytest.raises(graph.GraphError, match='source changed since recorded'):
        graph.reduce(root, state, receipt(root, state, evidence))


def test_shared_runtime_requires_review_build_and_smoke_kill(case):
    root, state, evidence = case
    state = step(root, state, evidence, risk_tier='shared_runtime')
    for expected in ('review', 'build', 'smoke'):
        state = step(root, state, evidence)
        assert state['development_graph']['stage'] == expected
    state = claimed(root, state)
    with pytest.raises(graph.GraphError, match='observed kill'):
        graph.reduce(root, state, receipt(root, state, evidence, terminal_reason='death_loop'))
    with pytest.raises(graph.GraphError, match='wrong receipt kind'):
        graph.reduce(root, state, receipt(root, state, evidence, kind='run'))
    state = graph.reduce(root, state, receipt(root, state, evidence))
    g = state['development_graph']
    assert g['stage'] == 'validate' and g['smoke']['attempt_id'] == 'smoke1'
    assert advances(g)[-2:] == [('build', 'smoke'), ('smoke', 'validate')]


def test_legacy_unit_keeps_review_and_build_and_legacy_rows_validate(case):
    root, state, evidence = reach(case, 'validate')
    g = state['development_graph']
    assert advances(g) == [('diagnose', 'implement'), ('implement', 'review'), ('review', 'build'), ('build', 'validate')]
    for row in g['history']:
        del row['risk_tier']  # saved history predating tiers
    graph.check_graph(g)


def test_history_cannot_claim_a_skip_its_tier_does_not_allow(case):
    root, state, evidence = case
    state = profile_plan(root, state, evidence, 'rotation.sql')
    state = step(root, state, evidence, file_hashes=graph.snapshot(root, ['rotation.sql']))
    g = state['development_graph']
    g['history'][-1]['risk_tier'] = 'class_native'
    with pytest.raises(graph.GraphError, match='illegal transition'):
        graph.check_graph(g)


def test_stage_outside_tier_is_invalid(case):
    root, state, evidence = reach(case, 'review')
    state['development_graph']['unit']['risk_tier'] = 'profile'
    with pytest.raises(graph.GraphError, match='skipped by the unit risk tier'):
        graph.check_graph(state['development_graph'])


@pytest.mark.parametrize('changes,match', [
    ({'risk_tier': 'tiny'}, 'risk_tier must be one of'),
    ({'reuse_build': None, 'risk_tier': 'class_native'}, None),
])
def test_plan_tier_validation(case, changes, match):
    root, state, evidence = case
    if match:
        with pytest.raises(graph.GraphError, match=match):
            step(root, state, evidence, **changes)
    else:
        assert step(root, state, evidence, **changes)['development_graph']['assignment']['risk_tier'] == 'class_native'


def test_reuse_build_is_only_for_profile(case):
    root, state, evidence = case
    with pytest.raises(graph.GraphError, match='only for profile'):
        step(root, state, evidence, risk_tier='class_native', reuse_build=prior_build(root))


def test_route_validates_and_carries_unit_tier(case):
    root, state, evidence = reach(case, 'publish')
    state = step(root, state, evidence)
    g = state['development_graph']
    event = {'action': 'route', 'revision': g['revision'], 'unit_id': 'u1', 'reason': 'next gap',
             'unit': {'id': 'u2', 'edge': 'rotation', 'requirements': ['actor_1'], 'next_action': 'tune', 'risk_tier': 'bogus'}}
    with pytest.raises(graph.GraphError, match='risk_tier'):
        graph.reduce(root, state, event)
    event['unit']['risk_tier'] = 'profile'
    routed = graph.reduce(root, state, event)
    put(root/graph.STATE_PATH, routed)
    resumed = graph.resume(root)
    assert resumed['tier']['risk_tier'] == 'profile'
    assert 'review' not in resumed['tier']['remaining_steps']
    assert 'build' in resumed['tier']['conditional_steps']
    assert resumed['reusable_build'] == state['development_graph']['receipts']['build']


def test_successors_and_native_paths():
    assert tiers.successors('implement', 'profile') == ('build', 'validate')
    assert tiers.successors('build', 'shared_runtime') == ('smoke',)
    assert tiers.successors('implement', 'class_native') == ('review',)
    assert tiers.native_path('src/server/game/Bots/BotController.cpp') and tiers.native_path('CMakeLists.txt')
    assert not tiers.native_path('sql/custom/world/rotation.sql') and not tiers.native_path('experiments/configs/x.json')
