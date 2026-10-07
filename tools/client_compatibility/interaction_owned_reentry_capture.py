"""Capture one reviewed same-client Hunter reentry without changing protocol behavior."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,enter,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_bridge_deploy import shot
from .observation.journal import entries


def preparation(t,source,entry,park,primary_stop):
    old=prepared(t,source,True);e,p,stop=[closed(v) for v in (entry,park,primary_stop)]
    for row,count in ((e,9),(p,4),(stop,8)):
        if len(row.get('checks',{}))!=count or not all(v is True for v in row['checks'].values()):
            raise RuntimeError('whole reentry preparation sources differ')
    if (e.get('phase')!='owned_class_entered' or p.get('phase')!='await_original_selection_review' or
        any(r.get('actor')!=old['class_actor'] or r.get('runtime')!=t.receipt['runtime'] or
            r.get('fixture_source')!=bound(source) for r in (e,p)) or
        not e['finished_at']<p['started_at']<p['finished_at']<t.receipt['started_at'] or
        stop.get('phase')!='user_requested_primary_client_stopped' or stop.get('before')!=stop.get('after') or
        stop['runtime']['worldserver']!=t.receipt['runtime']['worldserver']):
        raise RuntimeError('same-client normal entry/parking or primary stop differs')
    before=snapshot()
    with actor('primary'):primary_absent=lab.owned_process('client') is None
    checks={**origin_checks(old),**protected(old),
        'hunter_character':before['6']['native']==p['retained_class_fixture'],
        'hunter_saved':before['6']['saved']==p['retained_class_saved']==e['entered_saved'],
        'hunter_pets':before['6']['pets']==p['retained_class_pets'],
        'all_six_offline':all(v['native']['online']==0 for v in before.values()),
        'primary_stopped':primary_absent and before['1']==stop['after'],
        'origin_registration':actors.load()==old['origin_actor']}
    t.receipt.update(sources=[bound(v) for v in (source,entry,park,primary_stop)],
        checks=checks,all_offline_snapshot=before,primary_stop_source=bound(primary_stop),
        phase='await_owned_reentry_review',input_sent=False,qualification_added=False,
        frame=shot(t.out/'reentry_selection.png'),completed=all(checks.values()))
    if len(checks)!=14 or not all(checks.values()):raise RuntimeError('owned reentry offline preparation differs')
    if actors.register(6)!=old['class_actor']:raise RuntimeError('retained Hunter registration differs')


def capture(t,source,stage,review):
    old=prepared(t,source);p=closed(stage)
    if (p.get('phase')!='await_owned_reentry_review' or p.get('runtime')!=t.receipt['runtime'] or
        p.get('actor')!=old['origin_actor'] or p.get('fixture_source')!=bound(source) or
        len(p.get('checks',{}))!=14 or not all(v is True for v in p['checks'].values()) or
        p.get('all_offline_snapshot')!=snapshot()):
        raise RuntimeError('requires the exact closed offline reentry preparation')
    e=closed(Path(p['sources'][1]['path']))
    if p['sources'][1]!=bound(Path(p['sources'][1]['path'])):raise RuntimeError('earlier entry digest differs')
    path=lab.ROOT/'run/owned_entry_request_probe.json'
    if path.exists():raise RuntimeError('another owned entry probe is armed')
    started=time.time();config={'schema':'client442_owned_entry_request_probe_v1','owner':6,'account_id':2,
        'session':e['native_session'],'created_at':started,'expires_at':started+120,'runtime':t.receipt['runtime'],
        'entry_source':{'path':str(Path(p['sources'][1]['path']).relative_to(lab.ROOT)),
            'sha256':p['sources'][1]['sha256']}}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(source=bound(stage),capture_config=config,capture_config_sha256=digest,
        capture_disarmed=False,qualification_added=False,input_sent=True,
        ordinary_input={'kind':'reviewed_lobby_click','point':[640,660]});t.persist()
    try:enter(t,source,review)
    finally:
        until=time.time();session=config['session'];journal=lab.ROOT/'evidence/owned_entry_request_packets.jsonl'
        packets=[r for r in entries(journal) if r.get('session')==session and started<=r.get('time',0)<=until] if journal.exists() else []
        requests=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('session')==session and
            started<=r.get('time',0)<=until and (r.get('name'),r.get('direction'))==('CMSG_PLAYER_LOGIN','to_native')]
        t.receipt.update(capture_packets=packets,native_login_requests=requests,capture_until=until);t.persist()
        if not path.is_file() or lab.sha256(path)!=digest:
            raise RuntimeError('owned entry lease changed; refusing to remove another capture')
        path.unlink();t.receipt['capture_disarmed']=True;t.persist()
        if len(packets)>16 or any(r['direction']!='from_client' or len(bytes.fromhex(r['body']))!=5 or
                r['name'] not in ('CMSG_LOADING_SCREEN_NOTIFY','CMSG_GET_ACCOUNT_CHARACTER_LIST') for r in packets):
            raise RuntimeError('owned entry capture exceeds its fixed-width diagnostic scope')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','capture'])
    for name in ('preparation','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('entry','park','primary-stop','stage','review'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.action=='prepare' and not all((a.entry,a.park,a.primary_stop)):p.error('requires normal entry/parking and original primary stop')
    if a.action=='capture' and not all((a.stage,a.review)):p.error('requires closed preparation and fresh selected-character review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='prepare':preparation(t,a.preparation,a.entry,a.park,a.primary_stop)
            else:capture(t,a.preparation,a.stage,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','capture_disarmed','checks')}),flush=True)
