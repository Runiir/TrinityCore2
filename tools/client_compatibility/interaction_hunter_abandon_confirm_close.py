"""Close disposable Abandon after normal Hunter parking with primary stopped."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import prepared,character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .hunter_abandon_identity import named_preserved
from .interaction_primary_combat_reentry import retained
from .interaction_paused_scout_bridge_deploy import SCHEMA
from .interaction_single_scout_bridge_deploy import SCHEMA as SINGLE_SCHEMA
from .scout_relaunch_lineage import verified_deployment,deployment_runtime
from .interaction_parked_client_resource_pause import snapshot
from .hunter_disposable_tame import disposable_number


def close(t,preparation,entry,stage,confirm,park,finish,primary_stop,deployment,relaunch=None):
    old=prepared(t,preparation,True);paths=(entry,stage,confirm,park,finish,primary_stop)
    e,s,a,p,f,stop=[closed(v) for v in paths];d,lineage=verified_deployment(deployment,t.receipt['runtime'],relaunch)
    single=d.get('schema')==SINGLE_SCHEMA
    native=d.get('schema')=='client442_stopped_native_tame_deployment_v1'
    deployed=deployment_runtime(lineage,t.receipt['runtime'],d)
    number=6
    if a.get('disposable_tame_source'):
        tame=Path(a['disposable_tame_source']['path'])
        if a['disposable_tame_source']!=bound(tame):raise RuntimeError('disposable Tame source changed')
        number=disposable_number(closed(tame),a['retained_pet_before'],t.receipt['runtime']['worldserver'],d if native else None)
        if a.get('disposable_pet_number')!=number:raise RuntimeError('disposable Abandon number differs')
    for v,n in ((e,9),(s,11),(a,16),(p,4),(f,5),(stop,8)):
        if len(v.get('checks',{}))!=n or not all(v['checks'].values()):raise RuntimeError('whole Abandon source checks differ')
    if (a.get('phase')!='owned_disposable_pet_abandoned' or a.get('source')!=bound(stage) or
        s.get('phase')!='owned_test_pet_abandon_dialog' or
        any(v.get('fixture_source')!=bound(preparation) for v in (e,s,a,p,f)) or
        any(v.get('runtime')!=t.receipt['runtime'] for v in (e,s,a,p,f)) or
        any(v.get('actor')!=old['class_actor'] for v in (e,s,a,p)) or f.get('actor')!=old['origin_actor'] or
        not e['finished_at']<s['started_at']<s['finished_at']<a['started_at']<a['finished_at']<p['started_at']<p['finished_at']<f['started_at'] or
        stop.get('phase')!='user_requested_primary_client_stopped' or stop.get('before')!=stop.get('after') or
        d.get('schema') not in (SCHEMA,SINGLE_SCHEMA,'client442_stopped_native_tame_deployment_v1') or not d.get('completed') or not d.get('finished_at') or
        d.get('primary_stop_source')!=bound(primary_stop) or d.get('native')!=t.receipt['runtime']['worldserver'] or
        d.get('after')!=t.receipt['runtime']['modern_world'] or
        d.get('scout_lifetime')!=(t.receipt['runtime']['client'] if lineage and 'pause' in lineage else deployed['client']) or
        (not single and not lineage and d.get('before')!=stop['runtime']['modern_world']) or
        (d.get('native_before') if native else d.get('native'))!=stop['runtime']['worldserver']):
        raise RuntimeError('fresh Abandon, single-scout deployment or stopped primary lineage differs')
    with actor('primary'):primary_ok=lab.owned_process('client') is None and retained(1,1)==stop['after']
    current=pets(6);checks={**origin_checks(old),**protected(old),
        'hunter_offline':character(6,2)['online']==0,'hunter_saved':saved(6)==p['retained_class_saved']==e['entered_saved'],
        'hunter_character':character(6,2)==p['retained_class_fixture'],
        'named_pet_preserved':named_preserved(a['retained_pet_before'],current),
        'parked_pets_exact':current==p['retained_class_pets'],'test_pet_absent':all(r['id']!=number for r in current),
        'primary_intentionally_stopped':primary_ok,'origin_registration':actors.load()==old['origin_actor'],
        'no_probe':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_pet_abandon_probe.json','owned_tame_request_probe.json','owned_stable_request_probe.json')),
        'compiled_bridge':d['after'].get('build')==d['build'],
        'single_scout_reconnected':set(d.get('parked_reconnect_attempt',{}))=={'scout'}}
    t.receipt.update(sources=[bound(v) for v in (preparation,*paths,deployment)],checks=checks,input_sent=False,
        primary_stop_source=bound(primary_stop),retained_pets=current,frame=shot(t.out/'scout_offline.png'),
        completed=all(checks.values()),phase='owned_abandon_parked_boundary',qualification_added=False,
        all_offline_snapshot=snapshot(),disposable_pet_number=number)
    if relaunch:t.receipt['relaunch_source']=bound(relaunch)
    if not all(checks.values()):raise RuntimeError('disposable Abandon parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','stage','confirm','park','finish','primary-stop','deployment','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--relaunch',type=Path)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,a.preparation,a.entry,a.stage,a.confirm,a.park,a.finish,a.primary_stop,a.deployment,a.relaunch)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
