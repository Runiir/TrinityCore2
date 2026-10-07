"""A failed cache inspection may retain an exact pet without admitting the failure."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_hunter_stored_tame_boundary import prior_named_pet


def data():
    def ref(n):return {'path':n,'sha256':n+'-hash'}
    named={'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'slot':5,'active':0,'savetime':1}
    runtime={'worldserver':1,'modern_world':2,'client':3}
    confirmed={'phase':'owned_disposable_pet_abandoned','checks':dict.fromkeys(range(16),True),
        'retained_pet_before':[named,{'id':10}]}
    abandon={'phase':'owned_abandon_parked_boundary','checks':dict.fromkeys(range(19),True),
        'retained_pets':[named],'sources':[ref('oldprep'),ref('oldentry'),ref('dialog'),ref('confirm')]}
    stored={'phase':'owned_existing_stored_pet_boundary','checks':dict.fromkeys(range(15),True),
        'runtime':runtime,'pet_command_sent':False,'fixture_source':ref('prep'),'entry_source':ref('entry'),
        'baseline_pets':[named],'abandon_source':ref('abandon'),'confirmation_source':ref('confirm')}
    previous={'phase':'owned_tame_precast_parked_boundary','checks':dict.fromkeys(range(20),True),
        'runtime':runtime,'sources':[ref(n) for n in ('prep','entry','stored','failed','park','finish','stop')],
        'all_offline_snapshot':{'6':{'pets':[named]}}}
    docs={'stored':stored,'abandon':abandon,'confirm':confirmed}
    return previous,docs,ref


def call(previous,docs,ref):return prior_named_pet(previous,lambda p:docs[str(p)],lambda p:ref(str(p)))


def test_closed_no_tame_failure_can_preserve_its_exact_earlier_named_pet():
    p,d,r=data();rows,c,ref=call(p,d,r)
    assert rows==d['stored']['baseline_pets'] and c==d['confirm'] and ref==r('confirm')


@pytest.mark.parametrize('fault',['phase','closure_check','closure_size','sources','stored_hash','stored_phase',
    'stored_check','stored_size','runtime','pet_command','preparation','entry','saved_pet','abandon_hash',
    'abandon_phase','abandon_check','abandon_size','abandon_pet','confirmation_ref','confirmation_hash',
    'confirmation_phase','confirmation_check','confirmation_size','named_identity'])
def test_missing_or_changed_transitive_pet_evidence_is_refused(fault):
    p,d,r=deepcopy(data());s=d['stored'];a=d['abandon'];c=d['confirm']
    if fault=='phase':p['phase']='failed_inspection'
    elif fault=='closure_check':p['checks'][0]=False
    elif fault=='closure_size':p['checks'].pop(0)
    elif fault=='sources':p['sources'].pop()
    elif fault=='stored_hash':p['sources'][2]['sha256']='changed'
    elif fault=='stored_phase':s['phase']='other'
    elif fault=='stored_check':s['checks'][0]=False
    elif fault=='stored_size':s['checks'].pop(0)
    elif fault=='runtime':s['runtime']={'client':99}
    elif fault=='pet_command':s['pet_command_sent']=True
    elif fault=='preparation':s['fixture_source']=r('other')
    elif fault=='entry':s['entry_source']=r('other')
    elif fault=='saved_pet':s['baseline_pets']=[]
    elif fault=='abandon_hash':s['abandon_source']['sha256']='changed'
    elif fault=='abandon_phase':a['phase']='other'
    elif fault=='abandon_check':a['checks'][0]=False
    elif fault=='abandon_size':a['checks'].pop(0)
    elif fault=='abandon_pet':a['retained_pets']=[]
    elif fault=='confirmation_ref':s['confirmation_source']=r('other')
    elif fault=='confirmation_hash':
        a['sources'][3]['sha256']='changed';s['confirmation_source']=a['sources'][3]
    elif fault=='confirmation_phase':c['phase']='other'
    elif fault=='confirmation_check':c['checks'][0]=False
    elif fault=='confirmation_size':c['checks'].pop(0)
    else:c['retained_pet_before']=[{**c['retained_pet_before'][0],'name':'Other'},{'id':10}]
    with pytest.raises(RuntimeError):call(p,d,r)
