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
from tools.raid_program.raid_program_inputs import bind_name, discover_program, mode_scoped_research_state, read_json
from tools.raid_program.raid_program_request import raid_alias_index, resolve_raid_request
from tools.raid_program.scenario_catalog import STRATEGIES

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
    assert discovery['e2e']['route_template_scenario_id'] == 'blackwing_descent_10n'
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


def _set_research(repo: Path, name: str, **fields) -> None:
    path = repo / 'experiments/configs/cata_raid_encounters/blackwing_descent' / name
    document = json.loads(path.read_text())
    for key, value in fields.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    path.write_text(json.dumps(document))


HEROIC_ONLY = [{'key': 'heroic_only_claim', 'modes': ['10H', '25H']}]
ACCEPTED_10N = {'10N': 'accepted', '10H': 'fidelity_blocked', '25N': 'fidelity_blocked', '25H': 'fidelity_blocked'}


def _mode_research(repo: Path, mode: str = '10N') -> tuple[str, str | None]:
    unit = next(unit for unit in discover_program(repo, 'blackwing_descent', mode)['units'] if unit['boss_key'] == 'magmaw')
    gate = next((i for i in unit['missing_inputs'] if i['input'] == 'encounter_research'), None)
    return unit['research']['fidelity_state'], gate['detail'] if gate else None


def _synthetic_state(tmp_path: Path, contract: dict | None = None, ledger: dict | None = None,
                     mode: str = '10N') -> tuple[str | None, str | None]:
    """mode_scoped_research_state for a synthetic contract and ledger; None removes a field.

    The baseline is a clean, fully resolved 10N (contract and ledger agree, one heroic-only claim), so
    every refusal below comes from the one field the case changes. No real encounter data is read.
    """
    base = {'fidelity_state_by_mode': ACCEPTED_10N, 'unresolved': HEROIC_ONLY, 'unresolved_material_count': 1}
    documents = {'contract': {'ledger_path': 'synthetic_ledger.json', 'fidelity_state': 'fidelity_blocked', **base},
                 'ledger': dict(base)}
    for name, fields in (('contract', contract), ('ledger', ledger)):
        for key, value in (fields or {}).items():
            if value is None:
                documents[name].pop(key, None)
            else:
                documents[name][key] = value
    (tmp_path / 'synthetic_ledger.json').write_text(json.dumps(documents['ledger']))
    return mode_scoped_research_state(tmp_path, documents['contract'], None, mode)


def test_mode_scoped_research_state_cannot_bypass_unresolved_claims(tmp_path):
    # Coordinator decision: fidelity_state_by_mode[mode] outranks the contract-level state only when
    # neither the contract nor its ledger lists an unresolved material claim covering that mode.
    # Synthetic contract and ledger, so the proof does not depend on any real boss's current claims.
    assert _synthetic_state(tmp_path) == ('accepted', None)  # control: the clean baseline is accepted
    # The bypass: the contract says 10N accepted while its own unresolved claim carries no mode scope.
    state, detail = _synthetic_state(tmp_path, contract={'unresolved': [{'key': 'barrier'}]})
    assert state == 'fidelity_blocked' and 'contract unresolved claim barrier has no mode scope' in detail
    # A claim scoped to 10N blocks 10N.
    state, detail = _synthetic_state(tmp_path, contract={'unresolved': [{'key': 'barrier', 'modes': ['10N', '25N']}]})
    assert state == 'fidelity_blocked' and 'contract unresolved claim barrier covers 10N' in detail
    # A bare-string claim covers every mode.
    state, detail = _synthetic_state(tmp_path, contract={'unresolved': ['barrier']})
    assert state == 'fidelity_blocked' and 'claim barrier has no mode scope' in detail
    # The ledger must agree: a 10N claim there blocks even when the contract is clean.
    state, detail = _synthetic_state(tmp_path, ledger={'unresolved': [{'key': 'static_shock', 'modes': ['10N']}]})
    assert state == 'fidelity_blocked' and 'ledger unresolved claim static_shock covers 10N' in detail
    # So must its per-mode state and its count, and a claim on another mode does not block 10N.
    state, detail = _synthetic_state(tmp_path, ledger={'fidelity_state_by_mode': None})
    assert state == 'fidelity_blocked' and 'ledger fidelity_state_by_mode[10N] is not accepted' in detail
    state, detail = _synthetic_state(tmp_path, ledger={'unresolved_material_count': 2})
    assert state == 'fidelity_blocked' and 'does not reconcile' in detail
    assert _synthetic_state(tmp_path, contract={'unresolved': [{'key': 'other', 'modes': ['25N']}]}) == ('accepted', None)


