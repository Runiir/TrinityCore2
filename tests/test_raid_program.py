"""Raid-level request resolution and program discovery from the real raid data files."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import raid_program, raid_program_state as store
from tools.raid_program.development_graph import GraphError, STATE_PATH as BOSS_STATE_PATH
from tools.raid_program.queued_build import DEFAULT_POLICY_RELATIVE
from tools.raid_program.raid_program_inputs import bind_name, discover_program
from tools.raid_program.raid_program_request import raid_alias_index, resolve_raid_request

REAL = Path(__file__).resolve().parents[1]
REAL_DATA = [
    'experiments/configs/raid_prerequisites', 'experiments/configs/raid_compositions',
    'experiments/configs/raid_route_compositions', 'experiments/configs/raid_targets',
    'experiments/configs/cata_raid_strategy_catalog_v1.json', 'experiments/configs/cata_raid_script_readiness_v1.json',
    'experiments/configs/validation_scenarios_cata_001.json', 'experiments/configs/cata_raid_encounters/blackwing_descent',
    'experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json',
    'dataset/bot_runtime_profiles/profiles.json', DEFAULT_POLICY_RELATIVE.as_posix(),
]


def real_copy(tmp_path: Path, extra: list[str] = ()) -> Path:
    """A git checkout holding copies of the real raid data (never the real state files)."""
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    for relative in [*REAL_DATA, *extra]:
        source, target = REAL / relative, tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.is_file():
            shutil.copy2(source, target)
    return tmp_path


@pytest.mark.parametrize('request_text,raid,mode', [
    ('implement bwd 10n bots', 'blackwing_descent', '10N'),
    ('implement blackwing descent 10n bots', 'blackwing_descent', '10N'),
    ('implement BWD 25HC bots', 'blackwing_descent', '25H'),
    ('implement bot 10n bots', 'bastion_of_twilight', '10N'),
    ('implement bastion 25n bots', 'bastion_of_twilight', '25N'),
    ('implement the bastion of twilight 10h bots', 'bastion_of_twilight', '10H'),
    ('implement tofw 10n bots', 'throne_of_the_four_winds', '10N'),
    ('implement throne of the four winds 10n bots', 'throne_of_the_four_winds', '10N'),
    ('implement fl 10n bots', 'firelands', '10N'),
    ('implement firelands 25hc bots', 'firelands', '25H'),
    ('implement ds 10n bots', 'dragon_soul', '10N'),
    ('implement dragon soul 10 normal bots', 'dragon_soul', '10N'),
])
def test_raid_aliases_resolve_from_data(request_text, raid, mode):
    assert resolve_raid_request(REAL, request_text) == {'raid': raid, 'mode': mode}


@pytest.mark.parametrize('request_text', ['implement magmaw 10n bots', 'implement omnotron 10n bots',
                                          'implement ragnaros 25hc bots', 'implement hagara 10n bots'])
def test_boss_requests_are_not_raid_requests(request_text):
    assert resolve_raid_request(REAL, request_text) is None


def test_raid_request_needs_a_supported_difficulty():
    with pytest.raises(GraphError, match='missing or conflicting'):
        resolve_raid_request(REAL, 'implement bwd bots')
    with pytest.raises(GraphError, match='unsupported raid difficulty'):
        resolve_raid_request(REAL, 'implement baradin hold 10h bots')
    assert resolve_raid_request(REAL, 'implement bwd bots', mode='10n') == {'raid': 'blackwing_descent', 'mode': '10N'}


def test_aliases_come_only_from_data(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    directory = tmp_path / 'experiments/configs/raid_prerequisites'
    directory.mkdir(parents=True)
    (directory / 'test_keep.json').write_text(json.dumps({
        'raid': 'test_keep', 'name': 'The Silent Keep', 'script_header': 'TSK', 'difficulties': ['10n'],
        'aliases': ['keep of silence']}))
    (directory / 'other_keep.json').write_text(json.dumps({'raid': 'other_keep', 'name': 'Silent Harbor',
                                                           'difficulties': ['10n']}))
    index = raid_alias_index(tmp_path)
    assert index['tsk'] == {'test_keep'} and index['keep of silence'] == {'test_keep'}
    assert index['sk'] == {'test_keep'} and index['sh'] == {'other_keep'}
    assert index['silent'] == {'test_keep', 'other_keep'}  # shared first word is ambiguous
    assert resolve_raid_request(tmp_path, 'implement tsk 10n bots') == {'raid': 'test_keep', 'mode': '10N'}
    with pytest.raises(GraphError, match='ambiguous raid request'):
        resolve_raid_request(tmp_path, 'implement silent 10n bots')
    assert resolve_raid_request(tmp_path, 'implement bwd 10n bots') is None


def test_request_naming_a_raid_and_a_boss_is_refused(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    directory = tmp_path / 'experiments/configs/raid_prerequisites'
    directory.mkdir(parents=True)
    (directory / 'keep.json').write_text(json.dumps({'raid': 'keep', 'name': 'Warden', 'difficulties': ['10n']}))
    strategies = tmp_path / 'experiments/configs/cata_raid_strategy_catalog_v1.json'
    strategies.write_text(json.dumps({'raids': {'keep': {'bosses': [{'boss_slug': 'warden', 'modes': ['10N']}]}}}))
    with pytest.raises(GraphError, match='both a raid and a boss'):
        resolve_raid_request(tmp_path, 'implement warden 10n bots')


def test_strategy_binding_uses_names_not_hardcoded_bosses():
    slugs = ['omnotron_defense_system', 'valiona_and_theralion', 'yorsahj_the_unsleeping', 'magmaw']
    assert bind_name(['omnotron'], slugs) == 'omnotron_defense_system'
    assert bind_name(['theralion_and_valiona'], slugs) == 'valiona_and_theralion'
    assert bind_name(['yorsahj'], slugs) == 'yorsahj_the_unsleeping'
    assert bind_name(['nefarian'], slugs) is None


def test_bwd_program_is_created_from_real_data_files(tmp_path):
    repo = real_copy(tmp_path)
    boss_state = repo / BOSS_STATE_PATH
    boss_state.write_text('{"sentinel": "boss graph bytes"}\n')
    before = boss_state.read_bytes()
    view = raid_program.start_request(repo, 'implement bwd 10n bots')
    assert view['program_id'] == 'blackwing_descent:10N' and view['stage'] == 'plan' and view['round'] == 1
    assert boss_state.read_bytes() == before, 'a raid program must never write the boss-level graph'
    state, _ = store.load(repo)
    program = state['programs']['blackwing_descent:10N']
    assert state['focus'] == 'program' and state['active_program'] == 'blackwing_descent:10N'
    assert list(program['units']) == ['magmaw', 'omnotron', 'chimaeron', 'atramedes', 'maloriak', 'nefarian']
    assert program['units']['maloriak']['cohort_id'] == 'blackwing_descent_10n_maloriak_c0'
    assert program['units']['maloriak']['scenario_id'] == 'blackwing_descent_10n_maloriak_c0_diagnostic'
    assert program['units']['omnotron']['boss_scenario'] == 'blackwing_descent:omnotron_defense_system:10N'
    assert program['e2e']['unit_id'] == 'raid:blackwing_descent:10N:e2e'
    discovery = discover_program(repo, 'blackwing_descent', '10N')
    lockouts = {unit['boss_key']: unit['lockout'] for unit in discovery['units']}
    assert lockouts['magmaw']['fresh_instance'] and lockouts['omnotron']['fresh_instance']
    assert lockouts['maloriak']['precompleted_boss_keys'] == ['magmaw', 'omnotron']
    assert lockouts['maloriak']['diagnostic_only_assistance'] and not lockouts['maloriak']['certifies_predecessors']
    assert lockouts['nefarian']['seed_boss_argument'] == 'magmaw,omnotron,chimaeron,atramedes,maloriak'
    assert all(lockout['seedable'] for lockout in lockouts.values())
    assert discovery['e2e']['scenario_id'] == 'blackwing_descent_10n'
    assert set(discovery['e2e']['boss_nodes']) == set(program['units'])
    for unit in discovery['units']:
        assert all({'input', 'detail', 'owner_skill', 'blocks'} <= set(item) for item in unit['missing_inputs'])
        assert unit['files']['owned'][0].endswith('/Encounters/' + unit['boss_key'].title() + '/**')
    status = raid_program.status(repo)
    assert status['table'][0].startswith('boss | status') and len(status['table']) == 7


def test_selecting_the_same_program_twice_keeps_progress(tmp_path):
    repo = real_copy(tmp_path)
    raid_program.start_request(repo, 'implement bwd 10n bots')
    state, _ = store.load(repo)
    state['programs']['blackwing_descent:10N']['units']['magmaw']['results'].append({'marker': True})
    (repo / store.STATE_PATH).write_text(json.dumps(state))
    again = raid_program.start_request(repo, 'implement blackwing descent 10n bots')
    assert again['program_id'] == 'blackwing_descent:10N'
    reloaded, _ = store.load(repo)
    assert reloaded['programs']['blackwing_descent:10N']['units']['magmaw']['results'] == [{'marker': True}]


def test_preview_is_read_only(tmp_path):
    repo = real_copy(tmp_path)
    view = raid_program.start_request(repo, 'implement bwd 10n bots', preview=True)
    assert view['read_only'] and view['requested_program'] == 'blackwing_descent:10N'
    assert 'bwd' in view['aliases'] and not (repo / store.STATE_PATH).exists()


@pytest.mark.parametrize('raid,mode', [('dragon_soul', '10N'), ('firelands', '25H'),
                                       ('bastion_of_twilight', '10N'), ('throne_of_the_four_winds', '10N')])
def test_other_raids_list_missing_inputs_instead_of_failing(raid, mode):
    discovery = discover_program(REAL, raid, mode)
    assert discovery['units'], 'every boss of the prerequisite DAG becomes a unit'
    raid_inputs = {item['input'] for item in discovery['raid_inputs']}
    assert 'composition' in raid_inputs or discovery['composition']
    assert not discovery['e2e']['ready_to_run']
    for unit in discovery['units']:
        assert unit['cohort_id'].startswith(f"{raid}_{mode.lower()}_") and unit['cohort_id'].endswith('_c0')
        if 'composition' in raid_inputs:
            assert not unit['ready_to_run'] and 'composition' in unit['raid_run_blockers']


def test_heroic_only_bosses_are_excluded_on_normal():
    discovery = discover_program(REAL, 'bastion_of_twilight', '10N')
    assert {'boss_key': 'sinestra', 'reason': 'not available on 10n'} in discovery['excluded_bosses']
    assert 'sinestra' in {unit['boss_key'] for unit in discover_program(REAL, 'bastion_of_twilight', '10H')['units']}


def test_missing_native_scripts_are_run_blocking_work():
    units = {unit['boss_key']: unit for unit in discover_program(REAL, 'dragon_soul', '10N')['units']}
    script = next(item for item in units['morchok']['missing_inputs'] if item['input'] == 'native_script')
    assert script['blocks'] == 'run' and script['owner_skill'] == 'raid-encounter-implementation'
