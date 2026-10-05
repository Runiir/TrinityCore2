import pytest
from . import farm_graph,combat
from .test_farm_loop import row


def test_graph_blocks_travel_and_survey_with_uncollected_find(tmp_path):
    r=row();r['archaeology']['loot_open']=False;r['minimap_finds']={'clear':True,'confirmed':[]}
    for phase in ('teleport','portal','taxi','flight','survey'):
        with pytest.raises(RuntimeError,match='blocks'):
            farm_graph.transition(tmp_path/'graph.json',phase,r,pending={'site_id':187})
    r['minimap_finds']['clear']=False
    with pytest.raises(RuntimeError,match='blocks travel'):
        farm_graph.transition(tmp_path/'graph.json','flight',r)


def test_graph_remembers_combat_interruption_and_requires_jar_in_bags(tmp_path):
    r=row();r['archaeology']['loot_open']=False;r['minimap_finds']={'clear':True,'confirmed':[]}
    path=tmp_path/'graph.json'
    farm_graph.transition(path,'flight',r)
    farm_graph.transition(path,'combat',r)
    assert farm_graph.transition(path,'combat',r)['resumed_after_repair']
    resumed=farm_graph.transition(path,'observe',r)
    assert resumed['resume_state']=='flight'
    with pytest.raises(RuntimeError,match='item in bags'):farm_graph.transition(path,'jar_found',r)
    r['archaeology']['canopic_jars_in_bags']=1
    farm_graph.transition(path,'jar_found',r)
    with pytest.raises(RuntimeError,match='unsupported'):farm_graph.transition(path,'observe',r)


def test_combat_never_issues_key_one_during_cooldown_or_to_a_dead_target():
    r=row();r['movement']['in_combat']=True;r['farm_ui']['uptime']=10
    r['farm_ui']['combat']={'target_exists':True,'hostile':True,'target_dead':False,
        'attack_usable':True,'attack_in_range':1,'cooldown_ends':10}
    assert combat.ready(r)
    r['archaeology']['mounted']=True
    assert not combat.ready(r)
    r['archaeology']['mounted']=False
    r['farm_ui']['combat']['cooldown_ends']=11
    assert not combat.ready(r)
    r['farm_ui']['combat'].update(cooldown_ends=0,target_dead=True)
    assert not combat.ready(r)


def test_facing_recovery_requires_a_new_error_from_our_current_attack():
    r=row();r['movement']['in_combat']=True;r['farm_ui']['uptime']=10
    r['farm_ui']['combat']={'target_exists':True,'hostile':True,'attack_usable':True,'attack_in_range':True}
    r['farm_ui']['error']={'code':51,'at':9}
    assert not combat.needs_facing(r,None,0)
    assert not combat.needs_facing(r,10,0)
    r['farm_ui']['error']['at']=10
    assert combat.needs_facing(r,10,0)
    assert not combat.needs_facing(r,10,10)
    r['archaeology']['mounted']=True
    assert not combat.needs_facing(r,10,0)
