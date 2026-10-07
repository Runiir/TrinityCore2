"""Require complete ordinary entry, captured reentry and normal parking sources."""


def successful(row,count,runtime,actor,preparation):
    if (row.get('completed') is not True or row.get('failure') is not None or
        not row.get('finished_at') or row.get('runtime')!=runtime or row.get('actor')!=actor or
        row.get('fixture_source')!=preparation or row.get('model') is not None or
        row.get('custom_script_permission')!='blocked_by_user' or
        len(row.get('checks',{}))!=count or not all(v is True for v in row['checks'].values())):
        raise RuntimeError('whole owned reentry source differs')


def captured(entry,stage,previous,park,runtime,origin,hunter,refs):
    successful(entry,9,runtime,hunter,refs['preparation'])
    successful(stage,14,runtime,origin,refs['preparation'])
    successful(previous,9,runtime,hunter,refs['preparation'])
    successful(park,4,runtime,hunter,refs['preparation'])
    c=entry.get('capture_config',{});packets=entry.get('capture_packets',[])
    login=entry.get('native_login_requests',[]);offline=stage.get('all_offline_snapshot',{})
    if (entry.get('phase')!='owned_class_entered' or stage.get('phase')!='await_owned_reentry_review' or
        park.get('phase')!='await_original_selection_review' or entry.get('source')!=refs['stage'] or
        stage.get('sources')!=[refs[k] for k in ('preparation','previous','park','primary')] or
        stage.get('primary_stop_source')!=refs['primary'] or
        entry.get('capture_disarmed') is not True or entry.get('input_sent') is not True or
        entry.get('qualification_added') is not False or
        entry.get('ordinary_input')!={'kind':'reviewed_lobby_click','point':[640,660]} or
        c.get('schema')!='client442_owned_entry_request_probe_v1' or
        (c.get('owner'),c.get('account_id'),c.get('runtime'))!=(6,2,runtime) or
        c.get('session')!=previous.get('native_session') or entry.get('native_session')!=c.get('session') or
        c.get('entry_source',{}).get('sha256')!=refs['previous']['sha256'] or
        not previous['finished_at']<park['started_at']<park['finished_at']<stage['started_at']<
            stage['finished_at']<entry['started_at']<=c.get('created_at',0)<entry['finished_at'] or
        not 0<c.get('expires_at',0)-c['created_at']<=120 or
        set(offline)!={'1','2','3','4','5','6'} or any(v['native']['online']!=0 for v in offline.values()) or
        {k:offline['6'].get(k) for k in ('native','saved','pets')}!={'native':park['retained_class_fixture'],'saved':park['retained_class_saved'],
            'pets':park['retained_class_pets']} or len(login)!=1 or
        login[0].get('session')!=c['session'] or
        (login[0].get('name'),login[0].get('direction'))!=('CMSG_PLAYER_LOGIN','to_native') or
        not c['created_at']<=login[0].get('time',0)<=entry['finished_at'] or len(packets)>16 or
        any(r.get('session')!=c['session'] or r.get('direction')!='from_client' or
            r.get('name') not in ('CMSG_LOADING_SCREEN_NOTIFY','CMSG_GET_ACCOUNT_CHARACTER_LIST') or
            len(bytes.fromhex(r.get('body','')))!=5 or
            not c['created_at']<=r.get('time',0)<=c['expires_at'] for r in packets)):
        raise RuntimeError('captured ordinary reentry lineage differs')
