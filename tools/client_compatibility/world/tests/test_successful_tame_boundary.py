"""A stopped primary cannot be replaced by a fabricated two-client Tame closure."""
from copy import deepcopy
import pytest
from tools.client_compatibility.hunter_tame_boundary import (
    DEPLOYMENT_SCHEMA,successful_chain,retained_tame_pets)


def chain():
    runtime={'worldserver':{'pid':1},'modern_world':{'pid':3},'client':{'pid':4}}
    old={'runtime':runtime,'origin_actor':{'guid':2},'class_actor':{
        'guid':6,'account_id':2,'class':3,'level':10,'character_name':'Harnesshunt'},'finished_at':1}
    names=('entry','stored','stage','refresh','cast','restore','park','finish')
    refs={name:{'path':name+'/episode.json','sha256':name} for name in ('preparation',*names)}
    phases=('owned_class_entered','owned_existing_stored_pet_boundary','owned_existing_wolf_staged',
        'await_owned_tame_cast_review','owned_tame_native_outcome_captured','owned_tame_pose_restored',
        'await_original_selection_review',None)
    rows={name:{'runtime':runtime,'actor':old['origin_actor' if name=='finish' else 'class_actor'],
        'fixture_source':refs['preparation'],'completed':True,'failure':None,'phase':phases[i],
        'started_at':2*i+2,'finished_at':2*i+3} for i,name in enumerate(names)}
    for name,key,count in (('entry','checks',9),('stored','checks',15),('stage','stage_checks',13),
        ('cast','capture_checks',14),('park','checks',4),('finish','checks',5)):
        rows[name][key]=dict.fromkeys(range(count),True)
    rows['restore']['pose_restoration']={'checks':dict.fromkeys(range(8),True)}
    for name,key,target in (('stored','entry_source','entry'),('stage','entry_source','entry'),
        ('stage','stored_source','stored'),('refresh','staging_source','stage'),
        ('cast','staging_source','stage'),('restore','stage_source','stage')):rows[name][key]=refs[target]
    rows['stored']['pet_command_sent']=False;rows['refresh']['input_sent']=False
    rows['cast'].update(input_sent=True,capture_disarmed=True,qualification_added=False)
    stop={'phase':'user_requested_primary_client_stopped','checks':dict.fromkeys(range(8),True),
        'before':{'offline':True},'after':{'offline':True},
        'runtime':{'worldserver':runtime['worldserver'],'modern_world':{'pid':2}}}
    primary_ref={'path':'primary/episode.json','sha256':'primary'}
    deployment={'schema':DEPLOYMENT_SCHEMA,'completed':True,'finished_at':.5,
        'primary_stop_source':primary_ref,'native':runtime['worldserver'],
        'before':stop['runtime']['modern_world'],'after':runtime['modern_world'],
        'scout_lifetime':runtime['client'],'parked_reconnect_attempt':{'scout':{'completed':True}}}
    return old,runtime,rows,refs,stop,deployment,primary_ref


def test_fresh_tame_chain_keeps_primary_stopped():successful_chain(*chain())


@pytest.mark.parametrize('fault',['missing_check','failed_cast','failed_pose','missing_finish','wrong_actor',
    'wrong_native','wrong_bridge','wrong_client','wrong_source','wrong_stage','bad_order','replayed_refresh',
    'extra_pet_command','armed_capture','qualification','wrong_stop','changed_primary','bad_deployment',
    'unbound_stop','native_restart','bridge_mismatch','client_mismatch','fake_primary_reconnect','failed_reconnect'])
def test_incomplete_unbound_or_replayed_tame_cannot_close(fault):
    old,runtime,rows,refs,stop,d,primary_ref=deepcopy(chain())
    if fault=='missing_check':rows['stored']['checks'].pop(0)
    elif fault=='failed_cast':rows['cast']['completed']=False
    elif fault=='failed_pose':rows['restore']['pose_restoration']['checks'][0]=False
    elif fault=='missing_finish':rows['finish']['finished_at']=None
    elif fault=='wrong_actor':rows['park']['actor']={'guid':2}
    elif fault in ('wrong_native','wrong_bridge','wrong_client'):
        key={'wrong_native':'worldserver','wrong_bridge':'modern_world','wrong_client':'client'}[fault]
        rows['cast']['runtime']={**runtime,key:{'pid':99}}
    elif fault=='wrong_source':rows['cast']['fixture_source']={}
    elif fault=='wrong_stage':rows['cast']['staging_source']=refs['stored']
    elif fault=='bad_order':rows['park']['started_at']=rows['cast']['started_at']
    elif fault=='replayed_refresh':rows['refresh']['input_sent']=True
    elif fault=='extra_pet_command':rows['stored']['pet_command_sent']=True
    elif fault=='armed_capture':rows['cast']['capture_disarmed']=False
    elif fault=='qualification':rows['cast']['qualification_added']=True
    elif fault=='wrong_stop':stop['checks'][0]=False
    elif fault=='changed_primary':stop['after']={}
    elif fault=='bad_deployment':d['completed']=False
    elif fault=='unbound_stop':d['primary_stop_source']={}
    elif fault=='native_restart':d['native']={'pid':99}
    elif fault=='bridge_mismatch':d['after']={'pid':99}
    elif fault=='client_mismatch':d['scout_lifetime']={'pid':99}
    elif fault=='fake_primary_reconnect':d['parked_reconnect_attempt']['primary']={'completed':True}
    else:d['parked_reconnect_attempt']['scout']['completed']=False
    with pytest.raises((RuntimeError,TypeError)):successful_chain(old,runtime,rows,refs,stop,d,primary_ref)


def pet_state(number=8):
    named={'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'slot':5,
        'active':0,'savetime':10,'curhealth':278,'abdata':'preserved'}
    new={'id':number,'owner':6,'entry':299,'name':'Wolf','CreatedBySpell':13481,'slot':0,
        'active':1,'level':10,'modelid':18156,'savetime':20,'curhealth':278}
    cast={'baseline_pets':[named],'retained_pet_after':[named,new],
        'native_pet_after':{'fields':{'69':number,'5':299,'18':6,'48':10,'61':18156}}}
    return cast,deepcopy([named,new])


@pytest.mark.parametrize('number',[5,8,13])
def test_new_pet_identity_comes_from_the_actual_native_outcome(number):
    cast,current=pet_state(number);current[1]['savetime']=21
    assert retained_tame_pets(cast,current)


@pytest.mark.parametrize('fault',['old_pet','extra_pet','missing_named','name','slot','health','actions',
    'clock','future_clock','new_owner','new_entry','new_level','new_model','number','native_owner'])
def test_tame_closure_preserves_every_named_pet_field_and_exact_new_identity(fault):
    cast,current=pet_state()
    if fault=='old_pet':current[1]['id']=6
    elif fault=='extra_pet':current.append({'id':9})
    elif fault=='missing_named':current.pop(0)
    elif fault=='name':current[0]['name']='Wolf'
    elif fault=='slot':current[0]['slot']=0
    elif fault=='health':current[0]['curhealth']=1
    elif fault=='actions':current[0]['abdata']='changed'
    elif fault=='clock':current[0]['savetime']=9
    elif fault=='future_clock':current[1]['savetime']=10**12
    elif fault=='new_owner':current[1]['owner']=7
    elif fault=='new_entry':current[1]['entry']=42717
    elif fault=='new_level':current[1]['level']=1
    elif fault=='new_model':current[1]['modelid']=903
    elif fault=='number':cast['native_pet_after']['fields']['69']=6
    else:cast['native_pet_after']['fields']['18']=7
    assert not retained_tame_pets(cast,current)
