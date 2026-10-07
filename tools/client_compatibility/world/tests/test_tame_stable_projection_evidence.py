"""Reject stale public caches and missing, duplicate or foreign wire delivery."""
from copy import deepcopy
import pytest
from tools.client_compatibility.tame_stable_projection import prove,stable_update
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_tame_pet_added_stable import SOURCE,owned,baseline,cast,go,add


def source(codec):
    packet=owned(codec,[baseline(),cast(),go(),add()],deepcopy(SOURCE['pet_after']))[-1]
    e={'native_pet_after':SOURCE['pet_after'],'native_session':'owned','finished_at':101,
        'capture_packets':[{'name':'SMSG_PET_ADDED','direction':'from_native','body':SOURCE['body'],
            'session':'owned','time':100}],
        'cast_packets':[{'name':packet[0],'body':packet[1],'direction':'to_client','session':'owned','time':100.1}]}
    stored={'slot':6,'name':'Harnesswolf','level':10,'display_id':903}
    new={'slot':1,'name':'Wolf','level':10,'display_id':18156}
    before={'visible':False,'interacting':False,'stable_slots':16,'pets':[stored]}
    after={**before,'pets':[stored,new]}
    return deepcopy((e,before,after))


def test_native_candidate_packet_and_passive_cache_agree(codec):
    e,b,a=source(codec);p=prove(e,b,a)
    assert p['modern_stable_update']==e['cast_packets'][0] and p['pets'][1][1]==10
    assert stable_update(e['cast_packets'][0]['body'])==(p['pets'],(0,0),16)


@pytest.mark.parametrize('fault',['missing','duplicate','foreign','early','truncated','old_cache',
    'level9','wrong_model','lost_named','invented_before','npc_open','capacity','missing_added','foreign_added',
    'foreign_added_session'])
def test_projection_cannot_admit_incomplete_or_unattributed_delivery(codec,fault):
    e,b,a=source(codec)
    if fault=='missing':e['cast_packets']=[]
    elif fault=='duplicate':e['cast_packets']*=2
    elif fault=='foreign':e['cast_packets'][0]['session']='foreign'
    elif fault=='early':e['cast_packets'][0]['time']=99
    elif fault=='truncated':e['cast_packets'][0]['body']='00'
    elif fault=='old_cache':a['pets'].pop()
    elif fault=='level9':a['pets'][1]['level']=9
    elif fault=='wrong_model':a['pets'][1]['display_id']=903
    elif fault=='lost_named':a['pets'].pop(0)
    elif fault=='invented_before':b['pets']=[]
    elif fault=='npc_open':a['visible']=True
    elif fault=='capacity':a['stable_slots']=200
    elif fault=='missing_added':e['capture_packets']=[]
    elif fault=='foreign_added_session':e['capture_packets'][0]['session']='foreign'
    else:e['capture_packets'][0]['body']=SOURCE['body'][:26]+'0b000000'+SOURCE['body'][34:]
    with pytest.raises(ValueError):prove(e,b,a)
