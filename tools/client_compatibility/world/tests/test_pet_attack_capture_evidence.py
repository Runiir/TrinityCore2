"""Foreign controls and stale, dead or different targets cannot authorize an Attack click."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility.pet_attack_capture_evidence import button,target_checks,target_guid
from tools.client_compatibility.world.objects import INDEX

F=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())


def probe():
    p=copy.deepcopy(F['baseline_public_probe']);p['modified_click']=False
    next(r for r in p['actions'] if r['slot']==1)['usable']=True
    return p


def test_observed_owned_stock_attack_geometry_can_be_used_with_unmodified_usable_input():
    row,point=button(probe(),F['native_pet_create'])
    assert row['slot']==1 and all(type(v) is int for v in point)
    assert 0<=point[0]<1280 and 0<=point[1]<720


@pytest.mark.parametrize('fault',['owner','pet','modified','unknown_modifier','unusable','unknown_usability',
    'missing','duplicate','wrong_slot','not_token','not_available','wrong_button','hidden','disabled','fractional','outside'])
def test_wrong_unusable_hidden_or_ambiguous_attack_control_refuses_input(fault):
    p=probe();row=next(r for r in p['actions'] if r['slot']==1)
    if fault=='owner':p['owner_guid']='Player-1-00000004'
    elif fault=='pet':p['pet_guid']='Pet-foreign'
    elif fault=='modified':p['modified_click']=True
    elif fault=='unknown_modifier':p.pop('modified_click')
    elif fault=='unusable':row['usable']=False
    elif fault=='unknown_usability':row.pop('usable')
    elif fault=='missing':p['actions'].remove(row)
    elif fault=='duplicate':p['actions'].append(copy.deepcopy(row))
    elif fault=='wrong_slot':row['slot']=2
    elif fault=='not_token':row['is_token']=False
    elif fault=='not_available':row['available']=False
    elif fault=='wrong_button':row['frame']['button']='PetActionButton3'
    elif fault=='hidden':row['frame']['visible']=False
    elif fault=='disabled':row['frame']['enabled']=False
    elif fault=='fractional':row['frame']['x']=1.5
    else:row['frame']['y']=65535
    with pytest.raises(RuntimeError):button(p,F['native_pet_create'])


def selected():
    guid=0xf130000000000000 | 44548<<32 | 279984
    target={'guid':guid,'kind':3,'map':0,'fields':{INDEX['UNIT_FIELD_HEALTH']:100,INDEX['UNIT_FIELD_MAXHEALTH']:100}}
    owner={INDEX['UNIT_FIELD_TARGET']:guid&0xffffffff,INDEX['UNIT_FIELD_TARGET']+1:guid>>32}
    state={'target':{'guid':target_guid(target),'name':'Training Dummy','visible':True,'health':100,'max_health':100}}
    return target,state,owner


def test_selected_living_fixture_must_match_native_identity_public_visibility_and_health():
    target,state,owner=selected();assert all(target_checks(target,state,owner).values())


@pytest.mark.parametrize('fault',['absent','wrong_spawn','wrong_entry','wrong_kind','wrong_map','dead',
    'missing_health','native_selection','public_selection','wrong_name','hidden','public_health','public_max_health'])
def test_stale_dead_foreign_or_mismatched_targets_do_not_authorize_attack(fault):
    target,state,owner=selected()
    if fault=='absent':target=None
    elif fault=='wrong_spawn':target['guid']+=1
    elif fault=='wrong_entry':target['guid']+=1<<32
    elif fault=='wrong_kind':target['kind']=4
    elif fault=='wrong_map':target['map']=1
    elif fault=='dead':target['fields'][INDEX['UNIT_FIELD_HEALTH']]=0
    elif fault=='missing_health':target['fields'].pop(INDEX['UNIT_FIELD_HEALTH'])
    elif fault=='native_selection':owner[INDEX['UNIT_FIELD_TARGET']]=0
    elif fault=='public_selection':state['target']['guid']='Creature-foreign'
    elif fault=='wrong_name':state['target']['name']='Another Dummy'
    elif fault=='hidden':state['target']['visible']=False
    elif fault=='public_health':state['target']['health']=99
    else:state['target']['max_health']=99
    assert not all(target_checks(target,state,owner).values())
