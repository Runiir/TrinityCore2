"""A failed loading screen may be retired only with unchanged offline authority."""
def validate(stage,failed,current,runtime,stage_ref,preparation_ref):
    if (stage.get('completed') is not True or stage.get('failure') is not None or not stage.get('finished_at') or
        stage.get('phase')!='await_owned_reentry_review' or len(stage.get('checks',{}))!=14 or
        not all(v is True for v in stage['checks'].values()) or stage.get('runtime')!=runtime or
        stage.get('fixture_source')!=preparation_ref or stage.get('actor',{}).get('guid')!=2 or
        stage.get('model') is not None or stage.get('custom_script_permission')!='blocked_by_user' or
        failed.get('completed') is not False or
        failed.get('failure')!='RuntimeError: UI state observation deadline exceeded' or
        not failed.get('finished_at') or failed.get('runtime')!=runtime or failed.get('source')!=stage_ref or
        failed.get('fixture_source')!=preparation_ref or failed.get('input_sent') is not True or
        failed.get('capture_disarmed') is not True or failed.get('qualification_added') is not False or
        failed.get('model') is not None or failed.get('custom_script_permission')!='blocked_by_user' or
        failed.get('ordinary_input')!={'kind':'reviewed_lobby_click','point':[640,660]} or
        failed.get('native_login_requests')!=[] or not stage['finished_at']<failed['started_at']<failed['finished_at']):
        raise RuntimeError('requires the whole same-lifetime no-login capture and preparation')
    actor=failed.get('actor',{});c=failed.get('capture_config',{});rows=failed.get('capture_packets',[])
    if (tuple(actor.get(k) for k in ('guid','account_id','class','level'))!=(6,2,3,10) or
        c.get('schema')!='client442_owned_entry_request_probe_v1' or c.get('owner')!=6 or c.get('account_id')!=2 or
        not c.get('session') or c.get('runtime')!=runtime or
        not failed['started_at']<=c.get('created_at',0)<c.get('expires_at',0)<=c['created_at']+120 or
        len(rows)>16 or any(r.get('session')!=c['session'] or r.get('direction')!='from_client' or
            r.get('name') not in ('CMSG_LOADING_SCREEN_NOTIFY','CMSG_GET_ACCOUNT_CHARACTER_LIST') or
            len(bytes.fromhex(r.get('body','')))!=5 or
            not c['created_at']<=r.get('time',0)<=min(c['expires_at'],failed['finished_at']) for r in rows) or
        current!=stage.get('all_offline_snapshot') or set(current)!={'1','2','3','4','5','6'} or
        any(v['native']['online']!=0 for v in current.values())):
        raise RuntimeError('no-login capture or all six offline snapshots differ')
