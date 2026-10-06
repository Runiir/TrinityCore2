"""Ground input requires an observed current button and closed source-bound reticle."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_pet_moveto_capture import button,source
from tools.client_compatibility.interaction_owned_class_fixture import SCRIPT_BOUNDARY

F=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())


def test_actual_public_move_to_button_has_owned_visible_geometry():
    row,point=button(F['baseline_public_probe'],F['native_pet_create'])
    assert row['name']=='PET_ACTION_MOVE_TO' and row['slot']==3
    assert all(type(v) is int for v in point) and 0<=point[0]<1280 and 0<=point[1]<720


@pytest.mark.parametrize('fault',['owner','pet','missing','duplicate','not_available','not_token','wrong_button',
    'hidden','disabled','fractional_x','outside_y'])
def test_move_to_button_refuses_unowned_hidden_or_invalid_viewport_control(fault):
    probe=copy.deepcopy(F['baseline_public_probe']);row=next(r for r in probe['actions'] if r['slot']==3)
    if fault=='owner':probe['owner_guid']='Player-1-00000004'
    elif fault=='pet':probe['pet_guid']='Pet-foreign'
    elif fault=='missing':probe['actions'].remove(row)
    elif fault=='duplicate':probe['actions'].append(copy.deepcopy(row))
    elif fault=='not_available':row['available']=False
    elif fault=='not_token':row['is_token']=False
    elif fault=='wrong_button':row['frame']['button']='PetActionButton4'
    elif fault=='hidden':row['frame']['visible']=False
    elif fault=='disabled':row['frame']['enabled']=False
    elif fault=='fractional_x':row['frame']['x']=1.5
    else:row['frame']['y']=65535
    with pytest.raises(RuntimeError):button(probe,F['native_pet_create'])


def reticle():
    actor={'guid':5};runtime={'client':{'pid':1},'worldserver':{'pid':2},'modern_world':{'pid':3}}
    t=SimpleNamespace(fixture=actor,receipt={'runtime':runtime})
    d={'actor':copy.deepcopy(actor),'runtime':copy.deepcopy(runtime),'completed':True,'finished_at':1,'failure':None,
        'phase':'await_owned_pet_moveto_ground_review','sources':[{'sha256':'a'},{'sha256':'b'}],
        'qualification_added':False,'custom_script_permission':'blocked_by_user','softTargetInteract':copy.deepcopy(SCRIPT_BOUNDARY),
        'reticle_state':{'spell_targeting':True},'cases':[{'id':'diagnostic.pet_moveto.reticle',
            'status':'owned_pet_moveto_reticle_pass','oracle':{'checks':{str(i):True for i in range(6)}}}]}
    return d,t


def test_exact_closed_reticle_is_eligible_for_separately_reviewed_ground_input():
    d,t=reticle();assert source(d,t,['a','b']) is d


@pytest.mark.parametrize('fault',['unfinished','failed','actor','runtime','phase','sources','qualifies','scripts','cvar',
    'duplicate_case','wrong_case','failed_case','missing_check','false_check','no_reticle'])
def test_ground_source_refuses_open_changed_or_unbound_cursor(fault):
    d,t=reticle()
    if fault=='unfinished':d['finished_at']=None
    elif fault=='failed':d['completed']=False
    elif fault=='actor':d['actor']['guid']=4
    elif fault=='runtime':d['runtime']['client']['pid']=9
    elif fault=='phase':d['phase']='other'
    elif fault=='sources':d['sources'].reverse()
    elif fault=='qualifies':d['qualification_added']=True
    elif fault=='scripts':d['custom_script_permission']='allowed'
    elif fault=='cvar':d['softTargetInteract']['original_restored']=True
    elif fault=='duplicate_case':d['cases'].append(copy.deepcopy(d['cases'][0]))
    elif fault=='wrong_case':d['cases'][0]['id']='other'
    elif fault=='failed_case':d['cases'][0]['status']='client_or_protocol_failure'
    elif fault=='missing_check':d['cases'][0]['oracle']['checks'].pop('0')
    elif fault=='false_check':d['cases'][0]['oracle']['checks']['0']=False
    else:d['reticle_state']['spell_targeting']=False
    with pytest.raises(RuntimeError):source(d,t,['a','b'])
