"""Pure provenance checks for a fresh Tame with the primary client stopped."""
import time
from .scout_relaunch_lineage import deployment_runtime,SINGLE_SCHEMA


DEPLOYMENT_SCHEMA='client442_resource_paused_scout_deployment_v1'


def successful_chain(old,runtime,episodes,refs,stop,deployment,primary_ref,relaunch=None):
    counts={'entry':('checks',9),'stored':('checks',15),'stage':('stage_checks',13),
        'cast':('capture_checks',14),'restore':(None,8),'park':('checks',4),'finish':('checks',5)}
    for name,(key,count) in counts.items():
        row=episodes[name]
        checks=row.get(key,{}) if key else row.get('pose_restoration',{}).get('checks',{})
        if len(checks)!=count or not all(v is True for v in checks.values()):
            raise RuntimeError('whole fresh Tame source checks differ')
    phases={'entry':'owned_class_entered','stored':'owned_existing_stored_pet_boundary',
        'stage':'owned_existing_wolf_staged','refresh':'await_owned_tame_cast_review',
        'cast':'owned_tame_native_outcome_captured','restore':'owned_tame_pose_restored',
        'park':'await_original_selection_review'}
    hunter=old.get('class_actor',{});origin=old.get('origin_actor',{})
    if (old.get('runtime')!=runtime or origin.get('guid')!=2 or
        tuple(hunter.get(k) for k in ('guid','account_id','class','level','character_name'))!=(6,2,3,10,'Harnesshunt')):
        raise RuntimeError('fresh Tame fixture identity differs')
    previous=old['finished_at']
    for name,row in episodes.items():
        if (row.get('completed') is not True or row.get('failure') is not None or
            row.get('runtime')!=runtime or row.get('fixture_source')!=refs['preparation'] or
            row.get('actor')!=(origin if name=='finish' else hunter) or
            not previous<row.get('started_at',0)<row.get('finished_at',0) or
            (name in phases and row.get('phase')!=phases[name])):
            raise RuntimeError('fresh Tame same-runtime ordered source chain differs')
        previous=row['finished_at']
    for name,key,target in (('stored','entry_source','entry'),('stage','entry_source','entry'),
        ('stage','stored_source','stored'),('refresh','staging_source','stage'),
        ('cast','staging_source','stage'),('restore','stage_source','stage')):
        if episodes[name].get(key)!=refs[target]:raise RuntimeError('fresh Tame dependency differs')
    cast=episodes['cast']
    if (cast.get('input_sent') is not True or cast.get('capture_disarmed') is not True or
        cast.get('qualification_added') is not False or episodes['refresh'].get('input_sent') is not False or
        episodes['stored'].get('pet_command_sent') is not False):
        raise RuntimeError('fresh Tame input/capture boundary differs')
    deployed=deployment_runtime(relaunch,runtime,deployment)
    native=deployment.get('schema')=='client442_stopped_native_tame_deployment_v1'
    if (stop.get('phase')!='user_requested_primary_client_stopped' or
        len(stop.get('checks',{}))!=8 or not all(v is True for v in stop['checks'].values()) or
        stop.get('before')!=stop.get('after') or deployment.get('schema') not in (DEPLOYMENT_SCHEMA,SINGLE_SCHEMA,'client442_stopped_native_tame_deployment_v1') or
        deployment.get('completed') is not True or not deployment.get('finished_at') or
        deployment.get('primary_stop_source')!=primary_ref or
        deployment.get('native')!=runtime['worldserver'] or deployment.get('after')!=runtime['modern_world'] or
        deployment.get('scout_lifetime')!=(runtime['client'] if relaunch and 'pause' in relaunch else deployed['client']) or
        (deployment.get('schema')==DEPLOYMENT_SCHEMA and not relaunch and deployment.get('before')!=stop['runtime']['modern_world']) or
        (native_primary(deployment) if native else deployment.get('native'))!=stop['runtime']['worldserver'] or
        set(deployment.get('parked_reconnect_attempt',{}))!={'scout'} or
        deployment['parked_reconnect_attempt']['scout'].get('completed') is not True):
        raise RuntimeError('fresh Tame stopped-primary deployment lineage differs')


def native_primary(deployment):
    from .stopped_native_ancestry import primary_native
    return primary_native(deployment)


def saved_pet_preserved(before,after):
    return (set(before)==set(after) and 0<before.get('savetime',0)<=after.get('savetime',0)<=time.time() and
        {**before,'savetime':after['savetime']}==after)


def retained_tame_pets(cast,current):
    baseline=cast.get('baseline_pets',[]);captured=cast.get('retained_pet_after',[])
    native=cast.get('native_pet_after',{}).get('fields',{});number=native.get('69')
    if (len(baseline)!=1 or len(captured)!=2 or len(current)!=2 or type(number) is not int or number<=4 or
        baseline[0].get('id')!=4 or {r.get('id') for r in current}!={4,number} or
        {r.get('id') for r in captured}!={4,number}):return False
    named=next(r for r in current if r['id']==4);new=next(r for r in current if r['id']==number)
    captured_new=next(r for r in captured if r['id']==number)
    return (saved_pet_preserved(baseline[0],named) and saved_pet_preserved(captured_new,new) and
        tuple(named.get(k) for k in ('owner','entry','name','renamed','slot','active'))==
            (6,42717,'Harnesswolf',1,5,0) and
        tuple(new.get(k) for k in ('owner','entry','name','CreatedBySpell','slot','active','level','modelid'))==
            (6,299,'Wolf',13481,0,1,10,18156) and
        (native.get('5'),native.get('18'),native.get('48'),native.get('61'))==(299,6,10,18156))
