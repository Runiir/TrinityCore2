"""Close a normal disposable-pet Abandon Cancel with original actors offline."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import prepared,character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .hunter_pair_identity import identities
from .interaction_hunter_stable_slots import bound
from .interaction_primary_combat_reentry import retained


def close(t,preparation,entry,stage,cancel,park,finish,primary_stop):
    old=prepared(t,preparation,True)
    paths=(entry,stage,cancel,park,finish,primary_stop);e,s,c,p,f,stop=[closed(v) for v in paths]
    for v,key,n in ((e,'checks',9),(s,'checks',11),(c,'checks',12),(p,'checks',4),(f,'checks',5),(stop,'checks',8)):
        if len(v.get(key,{}))!=n or not all(v[key].values()):raise RuntimeError('whole Abandon Cancel source checks differ')
    if (s.get('phase')!='owned_test_pet_abandon_dialog' or c.get('phase')!='owned_test_pet_abandon_cancelled' or
        c.get('source')!=bound(stage) or any(v.get('fixture_source')!=bound(preparation) for v in (e,s,c,p,f)) or
        any(v.get('runtime')!=t.receipt['runtime'] for v in (e,s,c,p,f)) or
        any(v.get('actor')!=old['class_actor'] for v in (e,s,c,p)) or f.get('actor')!=old['origin_actor'] or
        not e['finished_at']<s['started_at']<s['finished_at']<c['started_at']<c['finished_at']<p['started_at']<p['finished_at']<f['started_at'] or
        stop.get('phase')!='user_requested_primary_client_stopped' or stop.get('action')!='stop_owned_primary_client' or
        stop.get('actor',{}).get('guid')!=1 or stop.get('input_sent') is not False or stop.get('before')!=stop.get('after') or
        any(stop['runtime'][k]!=t.receipt['runtime'][k] for k in ('worldserver','modern_world'))):
        raise RuntimeError('same-entry Abandon Cancel or exact stopped primary source differs')
    current=pets(6)
    with actor('primary'):
        primary_ok=lab.owned_process('client') is None and retained(1,1)==stop['after']
    checks={**origin_checks(old),**protected(old),
        'hunter_offline':character(6,2)['online']==0,
        'hunter_saved':saved(6)==p['retained_class_saved']==e['entered_saved'],
        'hunter_character':character(6,2)==p['retained_class_fixture'],
        'complete_pair_preserved':identities(c['retained_pet_before'],current),
        'parked_pets_exact':current==p['retained_class_pets'],
        'test_pet_active':any((v['id'],v['slot'],v['active'])==(6,0,1) for v in current),
        'named_pet_stored':any((v['id'],v['slot'],v['active'])==(4,5,0) for v in current),
        'primary_intentionally_stopped':primary_ok,
        'origin_registration':actors.load()==old['origin_actor'],
        'no_probe':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_pet_abandon_probe.json','owned_tame_request_probe.json','owned_stable_request_probe.json'))}
    t.receipt.update(sources=[bound(v) for v in (preparation,*paths)],checks=checks,input_sent=False,
        retained_pets=current,primary_stop_source=bound(primary_stop),frame=shot(t.out/'scout_offline.png'),
        completed=all(checks.values()),phase='owned_abandon_cancel_parked_boundary',qualification_added=False)
    if not all(checks.values()):raise RuntimeError('Abandon Cancel parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','stage','cancel','park','finish','primary-stop','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,a.preparation,a.entry,a.stage,a.cancel,a.park,a.finish,a.primary_stop)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
