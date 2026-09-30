"""program refresh-data and the build's data gate, with a fake DVC (never the real remote or repro)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.raid_program import raid_program, raid_program_data as data, raid_program_rounds as rounds
from tools.raid_program.development_graph import GraphError

from tests.test_raid_program_rounds import fake_build, program, sha, world  # noqa: F401 - fixtures by name
from tests.test_runtime_asset_closure_rebind import GEAR, ROUTES, _lock, closure  # noqa: F401

REAL = Path(__file__).resolve().parents[1]
REAL_GATE = data.data_gate  # the world fixture fakes data_gate for build tests; these tests use the real one
STAGES = ['validation_gear', 'validation_provisioning', 'validation_provisioning_verify', 'raid_shard_provisioning',
          'validation_scenarios']
DVC_YAML = {'stages': {
    'world_knowledge': {'cmd': 'x', 'deps': ['tools/world.py'], 'outs': ['dataset/world_knowledge']},
    'world_planner': {'cmd': 'x', 'deps': ['dataset/world_knowledge'], 'outs': ['dataset/world_planner']},
    'quest_reports': {'cmd': 'x', 'deps': ['dataset/world_planner'], 'outs': ['dataset/quest_reports']},
    'validation_gear': {'cmd': 'x', 'deps': ['dataset/world_planner/item_source_index.jsonl', 'configs/prov.json'],
                        'outs': [GEAR]},
    'validation_provisioning': {'cmd': 'x', 'deps': [GEAR, 'configs/prov.json'], 'outs': ['dataset/validation_provisioning']},
    'validation_provisioning_verify': {'cmd': 'x', 'deps': [f'{GEAR}', 'dataset/validation_provisioning'],
                                       'metrics': [{'dataset/validation_provisioning_verification/report.json': {'cache': False}}]},
    'raid_shard_provisioning': {'cmd': 'x', 'deps': [f'{GEAR}/profiles.json', 'dataset/world_knowledge/trainers.jsonl'],
                                'outs': ['dataset/raid_shard_provisioning']},
    'validation_scenarios': {'cmd': 'x', 'deps': ['dataset/validation_provisioning/report.json',
                                                  'dataset/validation_provisioning_verification/report.json',
                                                  'dataset/raid_shard_provisioning'],
                             'outs': [{ROUTES: {'persist': True}}]},
    'unrelated_report': {'cmd': 'x', 'deps': [ROUTES], 'outs': ['dataset/unrelated']},
}}
DOWNSTREAM = {'validation_gear': ['validation_provisioning', 'validation_provisioning_verify', 'raid_shard_provisioning'],
              'validation_provisioning': ['validation_provisioning_verify', 'validation_scenarios'],
              'validation_provisioning_verify': ['validation_scenarios'],
              'raid_shard_provisioning': ['validation_scenarios']}


class FakeDvc:
    """dvc status/repro/push over a stale set; a reproduced stage stales its direct consumers."""

    def __init__(self, root: Path, stale: set[str], fail: str | None = None):
        self.root, self.stale, self.fail, self.calls = root, set(stale), fail, []

    def __call__(self, root: Path, args: list[str], stream: bool = False) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        verb = args[0]
        if verb == 'status':
            detail = {name: [{'changed deps': {'x': 'modified'}}] for name in args[1:-1] if name in self.stale}
            return subprocess.CompletedProcess(args, 0, json.dumps(detail), '')
        if verb == 'repro':
            stage = args[-1]
            if stage == self.fail:
                return subprocess.CompletedProcess(args, 1, '', 'boom')
            self.stale.discard(stage)
            self.stale |= set(DOWNSTREAM.get(stage, []))
            if stage == 'validation_scenarios':  # a new payload: the closure must be rebound
                (self.root / ROUTES / 'validation_routes.jsonl').write_text('{"payload": "reproduced"}\n')
                _lock(self.root, {'validation_scenarios': ROUTES, 'validation_gear': GEAR})
            return subprocess.CompletedProcess(args, 0, '', '')
        return subprocess.CompletedProcess(args, 0, '', '')  # push

    def repros(self) -> list[str]:
        return [call[-1] for call in self.calls if call[0] == 'repro']


@pytest.fixture
def repo(world, closure):
    root = world['root']
    assert root == closure
    (root / 'dvc.yaml').write_text(yaml.safe_dump(DVC_YAML, sort_keys=False))
    return world


def test_raid_stages_are_derived_from_dvc_yaml(repo):
    graph = data.raid_stages(repo['root'])
    assert graph['stages'] == STAGES, 'dependency order; unrelated stages never enter'
    assert graph['boundary'] == ['world_knowledge', 'world_planner'], 'world-database extracts are a reported boundary'
    assert graph['upstream']['validation_scenarios'] == ['raid_shard_provisioning', 'validation_provisioning',
                                                         'validation_provisioning_verify'], 'metrics outputs count'


def test_real_dvc_yaml_closure():
    graph = data.raid_stages(REAL)
    assert graph['stages'] == STAGES and graph['boundary'] == ['world_knowledge', 'world_planner']


def to_review(root: Path) -> None:
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')


def test_refresh_data_reproduces_in_dependency_order_rebinds_and_pushes(repo):
    root = repo['root']
    to_review(root)
    (root / GEAR / 'profiles.json').chmod(0o664)
    dvc = FakeDvc(root, {'validation_gear', 'world_planner'})
    before = sha(root)
    report = data.refresh_data(root, before, dvc)
    assert dvc.repros() == STAGES, 'each stale stage once, upstream first, --single-item'
    assert all(call[:2] == ['repro', '--single-item'] for call in dvc.calls if call[0] == 'repro')
    assert 'world_planner' not in dvc.repros() and report['stale_boundary_stages'] == ['world_planner']
    assert 'world-database' in report['warning']
    assert [call for call in dvc.calls if call[0] == 'push'] == [['push', *STAGES]]
    assert report['modes_fixed'] == [f'{GEAR}/profiles.json'] and (root / GEAR / 'profiles.json').stat().st_mode & 0o777 == 0o644
    assert report['rebind']['written'] and REAL_GATE(root, FakeDvc(root, set()))['closure_bound']
    assert {'dvc.lock', 'experiments/configs/runtime_asset_closure_manifest_v1.json',
            'experiments/configs/runtime_asset_input_closure_manifest_v1.json',
            'artifacts/cata_raid_program/raid_program_state_v1.json'} <= set(report['files_to_commit'])
    assert report['commit'].startswith('git add ')
    row = rounds.current_round(program(root))['data_refreshes'][-1]
    assert row['reproduced'] == STAGES and row['pushed'] and row['stale_boundary_stages'] == ['world_planner']


def test_refresh_data_with_current_data_only_rebinds_and_pushes(repo):
    root = repo['root']
    to_review(root)
    dvc = FakeDvc(root, set())
    report = data.refresh_data(root, None, dvc)
    assert report['reproduced'] == [] and not report['rebind']['changes'] and report['push']['exit_status'] == 0


def test_refresh_data_failures_are_typed(repo):
    root = repo['root']
    with pytest.raises(GraphError, match='not implement or review or build'):
        data.refresh_data(root, None, FakeDvc(root, set()))
    to_review(root)
    with pytest.raises(GraphError, match='changed'):
        data.refresh_data(root, 'f' * 64, FakeDvc(root, set()))
    with pytest.raises(GraphError, match='repro --single-item validation_provisioning failed'):
        data.refresh_data(root, None, FakeDvc(root, {'validation_provisioning'}, fail='validation_provisioning'))
    assert not rounds.current_round(program(root)).get('data_refreshes'), 'nothing is recorded on failure'


def test_data_gate_blocks_stale_stages_and_an_unbound_closure(repo):
    root = repo['root']
    assert REAL_GATE(root, FakeDvc(root, set()))['ok']
    gate = REAL_GATE(root, FakeDvc(root, {'validation_provisioning'}))
    assert not gate['ok'] and gate['stale_stages'] == ['validation_provisioning'] and 'refresh-data' in gate['fix']
    boundary = REAL_GATE(root, FakeDvc(root, {'world_planner'}))
    assert boundary['ok'] and boundary['stale_boundary_stages'] == ['world_planner'] and boundary['warnings']
    (root / ROUTES / 'manifest.json').write_text('{"edited": "without a repro"}\n')
    unbound = REAL_GATE(root, FakeDvc(root, set()))
    assert not unbound['ok'] and 'does not match' in unbound['problems'][0]


def test_data_gate_modes_are_a_warning_and_status_failure_blocks(repo):
    root = repo['root']
    (root / GEAR / 'profiles.json').chmod(0o664)
    gate = REAL_GATE(root, FakeDvc(root, set()))
    assert gate['ok'] and gate['wrong_modes'] == [f'{GEAR}/profiles.json']

    def broken(root, args, stream=False):
        return subprocess.CompletedProcess(args, 255, '', 'ERROR: unexpected error')
    failed = REAL_GATE(root, broken)
    assert not failed['ok'] and 'dvc status unavailable' in failed['problems'][0]


def test_build_refuses_while_raid_data_is_stale(world):
    root = world['root']
    to_review(root)
    world['data_gate'] = {'ok': False, 'problems': ['stale raid DVC stages: validation_scenarios'], 'warnings': []}
    with pytest.raises(GraphError, match='data: stale raid DVC stages: validation_scenarios -> program refresh-data'):
        fake_build(root)
    assert program(root)['stage'] == 'build', 'the review was accepted; only the data gate refused'
    world['data_gate'] = {'ok': True, 'problems': [], 'warnings': []}
    assert fake_build(root)['success']


def test_refresh_data_cli_is_wired(repo, monkeypatch):
    root = repo['root']
    to_review(root)
    fake = FakeDvc(root, set())
    monkeypatch.setattr(data, 'dvc_runner', fake)
    result = raid_program.command(root, ['refresh-data', '--expect', sha(root)])
    assert result['refresh_data']['push']['targets'] == STAGES and result['resume']['stage'] == 'review'
