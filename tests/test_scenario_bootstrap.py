"""Scenario selection is control-plane evidence, not encounter qualification."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import scenario_bootstrap as bootstrap
from tools.raid_program import scenario_catalog as catalog

ROOT = Path(__file__).resolve().parents[1]


def write(root, path, value):
    p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))


@pytest.fixture
def repo(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    bosses=[('magmaw',['10N','10H','25N','25H']),('maloriak',['10N','10H','25N','25H']),('missing_boss',['25H'])]
    rows=[];scripts=[]
    for boss,modes in bosses:
        contract=f'experiments/configs/{boss}.json';ledger=f'experiments/configs/{boss}_ledger.json';dossier=f'docs/{boss}.md'
        rows.append({'boss_slug':boss,'modes':modes,'contract':contract,'ledger':ledger,'dossier':dossier,'fidelity_state':'fidelity_blocked'})
        write(tmp_path,contract,{'fidelity_state':'fidelity_blocked','unresolved_material_count':1,'mode_matrix':{m:{'heroic':m.endswith('H')} for m in modes}})
        write(tmp_path,ledger,{});write(tmp_path,dossier,{})
        scripts.append({'boss':boss,'source':None if boss=='missing_boss' else boss+'.cpp','status':'missing_dedicated_implementation' if boss=='missing_boss' else 'source_present_not_runtime_validated'})
        if boss!='missing_boss':write(tmp_path,Path('src')/(boss+'.cpp'),{})
    write(tmp_path,Path('src/instance.cpp'),{})
    write(tmp_path,catalog.STRATEGIES,{'raids':{'blackwing_descent':{'bosses':rows}}})
    write(tmp_path,catalog.READINESS,{'raids':[{'raid':'blackwing_descent','instance_source':'src/instance.cpp','encounters':scripts}],'source_tree_sha256':'stale'})
    write(tmp_path,catalog.ROSTER,{'slots':[{'slot':f'slot_{i}','class_spec':'fire_mage','role':'ranged_dps'} for i in range(25)]})
    write(tmp_path,catalog.TARGETS,{'targets':[{'spec_target_id':'fire_mage'}]})
    write(tmp_path,catalog.REFERENCES,{'reference_class':'self_provided_baseline','provider_revision':'pinned','requests':[{'target_spec':'fire_mage','request_sha256':'request','source_contract_sha256':'contract'}]})
    shards=[];routes=[]
    for boss in ('magmaw','maloriak'):
        sid=f'blackwing_descent_10n_{boss}_diagnostic'
        shards.append({'boss_key':boss,'scenario_id':sid,'runtime_profile_id':sid,'pool_tag':sid,'bots':[{'pool_tag':sid,'runtime_profile_id':sid,'character_guid':i+30001,'canonical_roster_slot_id':f'raid_{i}','class_spec':'fire_mage','role':'dps'} for i in range(10)]})
        routes.append({'id':sid,'difficulty':'normal_10man','provisioning_scenario_id':sid,'runtime_profile_id':sid,'route':[{'kind':'boss','node_id':f'bwd.{boss}.encounter'}]})
    write(tmp_path,catalog.SHARDS,{'shards':shards});write(tmp_path,catalog.ROUTES,{'diagnostic_scenarios':routes})
    encounter=catalog.resolve(tmp_path,'magmaw 10n')
    state=bootstrap.make_state(tmp_path,encounter,catalog.discover(tmp_path,encounter))
    state['development_graph']['completed_measurements']=[{'spec':'Survival','dps':35394.1167}]
    write(tmp_path,graph.STATE_PATH,state)
    return tmp_path


@pytest.mark.parametrize('requested,mode',[('implement magmaw 25hc bots','25H'),('Magmaw 25-player heroic','25H'),('continue Magmaw 10n bots','10N'),('magmaw 10 heroic','10H')])
def test_resolution(repo,requested,mode):
    assert catalog.resolve(repo,requested)=={'raid':'blackwing_descent','boss':'magmaw','mode':mode}


@pytest.mark.parametrize('requested,mode',[('magmaw',None),('magmaw 25hc','10n'),('magmaw 10n 25hc',None),('unknown 25hc',None),('missing boss 10n',None),('magmaw 20hc',None)])
def test_invalid_request_does_not_change_state(repo,requested,mode):
    before=(repo/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError):bootstrap.start(repo,requested,mode)
    assert (repo/graph.STATE_PATH).read_bytes()==before


def test_25h_uses_frozen_25_not_ten_normal_shard(repo):
    result=bootstrap.start(repo,'implement magmaw 25hc bots')
    assert result['encounter']['mode']=='25H'
    assert len(result['open_requirements'])==34  # 6 setup + damage fidelity + raid_target + 25 actors + encounter
    assert result['completed_measurements']==[]
    inputs=result['bootstrap_inputs']
    assert len(inputs['roster']['actors'])==25
    assert inputs['roster']['source']['path']==str(catalog.ROSTER)
    assert inputs['runtime']['scenario_id'] is None
    assert inputs['runtime']['status']=='missing_exact_runtime_scenario'
    assert inputs['research']['mode_observations']['heroic'] is True
    assert inputs['accepted'] is False and inputs['launch_authorized'] is False
    assert inputs['references']['fire_mage']['request_sha256']=='request'
    assert result['parked_scenarios']==['blackwing_descent:magmaw:10N']


def test_roundtrip_preserves_original_progress_and_does_not_reset_25h(repo):
    original=graph.read(repo/graph.STATE_PATH)
    bootstrap.start(repo,'magmaw 25hc')
    state=graph.read(repo/graph.STATE_PATH)
    state['development_graph']['failures']['a_proven_edge']=2
    write(repo,graph.STATE_PATH,state)
    bootstrap.start(repo,'magmaw 10n')
    returned=graph.read(repo/graph.STATE_PATH);returned.pop('parked_scenarios')
    assert returned==original
    result=bootstrap.start(repo,'magmaw 25hc')
    assert graph.read(repo/graph.STATE_PATH)['development_graph']['failures']['a_proven_edge']==2
    before=(repo/graph.STATE_PATH).read_bytes()
    assert bootstrap.start(repo,'magmaw','25h')['state_sha256']==result['state_sha256']
    assert (repo/graph.STATE_PATH).read_bytes()==before


def test_claimed_scenario_cannot_be_replaced(repo):
    s=graph.resume(repo)
    graph.advance(repo,{'action':'claim','revision':s['revision'],'unit_id':s['unit']['id'],'owner':'other-tab'},s['state_sha256'])
    before=(repo/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError,match='owned or unclosed'):bootstrap.start(repo,'magmaw 25hc')
    assert (repo/graph.STATE_PATH).read_bytes()==before
    # Idempotent same-scenario resume is still allowed and exposes ownership.
    assert bootstrap.start(repo,'magmaw 10n')['claim']['owner']=='other-tab'


def test_preview_and_stale_switch_do_not_mutate(repo):
    old=graph.resume(repo)['state_sha256'];before=(repo/graph.STATE_PATH).read_bytes()
    assert bootstrap.start(repo,'magmaw 25hc',preview=True)['read_only']
    assert (repo/graph.STATE_PATH).read_bytes()==before
    bootstrap.start(repo,'maloriak 10n')
    with pytest.raises(graph.GraphError,match='state changed'):bootstrap.start(repo,'magmaw 25hc',expected_sha256=old)


def test_fresh_process_can_select_then_resume_same_scenario(repo):
    cmd=[sys.executable,'-m','tools.raid_program.raid_workloop','--root',str(repo),'start','implement magmaw 25hc bots']
    first=json.loads(subprocess.check_output(cmd,cwd=ROOT,text=True))
    second=json.loads(subprocess.check_output(cmd,cwd=ROOT,text=True))
    assert first['state_sha256']==second['state_sha256']
    assert first['encounter']['mode']=='25H' and first['revision']==0


def test_missing_script_is_work_not_fake_readiness(repo):
    result=bootstrap.start(repo,'missing boss 25hc')
    assert result['bootstrap_inputs']['script']['task']=='implement_missing_boss_script'
    assert result['unit']['edge']=='missing_native_boss_script'
    assert result['bootstrap_inputs']['launch_authorized'] is False
    assert result['open_requirements']['native_script']['status']=='open'


def test_no_10h_roster_is_borrowed_from_10n(repo):
    result=bootstrap.start(repo,'magmaw 10hc')
    roster=result['bootstrap_inputs']['roster']
    assert roster['status']=='missing_exact_roster_do_not_guess_composition'
    assert roster['source'] is None
    assert all(a['class_spec'] is None for a in roster['actors'])


def test_catalog_change_is_reported_without_replacing_progress(repo):
    bootstrap.start(repo,'magmaw 25hc')
    before=(repo/graph.STATE_PATH).read_bytes()
    with (repo/catalog.REFERENCES).open('a') as stream:stream.write('\n')
    result=bootstrap.start(repo,'magmaw 25hc')
    assert str(catalog.REFERENCES) in result['changed_bootstrap_sources']
    assert (repo/graph.STATE_PATH).read_bytes()==before


def test_invalid_parked_identity_and_wrong_worktree_fail_closed(repo):
    bootstrap.start(repo,'magmaw 25hc');s=graph.read(repo/graph.STATE_PATH)
    s['parked_scenarios']['blackwing_descent:magmaw:10N']['development_graph']['encounter']['mode']='25H'
    write(repo,graph.STATE_PATH,s)
    with pytest.raises(graph.GraphError,match='mixed bootstrap|invalid parked'):bootstrap.start(repo,'magmaw 10n')


def test_real_catalog_selects_requested_mode_and_complete_frozen_roster():
    encounter=catalog.resolve(ROOT,'implement magmaw 25hc bots');inputs=catalog.discover(ROOT,encounter)
    assert len(inputs['roster']['actors'])==25
    assert [a['class_spec'] for a in inputs['roster']['actors']][:2]==['blood_death_knight','protection_paladin']
    assert inputs['research']['mode_observations']['heroic'] is True
    assert inputs['runtime']['scenario_id'] is None
    assert inputs['script']['source_present'] is True


def test_boss_query_reports_selected_program_not_parked_state(repo):
    from tools.raid_program.raid_workloop import active_work_unit_status
    bootstrap.start(repo,'magmaw 25hc')
    assert active_work_unit_status(repo)['mode']=='25H'


def test_mixed_saved_difficulty_roster_is_rejected_even_on_resume(repo):
    bootstrap.start(repo,'magmaw 25hc');state=graph.read(repo/graph.STATE_PATH)
    state['development_graph']['bootstrap_inputs']['encounter']['mode']='10N'
    write(repo,graph.STATE_PATH,state)
    with pytest.raises(graph.GraphError,match='mixed bootstrap'):graph.resume(repo)


@pytest.mark.parametrize('field,value',[('runtime_profile_id','other'),('provisioning_scenario_id','other'),('difficulty','heroic_10man'),('route',[])])
def test_inconsistent_declared_shard_route_rejected(repo,field,value):
    routes=graph.read(repo/catalog.ROUTES);routes['diagnostic_scenarios'][1][field]=value;write(repo,catalog.ROUTES,routes)
    before=(repo/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError,match='route boss'):bootstrap.start(repo,'maloriak 10n')
    assert (repo/graph.STATE_PATH).read_bytes()==before


def test_inconsistent_bot_profile_rejected(repo):
    shards=graph.read(repo/catalog.SHARDS);shards['shards'][1]['bots'][0]['runtime_profile_id']='other';write(repo,catalog.SHARDS,shards)
    with pytest.raises(graph.GraphError,match='bot identity'):bootstrap.start(repo,'maloriak 10n')


def test_real_omnotron_alias_resolves_existing_ten_player_shard():
    encounter=catalog.resolve(ROOT,'omnotron 10n');inputs=catalog.discover(ROOT,encounter)
    assert inputs['roster']['source']['path']==str(catalog.SHARDS)
    assert inputs['runtime']['scenario_id']=='blackwing_descent_10n_omnotron_diagnostic'


def test_current_unit_owner_overrides_legacy_initial_routing(repo):
    from tools.raid_program.raid_workloop import active_work_unit_status
    bootstrap.start(repo,'magmaw 25hc');s=graph.read(repo/graph.STATE_PATH)
    s['development_graph']['unit']['owner_skill']='raid-role-implementation'
    s['owner_skill']='stale_initial_research_owner'
    s['work_unit']='stale_initial_work_unit'
    write(repo,graph.STATE_PATH,s)
    status=active_work_unit_status(repo)
    assert status['owner_skill']=='raid-role-implementation'
    assert status['work_unit']==s['development_graph']['unit']['id']


def test_bootstrap_unit_requires_owner_skill(repo):
    state=graph.read(repo/graph.STATE_PATH)
    del state['development_graph']['unit']['owner_skill']
    with pytest.raises(graph.GraphError,match='owner_skill'):
        graph.check_state(repo,state)


def test_unrequested_wrong_key_parked_state_cannot_duplicate_progress(repo):
    bootstrap.start(repo,'magmaw 25hc');s=graph.read(repo/graph.STATE_PATH)
    s['parked_scenarios']['wrong:key:10N']=s['parked_scenarios'].pop('blackwing_descent:magmaw:10N')
    write(repo,graph.STATE_PATH,s);before=(repo/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError,match='invalid parked'):bootstrap.start(repo,'maloriak 10n')
    with pytest.raises(graph.GraphError,match='invalid parked'):bootstrap.start(repo,'magmaw 25hc')
    assert (repo/graph.STATE_PATH).read_bytes()==before


def test_scenario_switch_invalidates_old_operation_claim(repo):
    old=graph.resume(repo)
    bootstrap.start(repo,'magmaw 25hc')
    with pytest.raises(graph.GraphError,match='state changed'):
        graph.advance(repo,{'action':'claim','revision':old['revision'],'unit_id':old['unit']['id'],'owner':'stale-tab'},old['state_sha256'])


def test_plain_implementation_request_preserves_saved_task_and_coordinator_role(repo):
    saved = graph.read(repo/graph.STATE_PATH)
    saved['development_graph']['unit'].update(
        id='saved-stat-repair', owner_skill='raid-class-mechanics-implementation',
        next_action='Inspect retained effective stats before repeating measurement')
    write(repo, graph.STATE_PATH, saved)
    before = (repo/graph.STATE_PATH).read_bytes()
    cmd = [sys.executable, '-m', 'tools.raid_program.raid_workloop', '--root', str(repo),
           'start', 'implement magmaw 10n bots']
    result = json.loads(subprocess.check_output(cmd, cwd=ROOT, text=True))
    assert result['unit']['id'] == 'saved-stat-repair'
    assert result['coordinator_skill'] == 'trinity-orchestrator'
    assert not result['parent_objective_complete']
    assert result['completed_measurement_count'] == len(saved['development_graph']['completed_measurements'])
    full = json.loads(subprocess.check_output(cmd + ['--full'], cwd=ROOT, text=True))
    assert full['completed_measurements'] == saved['development_graph']['completed_measurements']
    assert (repo/graph.STATE_PATH).read_bytes() == before


def test_new_scenario_points_at_numeric_target_and_missing_file_is_open_work(repo):
    result=bootstrap.start(repo,'implement magmaw 25hc bots')
    path='experiments/configs/raid_targets/blackwing_descent_25h_magmaw.json'
    saved=graph.read(repo/graph.STATE_PATH)['development_graph']
    assert saved['raid_target']=={'scenario':'blackwing_descent_25h_magmaw','path':path}
    assert result['open_requirements']['raid_target']['target_path']==path
    assert 'raid_target' in result['unit']['requirements']
    assert result['finish_line']['target_present'] is False
    assert path in result['next_action'] and result['finish_line']['work_item']
    assert 'scoreboard verdict' in result['open_requirements']['encounter_performance']['description']


def test_existing_target_file_needs_no_target_work_item(repo):
    write(repo,'experiments/configs/raid_targets/blackwing_descent_10h_magmaw.json',{'schema':'raid_target_v1'})
    result=bootstrap.start(repo,'magmaw 10hc')
    assert 'raid_target' not in result['open_requirements']
    assert result['unit']['requirements']==['encounter_research']
    assert result['finish_line']['target_present'] is True and result['finish_line']['work_item'] is None


def write_registry(root, creatures):
    from tools.bot_ml.live_validation_fidelity import REGISTRY_PATH, REGISTRY_SCHEMA
    write(root, REGISTRY_PATH, {'schema': REGISTRY_SCHEMA, 'creatures': creatures})


def test_new_scenario_opens_encounter_damage_fidelity_against_the_registry(repo):
    result = bootstrap.start(repo, 'magmaw 25hc')
    requirement = result['open_requirements']['encounter_damage_fidelity']
    assert requirement['status'] == 'open'
    assert requirement['registry'] == 'experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json'
    assert 'Blizzlike' in requirement['description'] and requirement['registry'] in requirement['description']
    assert requirement['closure_rule'] == 'every boss entry of this scenario is calibrated or not_applicable in the registry'
    # No registry in this scratch repository: nothing to close against.
    assert requirement['registry_boss_entries_at_bootstrap'] == {} and requirement['registry_closable_at_bootstrap'] is False
    assert 'encounter_damage_fidelity' not in result['unit']['requirements']  # the first unit is unchanged


@pytest.mark.parametrize('statuses,closable', [({'1': 'calibrated', '2': 'not_applicable'}, True),
                                               ({'1': 'calibrated', '2': 'open'}, False)])
def test_damage_fidelity_closes_only_when_every_boss_entry_is_settled(repo, statuses, closable):
    from tools.bot_ml.live_validation_fidelity import check_scenario_damage_fidelity
    creatures = {entry: {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '10H', 'role': 'boss', 'status': status}
                 for entry, status in statuses.items()}
    creatures['3'] = {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '10H', 'role': 'add', 'status': 'open'}
    creatures['4'] = {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '25H', 'role': 'boss', 'status': 'open'}
    write_registry(repo, creatures)
    requirement = bootstrap.start(repo, 'magmaw 10hc')['open_requirements']['encounter_damage_fidelity']
    assert requirement['status'] == 'open'  # closing is a publication, never a bootstrap shortcut
    assert requirement['registry_boss_entries_at_bootstrap'] == statuses
    assert requirement['registry_closable_at_bootstrap'] is closable
    encounter = {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '10H'}
    if closable:
        check_scenario_damage_fidelity(repo, encounter)
    else:
        with pytest.raises(ValueError, match='not calibrated or not_applicable: 2'):
            check_scenario_damage_fidelity(repo, encounter)


def test_real_registry_closes_magmaw_10n_fidelity_once_the_heads_are_settled():
    requirement = bootstrap.damage_fidelity_requirement(ROOT, {'raid': 'blackwing_descent', 'boss': 'magmaw', 'mode': '10N'})
    assert requirement['registry_boss_entries_at_bootstrap'] == {'41570': 'calibrated', '42347': 'not_applicable', '48270': 'not_applicable'}
    assert requirement['registry_closable_at_bootstrap'] is True
