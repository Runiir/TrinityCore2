"""Resume the retained Hunter across a bound scout pause and bridge deployment."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed,parking_restored
from .interaction_owned_class_fixture import origin_checks,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_paused_scout_bridge_deploy import current,SCHEMA


def continuity(t,old,park,finish,pause,deployment,preparation_sha):
    previous=old.get('runtime',{});now=t.receipt['runtime'];fixture=old.get('class_actor',{})
    if (tuple(fixture.get(k) for k in ('guid','character_name','race','class','level','account_id'))!=
        (6,'Harnesshunt',1,3,10,2) or old.get('phase')!='await_owned_class_lobby_review' or
        old.get('actor')!=t.fixture or old.get('origin_actor')!=t.fixture or t.fixture.get('guid')!=2 or
        park.get('actor')!=fixture or finish.get('actor')!=t.fixture or
        park.get('runtime')!=previous or finish.get('runtime')!=previous or pause.get('runtime')!=previous or
        park.get('phase')!='await_original_selection_review' or not parking_restored(park) or
        any(e.get('fixture_source',{}).get('sha256')!=preparation_sha for e in (park,finish)) or
        len(finish.get('checks',{}))!=5 or not all(finish['checks'].values()) or
        not old['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at']<finish['finished_at']<=pause['started_at'] or
        pause.get('phase')!='parked_scout_resource_paused' or len(pause.get('checks',{}))!=8 or
        not all(pause['checks'].values()) or pause.get('before')!=pause.get('after')):
        raise RuntimeError('retained Hunter pause and original restoration chain differs')
    if (deployment.get('schema')!=SCHEMA or deployment.get('completed') is not True or
        not deployment.get('finished_at') or deployment.get('native_unchanged') is not True or
        deployment.get('primary_stopped') is not True or deployment.get('parked_scout') is not True or
        deployment.get('native')!=previous.get('worldserver') or now.get('worldserver')!=previous.get('worldserver') or
        deployment.get('before')!=previous.get('modern_world') or deployment.get('after')!=now.get('modern_world') or
        now.get('modern_world')==previous.get('modern_world') or
        deployment.get('previous_scout')!=previous.get('client') or deployment.get('scout_lifetime')!=now.get('client') or
        now.get('client')==previous.get('client') or deployment.get('offline_baselines')!=pause.get('after') or
        deployment.get('primary_stop_source')!=pause.get('primary_stop_source') or
        set(deployment.get('parked_reconnect_attempt',{}))!={'scout'} or
        deployment['parked_reconnect_attempt']['scout'].get('completed') is not True):
        raise RuntimeError('completed single-scout deployment lifetime or preservation differs')
    base=pause['after'];hunter=base.get('6',{});origin=base.get('2',{})
    if (hunter.get('native')!=park.get('retained_class_fixture') or hunter.get('saved')!=park.get('retained_class_saved') or
        hunter.get('pets')!=park.get('retained_class_pets') or origin.get('native')!=old.get('origin_native') or
        origin.get('saved')!=old.get('origin_saved')):
        raise RuntimeError('resource pause changed the retained Hunter or original scout')


def prepare(t,preparation,parked,origin_finish,pause_path,directory):
    sources=[preparation,parked,origin_finish,pause_path]
    old,park,finish,pause=[closed(p) for p in sources]
    deployment=current(directory,True);continuity(t,old,park,finish,pause,deployment,lab.sha256(preparation))
    if deployment['source']!=bound(pause_path):raise RuntimeError('single-scout deployment is bound to another pause')
    attempt=deployment['parked_reconnect_attempt']['scout'];path=Path(attempt.get('episode','')).resolve()
    if not path.is_relative_to(directory.parent) or lab.sha256(path)!=attempt.get('sha256'):
        raise RuntimeError('scout restoration digest or owned path differs')
    restored=closed(path)
    if (restored.get('phase')!='single_scout_parked_reconnected' or restored.get('actor')!=t.fixture or
        restored.get('runtime')!=t.receipt['runtime'] or len(restored.get('restoration_checks',{}))!=7 or
        not all(restored['restoration_checks'].values()) or restored.get('all_offline_snapshot')!=pause['after'] or
        restored.get('session')!=attempt.get('session')):
        raise RuntimeError('new scout has no complete bound offline restoration')
    checks=origin_checks(old);checks.update(protected(old));checks.update(
        retained_hunter=True,complete_six_actor_snapshot=True,primary_stopped=True,new_scout_restored=True)
    if not all(checks.values()):raise RuntimeError('original or protected saved state changed')
    sources+=[directory/'deployment.json',path]
    t.receipt.update(sources=[bound(p) for p in sources],origin_actor=old['origin_actor'],
        origin_native=old['origin_native'],origin_saved=old['origin_saved'],origin_roster=old['origin_roster'],
        class_actor=old['class_actor'],natural_native=park['retained_class_fixture'],
        natural_saved=park['retained_class_saved'],retained_class_pets=park['retained_class_pets'],
        protected_baseline=old['protected_baseline'],checks=checks,input_sent=False,qualification_added=False,
        qualified_scope='Retained Hunter continuity across source-bound single-scout relaunch only.')
    t.persist()
    if actors.register(6)!=old['class_actor']:raise RuntimeError('retained Hunter registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','origin-finish','pause','deployment','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.origin_finish,a.pause,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
