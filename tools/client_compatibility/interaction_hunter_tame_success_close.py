"""Close a fresh diagnostic Tame after normal parking with the primary stopped."""
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
from .interaction_hunter_tame_stage import NAMES
from .interaction_primary_combat_reentry import retained
from .interaction_parked_client_resource_pause import snapshot
from .hunter_tame_boundary import successful_chain,retained_tame_pets
from .scout_relaunch_lineage import verified_deployment


def close(t,paths,primary_stop,deployment,relaunch=None):
    old=prepared(t,paths['preparation'],True)
    rows={k:closed(p) for k,p in paths.items() if k!='preparation'}
    refs={k:bound(p) for k,p in paths.items()};stop=closed(primary_stop)
    deployment=deployment.resolve()
    if (deployment.name!='deployment.json' or not deployment.is_relative_to(lab.ROOT/'evidence') or
        deployment.is_symlink()):raise ValueError('requires the owned single-scout deployment')
    d,lineage=verified_deployment(deployment,t.receipt['runtime'],relaunch)
    successful_chain(old,t.receipt['runtime'],rows,refs,stop,d,bound(primary_stop),lineage)
    with actor('primary'):
        primary_ok=lab.owned_process('client') is None and retained(1,1)==stop['after']
    current=pets(6);park=rows['park'];all_offline=snapshot()
    checks={**origin_checks(old),**protected(old),
        'hunter_offline':character(6,2)['online']==0,
        'hunter_character':character(6,2)==park['retained_class_fixture'],
        'hunter_saved':saved(6)==park['retained_class_saved']==rows['entry']['entered_saved'],
        'parked_pets_exact':current==park['retained_class_pets'],
        'retained_named_and_new_pet':retained_tame_pets(rows['cast'],current),
        'primary_intentionally_stopped':primary_ok,
        'origin_registration':actors.load()==old['origin_actor'],
        'all_six_offline':set(all_offline)=={'1','2','3','4','5','6'} and
            all(v['native']['online']==0 for v in all_offline.values()),
        'no_probe':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_pet_abandon_probe.json','owned_tame_request_probe.json','owned_stable_request_probe.json')),
        'compiled_bridge':d['after'].get('build')==d['build'],
        'single_scout_reconnected':set(d['parked_reconnect_attempt'])=={'scout'}}
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
        checks['no_temporary_tame_pose_rows']=not q.fetchall()
    t.receipt.update(sources=[*refs.values(),bound(primary_stop),bound(deployment)],checks=checks,
        primary_stop_source=bound(primary_stop),deployment_source=bound(deployment),
        input_sent=False,qualification_added=False,retained_pets=current,all_offline_snapshot=all_offline,
        frame=shot(t.out/'scout_offline.png'),completed=all(checks.values()),
        phase='owned_tame_diagnostic_parked_boundary',
        qualified_scope='Read-only closure of one successful ordinary Tame and normal parking. '
            'Original pose, saved state and all protected actors preserved; Harnesswolf and new Wolf retained. '
            'Modern stable-cache delivery remains open. No qualification or gameplay input replay.')
    if relaunch:t.receipt['relaunch_source']=bound(relaunch)
    if not all(checks.values()):raise RuntimeError('fresh diagnostic Tame parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    names=('preparation','entry','stored','stage','refresh','cast','restore','park','finish')
    for name in (*names,'primary-stop','deployment','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--relaunch',type=Path)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,{k:getattr(a,k) for k in names},a.primary_stop,a.deployment,a.relaunch)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
