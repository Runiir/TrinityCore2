"""A new client may inherit the stored pet only through the exact saved deployment."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_hunter_stored_tame_boundary import ancestor


def data():
    before={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    runtime={'worldserver':before['worldserver'],'modern_world':{'pid':4},'client':{'pid':5}}
    base={'6':{'native':{'online':0},'saved':{'health':209},'pets':[{'id':4,'slot':5}]}}
    ref={'path':'deployment.json','sha256':'deployed'};previous={'runtime':before,'all_offline_snapshot':base}
    old={'sources':[ref],'natural_native':base['6']['native'],'natural_saved':base['6']['saved'],
        'retained_class_pets':base['6']['pets']}
    d={'schema':'client442_resource_paused_scout_deployment_v1','completed':True,'native':before['worldserver'],
        'before':before['modern_world'],'previous_scout':before['client'],'after':runtime['modern_world'],
        'scout_lifetime':runtime['client'],'offline_baselines':base}
    return previous,old,runtime,d,ref


def test_whole_deployment_preserves_the_exact_stored_pet_ancestor():ancestor(*data())


@pytest.mark.parametrize('fault',['native','bridge','client','old_bridge','old_client','snapshot','source',
    'character','saved','pets','incomplete','schema'])
def test_unbound_changed_or_different_lifetime_cannot_inherit_the_ancestor(fault):
    p,o,r,d,ref=deepcopy(data())
    if fault in ('native','bridge','client'):
        r={**r,{'native':'worldserver','bridge':'modern_world','client':'client'}[fault]:{'pid':99}}
    elif fault=='old_bridge':d['before']={'pid':99}
    elif fault=='old_client':d['previous_scout']={'pid':99}
    elif fault=='snapshot':d['offline_baselines']={}
    elif fault=='source':o['sources']=[]
    elif fault=='character':o['natural_native']={}
    elif fault=='saved':o['natural_saved']={}
    elif fault=='pets':o['retained_class_pets']=[]
    elif fault=='incomplete':d['completed']=False
    else:d['schema']='other'
    with pytest.raises(RuntimeError):ancestor(p,o,r,d,ref)
