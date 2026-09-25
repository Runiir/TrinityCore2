"""Boss-level start/resume stay unchanged next to a raid program (CLI level)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import raid_program_state as store
from tools.raid_program import scenario_bootstrap as bootstrap
from tools.raid_program import scenario_catalog as catalog

from tests.test_raid_program import REAL, real_copy

BOSS_INPUTS = ['experiments/configs/cata_raid_roster_25_v1.json', 'experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json',
               'experiments/configs/all_spec_targets_cata_p4_v1.json',
               'experiments/configs/wowsims_cata_dps_reference_requests_v1.json']


def workloop(root: Path, *args: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, '-m', 'tools.raid_program.raid_workloop', '--root', str(root), *args],
                               cwd=REAL, text=True, capture_output=True)
    try:
        return completed.returncode, json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise AssertionError(completed.stdout[-2000:] + completed.stderr[-2000:])


@pytest.fixture
def repo(tmp_path):
    root = real_copy(tmp_path, BOSS_INPUTS)
    encounter = catalog.resolve(root, 'implement magmaw 10n bots')
    state = bootstrap.make_state(root, encounter, catalog.discover(root, encounter))
    path = root / graph.STATE_PATH
    path.write_text(json.dumps(state, indent=2) + '\n')
    return root


def test_boss_resume_is_unchanged_without_a_raid_program(repo):
    before = (repo / graph.STATE_PATH).read_bytes()
    code, output = workloop(repo, 'resume', '--full')
    assert code == 0 and output['encounter'] == {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '10N'}
    assert (repo / graph.STATE_PATH).read_bytes() == before and not (repo / store.STATE_PATH).exists()


def test_raid_start_never_touches_the_boss_graph_and_focus_follows_the_last_start(repo):
    boss_before = (repo / graph.STATE_PATH).read_bytes()
    code, output = workloop(repo, 'start', 'implement bwd 10n bots')
    assert code == 0 and output['schema'] == 'raid_program_resume_v1' and output['stage'] == 'plan'
    assert '--expect ' + output['state_sha256'] in output['commands'][0]
    assert (repo / graph.STATE_PATH).read_bytes() == boss_before
    code, output = workloop(repo, 'resume')
    assert code == 0 and output['program_id'] == 'blackwing_descent:10N'
    code, output = workloop(repo, 'resume', '--boss', '--full')
    assert code == 0 and output['encounter']['boss'] == 'magmaw'
    code, output = workloop(repo, 'start', 'implement magmaw 10n bots', '--full')
    assert code == 0 and output['encounter']['boss'] == 'magmaw' and output['stage'] == 'diagnose'
    assert (repo / graph.STATE_PATH).read_bytes() == boss_before, 'selecting the active boss scenario is a no-op'
    assert json.loads((repo / store.STATE_PATH).read_text())['focus'] == 'boss'
    code, output = workloop(repo, 'resume', '--full')
    assert code == 0 and output['encounter']['boss'] == 'magmaw'
    code, output = workloop(repo, 'resume', '--program')
    assert code == 0 and output['program_id'] == 'blackwing_descent:10N'
    code, output = workloop(repo, 'program', 'status')
    assert code == 0 and output['table'][1].startswith('magmaw | open')


def test_boss_preview_and_program_preview_write_nothing(repo):
    code, output = workloop(repo, 'start', '--preview', 'implement maloriak 10n bots')
    assert code == 0 and output['requested_scenario']['boss'] == 'maloriak'
    code, output = workloop(repo, 'start', '--preview', 'implement bwd 10n bots')
    assert code == 0 and output['read_only'] and output['requested_program'] == 'blackwing_descent:10N'
    assert not (repo / store.STATE_PATH).exists()


def test_errors_keep_the_workloop_error_envelope(repo):
    code, output = workloop(repo, 'start', 'implement bwd bots')
    assert code == 2 and output == {'schema': 'raid_performance_workloop_error_v1',
                                    'error': 'missing or conflicting raid size/difficulty'}
    code, output = workloop(repo, 'resume', '--program')
    assert code == 2 and 'no raid program selected' in output['error']
    code, output = workloop(repo, 'start', 'implement nobody 10n bots')
    assert code == 2 and output['error'].startswith('unknown or ambiguous boss/raid')


def test_program_packet_cli_writes_the_worker_contract(repo, tmp_path_factory):
    workloop(repo, 'start', 'implement bwd 10n bots')
    code, output = workloop(repo, 'program', 'plan')
    assert code == 0 and output['stage'] == 'implement'
    assert set(output['packets']) >= {'boss:magmaw', 'boss:nefarian'}
    target = tmp_path_factory.mktemp('packets') / 'nefarian.json'
    code, packet = workloop(repo, 'program', 'packet', '--id', 'boss:nefarian', '--output', str(target))
    assert code == 0 and json.loads(target.read_text()) == packet
    assert packet['units'][0]['lockout']['seed_boss_argument'] == 'magmaw,omnotron,chimaeron,atramedes,maloriak'
    assert packet['handoff']['save_as'].startswith('artifacts/cata_raid_program/raid_programs/blackwing_descent_10n/round01/')
    assert any(path.endswith('/Encounters/Magmaw/**') for path in packet['forbidden_files'])
