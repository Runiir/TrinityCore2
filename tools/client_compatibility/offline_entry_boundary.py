"""A failed re-entry can be stopped only at an unchanged closed offline boundary."""

def validate(boundary,preparation,failed,runtime,current,events,preparation_ref,fixture):
    if (boundary.get('completed') is not True or boundary.get('failure') is not None or
        boundary.get('phase')!='owned_abandon_parked_boundary' or
        len(boundary.get('checks',{}))!=19 or not all(v is True for v in boundary['checks'].values()) or
        boundary.get('runtime')!=runtime or boundary.get('actor')!=preparation.get('origin_actor') or
        boundary.get('actor',{}).get('guid')!=2 or preparation.get('class_actor')!=fixture or
        fixture.get('guid')!=6 or preparation.get('runtime')!=runtime or
        preparation.get('phase')!='await_owned_class_lobby_review' or preparation.get('completed') is not True or
        failed.get('actor')!=fixture or failed.get('runtime')!=runtime or
        failed.get('fixture_source')!=preparation_ref or failed.get('completed') is not False or
        failed.get('failure')!='RuntimeError: UI observation did not become decodable' or
        failed.get('phase')!='owned_class_entry_started' or not failed.get('finished_at') or
        not boundary.get('finished_at',0)<preparation.get('started_at',0)<preparation.get('finished_at',0)<
            failed.get('started_at',0)<failed['finished_at'] or
        current!=boundary.get('all_offline_snapshot') or set(current)!={'1','2','3','4','5','6'} or
        any(v.get('native',{}).get('online')!=0 for v in current.values()) or
        any(r.get('name')=='CMSG_PLAYER_LOGIN' or r.get('event')=='native_player_created' for r in events) or
        not any(r.get('name')=='CMSG_LOADING_SCREEN_NOTIFY' and r.get('direction')=='from_client' for r in events) or
        not any(r.get('event')=='unmapped_client_packet' and r.get('name')=='CMSG_GET_ACCOUNT_CHARACTER_LIST' for r in events)):
        raise RuntimeError('closed failed re-entry or complete offline preservation differs')
