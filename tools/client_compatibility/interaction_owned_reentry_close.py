"""Close two successful captured reentries, retaining pets and the stopped primary."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import prepared,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_hunter_tame_stage import NAMES
from .owned_reentry_boundary import captured,successful
from .scout_relaunch_lineage import verified_deployment
from .observation.journal import entries


def close(t,source,reentries,park_path,finish_path,primary_stop,deployment):
    old=prepared(t,source,True);ref=bound(source);stop=closed(primary_stop)
    if (stop.get('phase')!='user_requested_primary_client_stopped' or
        len(stop.get('checks',{}))!=8 or not all(v is True for v in stop['checks'].values()) or
        stop.get('before')!=stop.get('after') or
        stop['runtime']['worldserver']!=t.receipt['runtime']['worldserver']):
        raise RuntimeError('original user-stopped primary differs')
    d,_=verified_deployment(deployment,t.receipt['runtime'])
    closed_sources=[bound(source),bound(primary_stop),bound(deployment)]
    previous=None
    for path in reentries:
        e=closed(path);stage_path=Path(e['source']['path']);stage=closed(stage_path)
        previous_path=Path(stage['sources'][1]['path']);p=closed(previous_path)
        prior_park_path=Path(stage['sources'][2]['path']);prior_park=closed(prior_park_path)
        refs={'preparation':ref,'stage':bound(stage_path),'previous':bound(previous_path),
            'park':bound(prior_park_path),'primary':bound(primary_stop)}
        captured(e,stage,p,prior_park,t.receipt['runtime'],old['origin_actor'],old['class_actor'],refs)
        if previous is not None and refs['previous']!=previous:
            raise RuntimeError('captured reentries are not one consecutive client lifetime')
        if stage.get('refreshed_source'):
            parent_path=Path(stage['refreshed_source']['path']);parent=closed(parent_path)
            if stage['refreshed_source']!=bound(parent_path) or any(stage.get(k)!=parent.get(k) for k in
                ('sources','checks','all_offline_snapshot','primary_stop_source','fixture_source','actor','runtime')):
                raise RuntimeError('refreshed closed selection source differs')
            closed_sources.append(bound(parent_path))
        journal=list(entries(lab.ROOT/'evidence/owned_entry_request_packets.jsonl'))
        raw=[r for r in journal if r.get('session')==e['native_session'] and
            e['capture_config']['created_at']<=r.get('time',0)<=e['capture_until']]
        native=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if
            r.get('session')==e['native_session'] and e['capture_config']['created_at']<=r.get('time',0)<=
            e['capture_until'] and (r.get('name'),r.get('direction'))==('CMSG_PLAYER_LOGIN','to_native')]
        if raw!=e['capture_packets'] or native!=e['native_login_requests']:
            raise RuntimeError('actual captured raw requests or native login journal differs')
        previous=bound(path);closed_sources.extend([previous,*refs.values()])
    park,finish=closed(park_path),closed(finish_path)
    successful(park,4,t.receipt['runtime'],old['class_actor'],ref)
    successful(finish,5,t.receipt['runtime'],old['origin_actor'],ref)
    if not e['finished_at']<park['started_at']<park['finished_at']<finish['started_at']:
        raise RuntimeError('final normal parking and selection order differs')
    before=snapshot();hunter=before['6']
    with actor('primary'):primary_absent=lab.owned_process('client') is None
    checks={**origin_checks(old),**protected(old),
        'hunter_character':hunter['native']==park['retained_class_fixture'],
        'hunter_saved':hunter['saved']==park['retained_class_saved']==e['entered_saved']==old['natural_saved'],
        'hunter_pets':hunter['pets']==park['retained_class_pets'],
        'all_six_offline':all(v['native']['online']==0 for v in before.values()),
        'primary_intentionally_stopped':primary_absent and before['1']==stop['after'],
        'origin_registration':actors.load()==old['origin_actor'],
        'no_probe':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_pet_abandon_probe.json','owned_tame_request_probe.json','owned_stable_request_probe.json',
                'owned_entry_request_probe.json')),
        'compiled_bridge':d['after'].get('build')==d['build'],
        'single_scout_reconnected':set(d['parked_reconnect_attempt'])=={'scout'},
        'two_captured_native_reentries':len(reentries)==2,
        'hunter_home_pose':all(hunter['native'][k]==old['natural_native'][k] for k in
            ('position_x','position_y','position_z','orientation','map'))}
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
        checks['no_temporary_pose_rows']=not q.fetchall()
    t.receipt.update(sources=[*closed_sources,bound(park_path),bound(finish_path)],checks=checks,
        primary_stop_source=bound(primary_stop),deployment_source=bound(deployment),
        all_offline_snapshot=before,input_sent=False,qualification_added=False,
        frame=shot(t.out/'scout_offline.png'),completed=all(checks.values()),
        phase='owned_reentry_parked_boundary',qualified_scope='Two ordinary captured reentries succeeded; '
            'historical loading stalls remain unresolved. No gameplay qualification or replay.')
    if len(checks)!=20 or not all(checks.values()):raise RuntimeError('captured reentry parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','finish','primary-stop','deployment','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reentry',type=Path,action='append',required=True);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,a.preparation,a.reentry,a.park,a.finish,a.primary_stop,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
