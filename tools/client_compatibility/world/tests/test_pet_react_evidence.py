"""Local checkbox changes cannot substitute for real owned native mode readback."""
import copy,struct
import pytest
from tools.client_compatibility.pet_react_evidence import mode_button,info_pairs,readback_checks
from tools.client_compatibility.pet_command_evidence import command_checks
from tools.client_compatibility.interaction_pet_command_probe import expected_guid
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid

PET={'guid':0xf14001a00000001a,'map':0}


def rows():return [{'session':'owned','time':10,'name':'CMSG_REQUEST_PET_INFO','direction':'from_client','body':''},
    {'session':'owned','time':10.1,'name':'CMSG_REQUEST_PET_INFO','direction':'to_native','body':''}]


def values(mode=0):
    p={'owner_guid':'Player-1-00000005','pet_guid':expected_guid(PET),'pet_speed':0,'player_speed':0,
        'actions':[{'slot':i,'name':name,'available':True,'is_token':True,'active':value==mode,
            'frame':{'button':'PetActionButton'+str(i),'available':True,'visible':True,'enabled':True,'x':24575,'y':59440}}
            for i,name,value in [(8,'PET_MODE_ASSIST',3),(9,'PET_MODE_DEFENSIVE',1),(10,'PET_MODE_PASSIVE',0)]]}
    catalog={'guid':PET['guid'],'react':mode,'command':1,'packet':{'direction':'from_native','name':'SMSG_PET_SPELLS'}}
    return catalog,{'probe':p,'ui_clean':True},{'id':2,'owner':5,'entry':416,'Reactstate':mode}


@pytest.mark.parametrize('mode',[0,1,3])
def test_exact_owned_command_and_three_independent_mode_readbacks(mode):
    body=Writer().guid(*modern_guid(PET['guid'],0)).pack('I',6<<23|mode).guid().pack('3f',0,0,0).finish()
    requests=[{'time':1,'direction':'from_client','name':'CMSG_PET_ACTION','body':body.hex()},
        {'time':1.1,'direction':'to_native','name':'CMSG_PET_ACTION',
            'body':struct.pack('<QIQfff',PET['guid'],6<<24|mode,0,0,0,0).hex()}]
    assert all(command_checks(requests,PET,mode,action_type=6).values())
    c,p,s=values(mode);assert all(readback_checks(c,PET,mode,info_pairs(rows(),'owned',9,11),p,s).values())
    button,point=mode_button(p['probe'],mode);assert button['slot']=={0:10,1:9,3:8}[mode] and point==[480,653]


@pytest.mark.parametrize('fault',['foreign_modern','foreign_native','outside','late','body','duplicate','missing'])
def test_info_request_requires_exact_current_window_native_delivery(fault):
    source=rows()
    if fault=='foreign_modern':source[0]['session']='foreign'
    elif fault=='foreign_native':source[1]['session']='foreign'
    elif fault=='outside':source[0]['time']=8
    elif fault=='late':source[1]['time']=12.1
    elif fault=='body':source[0]['body']='01';source[1]['body']='01'
    elif fault=='duplicate':source.append(dict(source[1]))
    else:source.pop()
    c,p,s=values();assert not all(readback_checks(c,PET,0,info_pairs(source,'owned',9,13),p,s).values())


@pytest.mark.parametrize('fault',['no_catalog','foreign_catalog','wrong_native_mode','non_native_catalog',
    'wrong_saved_mode','foreign_saved_owner','foreign_saved_pet','wrong_public_mode','duplicate_public_mode',
    'missing_other_mode','two_active_modes','moving','lua_error'])
def test_local_mode_without_matching_owned_native_saved_and_public_state_is_insufficient(fault):
    c,p,s=copy.deepcopy(values())
    if fault=='no_catalog':c=None
    elif fault=='foreign_catalog':c['guid']+=1
    elif fault=='wrong_native_mode':c['react']=3
    elif fault=='non_native_catalog':c['packet']['direction']='to_client'
    elif fault=='wrong_saved_mode':s['Reactstate']=3
    elif fault=='foreign_saved_owner':s['owner']=4
    elif fault=='foreign_saved_pet':s['id']=1
    elif fault=='wrong_public_mode':p['probe']['actions'][2]['active']=False
    elif fault=='duplicate_public_mode':p['probe']['actions'].append(dict(p['probe']['actions'][2]))
    elif fault=='missing_other_mode':p['probe']['actions'].pop(1)
    elif fault=='two_active_modes':p['probe']['actions'][0]['active']=True
    elif fault=='moving':p['probe']['pet_speed']=8
    else:p['ui_clean']=False
    assert not all(readback_checks(c,PET,0,info_pairs(rows(),'owned',9,11),p,s).values())


@pytest.mark.parametrize('fault',['hidden','disabled','unavailable','outside','wrong_button','wrong_token','duplicate'])
def test_stock_button_requires_unambiguous_visible_enabled_owned_viewport_geometry(fault):
    c,p,s=values();row=p['probe']['actions'][0];frame=row['frame']
    if fault=='hidden':frame['visible']=False
    elif fault=='disabled':frame['enabled']=False
    elif fault=='unavailable':frame['available']=False
    elif fault=='outside':frame['x']=65536
    elif fault=='wrong_button':frame['button']='ActionButton8'
    elif fault=='wrong_token':row['name']='PET_ACTION_ATTACK'
    else:p['probe']['actions'].append(copy.deepcopy(row))
    with pytest.raises(RuntimeError):mode_button(p['probe'],3)
