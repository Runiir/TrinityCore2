"""Close a no-Tame cache diagnostic after normal parking and original selection."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_bridge_deploy import shot
from .observation.journal import entries


def close(t,preparation,entry,stored,failed,park,finish,primary_stop):
    old=prepared(t,preparation,True);e,s,p,f,stop=[closed(x) for x in (entry,stored,park,finish,primary_stop)]
    bad=json.loads(failed.read_text());runtime=t.receipt['runtime']
    for row,count in ((e,9),(s,15),(p,4),(f,5),(stop,8)):
        if len(row.get('checks',{}))!=count or not all(row['checks'].values()):
            raise RuntimeError('whole no-Tame closure source checks differ')
    if (bad.get('completed') is not False or not bad.get('finished_at') or
        bad.get('failure')!='RuntimeError: requires the exact stored Harnesswolf cache and no active pet' or
        bad.get('gameplay_input_sent') is not False or bad.get('qualification_added') is not False or
        bad.get('public_stable',{}).get('pets') or
        any(v.get('runtime')!=runtime or v.get('fixture_source')!=bound(preparation) for v in (e,s,bad,p,f)) or
        any(v.get('actor')!=old['class_actor'] for v in (e,s,bad,p)) or f.get('actor')!=old['origin_actor'] or
        bad.get('entry_source')!=bound(entry) or s.get('entry_source')!=bound(entry) or
        not old['finished_at']<e['started_at']<e['finished_at']<s['started_at']<s['finished_at']<
            bad['started_at']<bad['finished_at']<p['started_at']<p['finished_at']<f['started_at']<f['finished_at']):
        raise RuntimeError('no-Tame diagnostic and normal restoration chain differs')
    native_requests=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if
        r.get('session')==e['native_session'] and e['started_at']<=r.get('time',0)<=p['finished_at'] and
        (r.get('name'),r.get('direction'))==('CMSG_CAST_SPELL','to_native')]
    if any(int.from_bytes(bytes.fromhex(r['body'])[1:5],'little')==1515 for r in native_requests):
        raise RuntimeError('a native Tame request prevents no-Tame closure')
    current=snapshot();owner=current['6']['native'];natural=old['natural_native']
    with actor('primary'):primary_absent=lab.owned_process('client') is None
    checks={**origin_checks(old),**protected(old),'hunter_offline':owner['online']==0,
        'hunter_saved':current['6']['saved']==p['retained_class_saved']==e['entered_saved'],
        'hunter_character':owner==p['retained_class_fixture'],
        'named_pet_exact':current['6']['pets']==p['retained_class_pets']==old['retained_class_pets'],
        'hunter_pose_resources':all(owner[k]==natural[k] for k in
            ('position_x','position_y','position_z','orientation','map','health','money','xp','power1')),
        'all_six_offline':all(v['native']['online']==0 for v in current.values()),
        'primary_intentionally_stopped':primary_absent and current['1']==stop['after'],
        'origin_registration':actors.load()==old['origin_actor'],'no_native_tame':True,
        'no_probe':not any((lab.ROOT/'run'/n).exists() for n in
            ('owned_tame_request_probe.json','owned_pet_abandon_probe.json','owned_stable_request_probe.json')),
        'normal_parking':p.get('phase')=='await_original_selection_review','same_native_session':
            bad.get('native_session')==s.get('native_session')==e['native_session']}
    t.receipt.update(sources=[bound(x) for x in (preparation,entry,stored,failed,park,finish,primary_stop)],
        checks=checks,all_offline_snapshot=current,primary_stop_source=bound(primary_stop),
        native_cast_requests=native_requests,input_sent=False,qualification_added=False,
        frame=shot(t.out/'scout_offline.png'),completed=all(checks.values()),
        phase='owned_tame_precast_parked_boundary',qualified_scope='No-Tame cache diagnostic closed after normal parking; the failed baseline remains excluded.')
    if len(checks)!=20 or not all(checks.values()):raise RuntimeError('no-Tame parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','stored','failed','park','finish','primary-stop','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,a.preparation,a.entry,a.stored,a.failed,a.park,a.finish,a.primary_stop)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
