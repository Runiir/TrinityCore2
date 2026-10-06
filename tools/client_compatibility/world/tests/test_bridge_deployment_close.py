import copy
import pytest
from tools.client_compatibility.interaction_bridge_deployment_close import validate


def data():
    runtime={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    current={'primary':runtime,'scout':{**runtime,'client':{'pid':4}}}
    report={'parked_scout':True,'native_unchanged':True,'native':runtime['worldserver'],
        'after':runtime['modern_world'],'reconnected':{'primary':{'completed':True},'scout':{'completed':True,'parked':True}}}
    episodes={name:{'completed':True,'finished_at':42,'failure':None,
        'actor':{'actor':name,'guid':guid},'runtime':copy.deepcopy(current[name])}
        for name,guid in [('primary',1),('scout',2)]}
    episodes['primary']['bridge_native_restoration']={'checks':dict.fromkeys(range(9),True)}
    episodes['scout']['restoration_checks']=dict.fromkeys(range(5),True)
    return report,episodes,current


def test_verified_both_actor_restorations_close_without_game_input():
    validate(*data())


@pytest.mark.parametrize('change',['already_closed','unfinished','failure','missing_check','failed_check',
    'wrong_actor','wrong_guid','new_client','new_native','new_bridge','scout_in_world','missing_actor'])
def test_unfinished_unbound_or_replaced_actor_cannot_close_deployment(change):
    report,episodes,current=data();e=episodes['primary']
    if change=='already_closed':report['completed']=True
    elif change=='unfinished':e.pop('finished_at')
    elif change=='failure':e['failure']='interrupted'
    elif change=='missing_check':e['bridge_native_restoration']['checks'].pop(0)
    elif change=='failed_check':e['bridge_native_restoration']['checks'][0]=False
    elif change=='wrong_actor':e['actor']['actor']='scout'
    elif change=='wrong_guid':e['actor']['guid']=2
    elif change=='new_client':current['primary']={**current['primary'],'client':{'pid':5}}
    elif change=='new_native':report['native']={'pid':5}
    elif change=='new_bridge':report['after']={'pid':5}
    elif change=='scout_in_world':report['reconnected']['scout']['parked']=False
    else:report['reconnected'].pop('scout')
    with pytest.raises(RuntimeError):validate(report,episodes,current)
