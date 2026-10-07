"""Later disposable pets require their immutable successful Tame outcome."""
from copy import deepcopy
import pytest
from tools.client_compatibility.hunter_disposable_tame import disposable_number,pair_preserved
from tools.client_compatibility.world.tests.test_successful_tame_boundary import pet_state


def data():
    source,rows=pet_state();rows[0]['CreatedBySpell']=883;rows[1]['renamed']=0
    source['retained_pet_after']=deepcopy(rows)
    source.update(completed=True,failure=None,finished_at=100,phase='owned_tame_native_outcome_captured',
        input_sent=True,capture_disarmed=True,qualification_added=False,runtime={'worldserver':{'pid':1}},
        actor={'guid':6,'account_id':2,'class':3,'level':10},capture_checks=dict.fromkeys(range(14),True))
    return source,rows,{'pid':1}


def test_disposable_number_is_bound_to_the_actual_tame_and_complete_named_pet():
    source,rows,native=data();rows[1]['savetime']=21
    assert disposable_number(source,rows,native)==8
    assert pair_preserved(source['retained_pet_after'],rows)


def native_data():
    source,rows,previous=data();native={'pid':2}
    d={'schema':'client442_stopped_native_tame_deployment_v1','completed':True,'installed':True,
        'finished_at':110,'native_restarted':True,'bridge_unchanged':True,'native_before':previous,'native':native,
        'installation_checks':dict.fromkeys(range(9),True),'offline_baselines':{'6':{'pets':deepcopy(rows)}}}
    return source,rows,native,d


def test_stopped_native_restart_keeps_the_exact_tame_owned_disposable_identity():
    assert disposable_number(*native_data())==8


@pytest.mark.parametrize('fault',['unverified','unfinished','not_installed','restart','bridge','old_native','native','check','pets'])
def test_native_restart_does_not_relax_pet_provenance(fault):
    s,rows,n,d=native_data()
    if fault=='unverified':d['schema']='other'
    elif fault=='unfinished':d['completed']=False
    elif fault=='not_installed':d['installed']=False
    elif fault=='restart':d['native_restarted']=False
    elif fault=='bridge':d['bridge_unchanged']=False
    elif fault=='old_native':d['native_before']={}
    elif fault=='native':d['native']={}
    elif fault=='check':d['installation_checks'][0]=False
    else:d['offline_baselines']['6']['pets']=[]
    with pytest.raises(RuntimeError):disposable_number(s,rows,n,d)


@pytest.mark.parametrize('fault',['failed','unfinished','changed_native','wrong_actor','wrong_class','check',
    'missing_check','replayed','armed','qualification','number','named_active','named_name','named_health',
    'new_owner','new_entry','new_creation_spell','new_slot','extra_pet','missing_pet'])
def test_unattributed_or_mutated_pet_cannot_become_disposable(fault):
    source,rows,native=data()
    if fault=='failed':source['completed']=False
    elif fault=='unfinished':source['finished_at']=None
    elif fault=='changed_native':native={'pid':2}
    elif fault=='wrong_actor':source['actor']['guid']=7
    elif fault=='wrong_class':source['actor']['class']=9
    elif fault=='check':source['capture_checks'][0]=False
    elif fault=='missing_check':source['capture_checks'].pop(0)
    elif fault=='replayed':source['input_sent']=False
    elif fault=='armed':source['capture_disarmed']=False
    elif fault=='qualification':source['qualification_added']=True
    elif fault=='number':source['native_pet_after']['fields']['69']=6
    elif fault=='named_active':rows[0]['active']=1
    elif fault=='named_name':rows[0]['name']='Wolf'
    elif fault=='named_health':rows[0]['curhealth']=1
    elif fault=='new_owner':rows[1]['owner']=7
    elif fault=='new_entry':rows[1]['entry']=42717
    elif fault=='new_creation_spell':rows[1]['CreatedBySpell']=883
    elif fault=='new_slot':rows[1]['slot']=5
    elif fault=='extra_pet':rows.append({'id':9})
    else:rows.pop()
    with pytest.raises(RuntimeError):disposable_number(source,rows,native)