def test_mode_scoped_research_state_accepts_a_fully_resolved_mode(tmp_path):
    repo = real_copy(tmp_path)
    for name in ('magmaw_v1.json', 'magmaw_ledger_v1.json'):
        _set_research(repo, name, fidelity_state='fidelity_blocked', fidelity_state_by_mode=ACCEPTED_10N,
                      unresolved=HEROIC_ONLY, unresolved_material_count=1)
    assert _mode_research(repo) == ('accepted', None)
    # Other modes keep the contract-level state: the heroic claim and their own by-mode state block them.
    for mode in ('10H', '25N'):
        state, detail = _mode_research(repo, mode)
        assert state == 'fidelity_blocked' and detail
    # Without a per-mode state the contract-level state decides, as before.
    _set_research(repo, 'magmaw_v1.json', fidelity_state_by_mode=None)
    assert _mode_research(repo)[0] == 'fidelity_blocked'


def test_a_refused_mode_override_never_falls_back_to_a_global_accepted(tmp_path):
    # Re-review repro 1: global accepted must not win over an explicit 10N fidelity_blocked.
    repo = real_copy(tmp_path)
    contract, ledger = 'magmaw_v1.json', 'magmaw_ledger_v1.json'
    for name in (contract, ledger):
        _set_research(repo, name, fidelity_state='accepted', unresolved=HEROIC_ONLY, unresolved_material_count=1,
                      fidelity_state_by_mode={**ACCEPTED_10N, '10N': 'fidelity_blocked'})
    state, detail = _mode_research(repo)
    assert state == 'fidelity_blocked' and 'fidelity_state_by_mode[10N] is not accepted' in detail
    # Re-review repro 2: global accepted must not win over an unresolved 10N claim.
    for name in (contract, ledger):
        _set_research(repo, name, fidelity_state_by_mode=ACCEPTED_10N)
    _set_research(repo, contract, unresolved=[{'key': 'barrier', 'modes': ['10N']}])
    state, detail = _mode_research(repo)
    assert state == 'fidelity_blocked' and 'contract unresolved claim barrier covers 10N' in detail
    # A malformed override blocks every mode rather than falling back.
    _set_research(repo, contract, fidelity_state_by_mode=['10N', 'accepted'])
    assert _mode_research(repo)[0] == 'fidelity_blocked'
    # A present null is an authoritative refusal too, not an absent field.
    path = repo / 'experiments/configs/cata_raid_encounters/blackwing_descent' / contract
    document = json.loads(path.read_text())
    document['fidelity_state_by_mode'] = None
    path.write_text(json.dumps(document))
    state, detail = _mode_research(repo)
    assert state == 'fidelity_blocked' and 'not a mode-to-state object' in detail
    # Only a missing override (or one that does not name the mode) falls back to the global state.
    _set_research(repo, contract, fidelity_state_by_mode=None)
    assert _mode_research(repo) == ('accepted', None)
    _set_research(repo, contract, fidelity_state_by_mode={'25H': 'fidelity_blocked'})
    assert _mode_research(repo) == ('accepted', None)


@pytest.mark.parametrize('modes', [['10n'], [None], ['10N ', '25H'], ['ten_normal'], [10], [{'mode': '10N'}], [['10N']],
                                   ['25H', {'mode': '10N'}]])
def test_non_canonical_claim_modes_block_every_mode(tmp_path, modes):
    repo = real_copy(tmp_path)
    for name in ('magmaw_v1.json', 'magmaw_ledger_v1.json'):
        _set_research(repo, name, fidelity_state='fidelity_blocked', fidelity_state_by_mode=ACCEPTED_10N,
                      unresolved=HEROIC_ONLY, unresolved_material_count=1)
    _set_research(repo, 'magmaw_ledger_v1.json', unresolved=[{'key': 'hidden_10n_claim', 'modes': modes}])
    state, detail = _mode_research(repo)
    assert state == 'fidelity_blocked' and 'hidden_10n_claim has non-canonical modes' in detail


