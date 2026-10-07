"""Bind the retained Hunter to a completed bridge replacement on the same scout."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import origin_checks,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_single_scout_bridge_deploy import current


def prepare(t,preparation,parked,finish_path,directory):
    old,park,finish=[closed(p) for p in (preparation,parked,finish_path)]
    d=current(t,directory);previous=old['runtime'];now=t.receipt['runtime'];h=d['offline_baselines']['6']
    if (old.get('phase')!='await_owned_class_lobby_review' or old.get('origin_actor')!=t.fixture or
        old.get('class_actor',{}).get('guid')!=6 or old.get('protected_baseline') is None or
        park.get('actor')!=old['class_actor'] or finish.get('actor')!=t.fixture or
        park.get('phase')!='await_original_selection_review' or
        len(park.get('checks',{}))!=4 or not all(park['checks'].values()) or
        len(finish.get('checks',{}))!=5 or not all(finish['checks'].values()) or
        any(e.get('fixture_source')!=bound(preparation) or e.get('runtime')!=previous for e in (park,finish)) or
        not old['finished_at']<park['started_at']<park['finished_at']<finish['started_at']<finish['finished_at']<d['started_at'] or
        previous['worldserver']!=now['worldserver'] or previous['client']!=now['client'] or
        previous['modern_world']!=d['before'] or now['modern_world']!=d['after'] or
        h['native']!=park['retained_class_fixture'] or h['saved']!=park['retained_class_saved'] or
        h['pets']!=park['retained_class_pets'] or d.get('completed') is not True or
        set(d.get('parked_reconnect_attempt',{}))!={'scout'}):
        raise RuntimeError('same-scout retained Hunter source chain differs')
    attempt=d['parked_reconnect_attempt']['scout'];path=Path(attempt['episode'])
    if bound(path)['sha256']!=attempt.get('sha256'):raise RuntimeError('closed scout restoration digest differs')
    restored=closed(path)
    if (restored.get('phase')!='single_scout_bridge_parked_reconnected' or
        restored.get('actor')!=t.fixture or restored.get('runtime')!=now or
        len(restored.get('restoration_checks',{}))!=7 or not all(restored['restoration_checks'].values()) or
        restored.get('all_offline_snapshot')!=d['offline_baselines'] or restored.get('session')!=attempt['session']):
        raise RuntimeError('whole closed single-scout restoration differs')
    checks={**origin_checks(old),**protected(old),'retained_hunter':True,
        'complete_offline_snapshot':True,'primary_stopped':True,'same_scout_restored':True}
    if not all(checks.values()):raise RuntimeError('retained or protected actors differ')
    t.receipt.update(sources=[bound(p) for p in (preparation,parked,finish_path,directory/'deployment.json',path)],
        origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=old['class_actor'],natural_native=h['native'],natural_saved=h['saved'],
        retained_class_pets=h['pets'],protected_baseline=old['protected_baseline'],checks=checks,
        input_sent=False,qualification_added=False,qualified_scope='Retained Hunter continuity across a same-scout bridge replacement.')
    t.persist()
    if actors.register(6)!=old['class_actor']:raise RuntimeError('Hunter registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','finish','deployment','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.finish,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
