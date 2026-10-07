"""Failed or foreign whole diagnostics cannot become archived stable acceptance."""
from copy import deepcopy
import struct
import pytest
from tools.client_compatibility.review_hunter_stable_checkpoint import packet_proof
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid


def accepted():
    master=(0xf13<<52)|(6749<<32)|205261;identity=list(modern_guid(master,0))
    cfg={'native_master_guid':master,'modern_master_guid':identity,'session':'owned','owner':6,
        'created_at':100,'expires_at':160}
    row={'time':101,'session':'owned','direction':'from_native','name':'MSG_LIST_STABLED_PETS',
        'body':(struct.pack('<QBBiIII',master,1,20,0,4,42717,10)+b'Harnesswolf\0\x01').hex()}
    episode={'completed':True,'failure':None,'finished_at':170,'phase':'hunter_stable_native_open_verified',
        'outcome_checks':{str(i):True for i in range(9)},'restoration_checks':{str(i):True for i in range(13)},
        'protected_checks':{str(i):True for i in range(5)},'capture_config':cfg,'native_session':'owned',
        'actor':{'guid':6,'class':3},'capture_disarmed':True,'capture_packets':[row],
        'baseline_pets':[{'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'modelid':903}],
        'public_stable':{'visible':True,'selected':1,'name':'Harnesswolf','stable_slots':16,
            'pets':[{'slot':1,'name':'Harnesswolf','level':10,'display_id':903}],
            'events':{'PET_STABLE_SHOW':{'count':1}}},
        'cases':[{'id':'pets.stable_open','status':'native_owned_stable_open_pass'}]}
    delivered={'session':'owned','direction':'to_client','name':'SMSG_NPC_INTERACTION_OPEN_RESULT','time':102,
        'body':Writer().guid(*identity).pack('i',22).bits(1,1).finish().hex()}
    return episode,[delivered]


def test_scope_requires_native_catalog_public_cache_and_archived_notification():
    e,p=accepted();proof=packet_proof(e,p)
    assert proof['native_catalogs']==1 and proof['delivered_notifications']==1 and proof['native_capacity']==16
    with pytest.raises(RuntimeError,match='notification'):packet_proof(e,[])


@pytest.mark.parametrize('fault',['failed','phase','restoration','protected','session','body','time','model','master','case'])
def test_failed_or_foreign_stable_evidence_is_excluded(fault):
    e,p=accepted();e=deepcopy(e)
    if fault=='failed':e.update(completed=False,failure='whole failed')
    elif fault=='phase':e['phase']='hunter_stable_request_staged'
    elif fault in ('restoration','protected'):e[fault+'_checks']['0']=False
    elif fault=='session':e['capture_packets'][0]['session']='foreign'
    elif fault=='body':e['capture_packets'][0]['body']+='00'
    elif fault=='time':e['capture_packets'][0]['time']=161
    elif fault=='model':e['public_stable']['pets'][0]['display_id']=2404
    elif fault=='master':e['capture_config']['modern_master_guid'][0]+=1
    elif fault=='case':e['cases'][0]['status']='client_or_protocol_failure'
    with pytest.raises(RuntimeError):packet_proof(e,p)