def test_real_bwd_contracts_claim_an_accepted_10n_mode_only_when_the_ledger_agrees():
    # A contract may say 10N accepted (after research and user decisions), but only when the per-mode gate
    # agrees: contract and ledger both accepted for 10N, both counts reconcile, no unresolved claim covers
    # 10N. Every contract that does not claim it stays blocked.
    rows = (read_json(REAL, STRATEGIES).get('raids') or {}).get('blackwing_descent', {}).get('bosses') or []
    units = {unit['strategy_slug']: unit for unit in discover_program(REAL, 'blackwing_descent', '10N')['units']}
    assert rows and set(units) == {row['boss_slug'] for row in rows}
    claiming = 0
    for row in rows:
        contract = read_json(REAL, Path(row['contract']))
        ledger = read_json(REAL, Path(contract.get('ledger_path') or row['ledger']))
        assert contract and ledger, row['boss_slug']
        unit = units[row['boss_slug']]
        assert unit['research']['contract'] == row['contract']
        claims = (contract.get('fidelity_state_by_mode') or {}).get('10N') == 'accepted'
        state = mode_scoped_research_state(REAL, contract, row, '10N')
        if not claims:
            assert state[0] != 'accepted', row['boss_slug']
            assert unit['research']['fidelity_state'] != 'accepted', row['boss_slug']
            continue
        claiming += 1
        assert state == ('accepted', None), (row['boss_slug'], state)
        assert unit['research']['fidelity_state'] == 'accepted', row['boss_slug']
        # The same agreement, spelled out rather than trusted from the gate.
        for name, document in (('contract', contract), ('ledger', ledger)):
            claim_list = document['unresolved']
            assert document['fidelity_state_by_mode']['10N'] == 'accepted', (row['boss_slug'], name)
            assert len(claim_list) == document['unresolved_material_count'], (row['boss_slug'], name)
            assert all(isinstance(claim, dict) and claim.get('modes') and '10N' not in claim['modes']
                       for claim in claim_list), (row['boss_slug'], name)
    assert claiming, 'no real BWD contract claims an accepted 10N: the consistency check would be vacuous'


def _full_raid(repo: Path, **overrides) -> dict:
    """Force a full_raid cohort (row and profile included) into the copied data; returns the entry."""
    composition_path = repo / 'experiments/configs/raid_compositions/blackwing_descent_10n.json'
    composition = json.loads(composition_path.read_text())
    cohort = 'blackwing_descent_10n_full_c0'
    full = {'scenario_id': 'blackwing_descent_10n', 'route_scenario_id': cohort, 'cohort_id': cohort,
            'runtime_profile_id': cohort, 'pool_tag': cohort} | overrides
    composition['full_raid'] = full
    composition_path.write_text(json.dumps(composition))
    scenarios_path = repo / 'experiments/configs/validation_scenarios_cata_001.json'
    scenarios = json.loads(scenarios_path.read_text())
    rows = [row for group in ('scenarios', 'diagnostic_scenarios') for row in scenarios.get(group) or []]
    if not any(row['id'] == cohort for row in rows):
        template = next(row for row in rows if row['id'] == 'blackwing_descent_10n')
        scenarios.setdefault('diagnostic_scenarios', []).append(dict(template, id=cohort))
        scenarios_path.write_text(json.dumps(scenarios))
    profiles_path = repo / 'dataset/bot_runtime_profiles/profiles.json'
    profiles = json.loads(profiles_path.read_text())
    if not any(row.get('name') == cohort for row in profiles['profiles']):
        profiles['profiles'].append({'name': cohort, 'pool_tag_filter': cohort})
        profiles_path.write_text(json.dumps(profiles))
    return full


def test_e2e_identity_is_the_full_raid_cohort_row(tmp_path):
    repo = real_copy(tmp_path)
    _full_raid(repo)
    e2e = discover_program(repo, 'blackwing_descent', '10N')['e2e']
    cohort = 'blackwing_descent_10n_full_c0'
    assert (e2e['scenario_id'], e2e['runtime_profile_id'], e2e['pool_tag'], e2e['cohort_id']) == (cohort,) * 4
    assert e2e['route_template_scenario_id'] == 'blackwing_descent_10n'
    assert len(e2e['expected_boss_nodes']) == 6
    assert not [item for item in e2e['missing_inputs'] if item['input'].startswith('e2e_')]


def test_e2e_identity_mismatch_is_a_typed_missing_input(tmp_path):
    repo = real_copy(tmp_path)
    _full_raid(repo, pool_tag='blackwing_descent_10n', scenario_id='other_route')
    e2e = discover_program(repo, 'blackwing_descent', '10N')['e2e']
    names = {item['input'] for item in e2e['missing_inputs']}
    assert {'e2e_identity', 'e2e_route_template'} <= names and not e2e['ready_to_run']


def test_e2e_cohort_row_must_hold_every_composed_boss_node(tmp_path):
    repo = real_copy(tmp_path)
    _full_raid(repo)
    scenarios_path = repo / 'experiments/configs/validation_scenarios_cata_001.json'
    scenarios = json.loads(scenarios_path.read_text())
    for group in ('scenarios', 'diagnostic_scenarios'):
        for row in scenarios.get(group) or []:
            if row['id'] == 'blackwing_descent_10n_full_c0':
                row['route'] = [node for node in row['route'] if node.get('node_id') != 'bwd.nefarian.encounter']
    scenarios_path.write_text(json.dumps(scenarios))
    e2e = discover_program(repo, 'blackwing_descent', '10N')['e2e']
    rows = next(item for item in e2e['missing_inputs'] if item['input'] == 'e2e_route_rows')
    assert 'bwd.nefarian.encounter' in rows['detail']


