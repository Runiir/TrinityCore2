"""Bind the retained Hunter to a closed offline native pet-slot deployment."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed,parking_restored
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_primary_combat_reentry import protected_snapshot
from .interaction_hunter_stable_slots import bound


def continuity(old,park,finish,deployment,current):
    previous=old.get('runtime',{})
    if (old.get('phase')!='await_owned_class_lobby_review' or
        old.get('class_actor',{}).get('guid')!=6 or old.get('origin_actor',{}).get('guid')!=2 or
        park.get('actor')!=old['class_actor'] or finish.get('actor')!=old['origin_actor'] or
        park.get('runtime')!=previous or finish.get('runtime')!=previous or
        park.get('phase')!='await_original_selection_review' or not parking_restored(park) or
        len(finish.get('checks',{}))!=5 or not all(finish['checks'].values())):
        raise RuntimeError('closed native Hunter parking chain differs')
    if (deployment.get('schema')!='client442_offline_native_feedback_deployment_v1' or
        deployment.get('kind')!='pet_slot' or deployment.get('completed') is not True or
        not deployment.get('finished_at') or deployment.get('native_restarted') is not True or
        deployment.get('bridge_unchanged') is not True or deployment.get('config_unchanged') is not True or
        deployment.get('native_before')!=previous.get('worldserver') or
        deployment.get('native')!=current.get('worldserver') or
        previous.get('worldserver')==current.get('worldserver') or
        deployment.get('before')!=previous.get('modern_world') or
        deployment.get('after')!=current.get('modern_world') or
        previous.get('modern_world')!=current.get('modern_world') or
        previous.get('client')!=current.get('client') or
        deployment.get('client_lifetimes',{}).get('scout')!=current.get('client') or
        not deployment.get('parked_primary') or not deployment.get('parked_scout') or
        set(deployment.get('reconnected',{}))!={'primary','scout'} or
        not all(v.get('completed') and v.get('parked') for v in deployment['reconnected'].values())):
        raise RuntimeError('closed native-only pet-slot lifetime continuity differs')


def prepare(t,preparation,parked,origin_finish,deployment_path):
    old,park,finish=[closed(p) for p in (preparation,parked,origin_finish)]
    deployment_path=deployment_path.resolve()
    if (deployment_path.name!='deployment.json' or deployment_path.is_symlink() or
        not deployment_path.is_relative_to(lab.ROOT/'evidence')):
        raise ValueError('requires closed private native deployment')
    d=json.loads(deployment_path.read_text());continuity(old,park,finish,d,t.receipt['runtime'])
    if (t.fixture!=old['origin_actor'] or park.get('fixture_source')!=bound(preparation) or
        finish.get('fixture_source')!=bound(preparation) or protected_snapshot()!=d['protected']):
        raise RuntimeError('native preparation actor, source or saved-state authority differs')
    for name in ('primary','scout'):
        ref=d['parked_reconnect_attempt'][name];path=Path(ref['episode']).resolve();e=closed(path)
        if (not path.is_relative_to(deployment_path.parent) or lab.sha256(path)!=ref['sha256'] or
            e.get('actor',{}).get('actor')!=name or e.get('runtime',{}).get('worldserver')!=d['native'] or
            e.get('runtime',{}).get('modern_world')!=d['after'] or e.get('input_sent') is not False or
            len(e.get('checks',{}))!=7 or not all(e['checks'].values())):
            raise RuntimeError('native deployment final offline restoration differs')
    checks={'original_native':character(2,2)==old['origin_native'],
        'original_saved':saved(2)==old['origin_saved'],'class_offline':park['retained_class_fixture']['online']==0,
        'retained_native':character(6,2)==park['retained_class_fixture'],
        'retained_saved':saved(6)==park['retained_class_saved'],
        'retained_pets':pets(6)==park['retained_class_pets'],
        'installed_binary':lab.sha256(lab.ROOT/'bin/worldserver')==d['binary_sha256'],
        'unchanged_config':lab.sha256(lab.ROOT/'config/worldserver.conf')==d['config_before_sha256']}
    checks.update(protected(old))
    if not all(checks.values()):raise RuntimeError('retained native Hunter saved state differs')
    t.receipt.update(sources=[bound(p) for p in (preparation,parked,origin_finish,deployment_path)],
        origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=old['class_actor'],
        natural_native=park['retained_class_fixture'],natural_saved=park['retained_class_saved'],
        retained_class_pets=park['retained_class_pets'],protected_baseline=old['protected_baseline'],checks=checks,
        qualified_scope='Retained native Hunter continuity only; no gameplay qualification.')
    t.persist()
    if actors.register(6)!=old['class_actor']:raise RuntimeError('retained Hunter registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','origin-finish','deployment','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',
                                                          softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.origin_finish,a.deployment)
        except Exception as e:t.receipt.update(failure=f'{type(e).__name__}: {e}',completed=False)
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase','checks')}),flush=True)