def test_raid_level_inputs_are_routed_to_owning_packets():
    discovery = discover_program(REAL, 'dragon_soul', '10N')
    owners = {item['input']: item['owner_skill'] for item in discovery['raid_inputs']}
    assert owners['prerequisite_graph_unverified'] == 'raid-shard-architecture'
    assert owners.get('script_readiness_audit', 'raid-encounter-research') == 'raid-encounter-research'


def test_shard_packet_tests_are_existing_modules():
    tests = discover_program(REAL, 'blackwing_descent', '10N')['shard_tests']
    assert tests and all((REAL / path).is_file() for path in tests)
    assert 'tests/test_raid_shard_plan.py' in tests


def test_skills_route_raid_requests_and_carry_the_agents_patch():
    reference = (REAL / '.agents/skills/trinity-orchestrator/references/raid-program.md').read_text()
    routing = reference.split('## AGENTS.md routing (applied by the coordinator)')[1]
    for phrase in ('raid_workloop start', 'resume --program', 'resume --boss', 'one implementation agent per round',
                   'parent_objective_complete', 'bwd'):
        assert phrase in routing
    for phrase in ('program ingest', '--failed-batch', 'e2e --failed', 'build --finish', '--replan', '--output-dir'):
        assert phrase in reference
    shard_skill = (REAL / '.agents/skills/raid-shard-architecture/SKILL.md').read_text()
    assert 'raid_compositions/<raid>_<size><diff>.json' in shard_skill and '<raid>_<size>.json' not in shard_skill
    orchestrator = (REAL / '.agents/skills/trinity-orchestrator/SKILL.md').read_text()
    assert 'references/raid-program.md' in orchestrator
    assert 'program ingest' in (REAL / '.agents/skills/raid-tuning-playbook/SKILL.md').read_text()


def _generated_plan(repo: Path, scenarios: list[str]) -> None:
    composition = json.loads((repo / 'experiments/configs/raid_compositions/blackwing_descent_10n.json').read_text())
    path = repo / 'dataset/raid_shard_provisioning' / composition['composition_id'] / 'plan.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'schema': 'raid_shard_plan_v1', 'shards': [{'scenario_id': s} for s in scenarios]}))


def test_generated_plan_is_a_typed_shards_input(tmp_path):
    repo = real_copy(tmp_path)
    discovery = discover_program(repo, 'blackwing_descent', '10N')
    assert discovery['generated_plan'].endswith('/plan.json')
    item = next(item for item in discovery['raid_inputs'] if item['input'] == 'generated_plan')
    assert item['blocks'] == 'run' and item['owner_skill'] == 'raid-shard-architecture'
    assert all('generated_plan' in unit['raid_run_blockers'] and not unit['ready_to_run'] for unit in discovery['units'])
    cohorts = [unit['scenario_id'] for unit in discovery['units']]
    _full_raid(repo)
    _generated_plan(repo, cohorts[:-1])
    discovery = discover_program(repo, 'blackwing_descent', '10N')
    assert not [item for item in discovery['raid_inputs'] if item['input'] == 'generated_plan']
    last = discovery['units'][-1]
    assert 'generated_plan_cohort' in [item['input'] for item in last['missing_inputs']] and not last['ready_to_run']
    assert 'e2e_generated_plan_cohort' in [item['input'] for item in discovery['e2e']['missing_inputs']]
    _generated_plan(repo, cohorts + ['blackwing_descent_10n_full_c0'])
    discovery = discover_program(repo, 'blackwing_descent', '10N')
    assert not [item for unit in discovery['units'] for item in unit['missing_inputs'] if item['input'] == 'generated_plan_cohort']
    assert 'e2e_generated_plan_cohort' not in [item['input'] for item in discovery['e2e']['missing_inputs']]


def test_reference_requires_tmp_runs_and_names_the_build_time_ownership_check():
    reference = (REAL / '.agents/skills/trinity-orchestrator/references/raid-program.md').read_text()
    assert '--output-dir /tmp/' in reference and 'archive-pending' in reference and 'raid_shard_plan' in reference
    assert 'ownership guarantee' in reference
    from tools.raid_program.raid_program import NEW_RUN_DIR
    assert NEW_RUN_DIR.startswith('/tmp/')
