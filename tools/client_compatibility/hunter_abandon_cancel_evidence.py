"""Pure archive proof for one disposable Wolf6 Abandon Cancel."""
from pathlib import Path
from . import lab_runtime as lab
from .hunter_pair_identity import identities
from .review_native_feedback_checkpoint import require

CLOSURE='hunter_abandon_close01/episode.json'


def proof(data,digests,abandon_events):
    c=data[CLOSURE];directory=Path(c['sources'][0]['path']).parent.parent
    def whole(e,phase,n):
        require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at') and
            (phase is None or e.get('phase')==phase) and len(e.get('checks',{}))==n and all(e['checks'].values()),
            'whole Abandon Cancel source differs')
    def linked(ref):
        path=Path(ref['path']);require(path.is_relative_to(directory),'foreign cancellation source')
        key=str(path.relative_to(directory));require(digests.get(key)==ref['sha256'],'cancellation source digest differs')
        return data[key]
    def frame(e,ref):
        f=e['frame'];key=str(Path(ref['path']).parent.relative_to(directory)/f['file'])
        require(digests.get(key)==f['sha256'],'cancellation frame digest differs')
        m=f['monitor'];i=m['input_isolation']
        require(m['second_monitor_verified'] and m['monitor']['name']=='HDMI-1' and
            i['actor']=='scout' and i['display']==':3' and i['host_activation_sent'] is False,
            'single owned monitor/input boundary differs')
    whole(c,'owned_abandon_cancel_parked_boundary',18)
    refs=c['sources'];old,e,s,a,p,f=[linked(r) for r in refs[:6]]
    whole(e,'owned_class_entered',9);whole(s,'owned_test_pet_abandon_dialog',11)
    whole(a,'owned_test_pet_abandon_cancelled',12);whole(p,'await_original_selection_review',4);whole(f,None,5)
    require(old['completed'] and old['phase']=='await_owned_class_lobby_review' and
        e['finished_at']<s['started_at']<s['finished_at']<a['started_at']<a['finished_at']<p['started_at']<p['finished_at']<f['started_at'],
        'complete cancellation entry/park ordering differs')
    for x in (s,a,p):
        require(x['actor']==e['actor'] and x['runtime']==e['runtime'] and x['fixture_source']==refs[0] and
            x['model'] is None and x['custom_script_permission']=='blocked_by_user','owned cancellation runtime/source differs')
    require(a['native_session']==s['native_session']==e['native_session'] and a['source']==refs[2] and
        a['abandon_confirmation_sent'] is False and a['ordinary_input']=={'kind':'click','value':[701,192],'hold':.4},
        'one ordinary stock Cancel differs')
    d=linked(a['screen_review'])
    require(d['reviewed'] is True and d['control']=='Cancel Abandon' and d['point']==[701,192] and
        d['source']==refs[2] and d['frame']==s['frame'] and d['fixture_source_sha256']==refs[0]['sha256'],
        'exact reviewed Cancel control differs')
    require(len(s['state']['pet_popups'])==1 and s['state']['pet_popups'][0]['which']=='ABANDON_PET' and
        [(x['name'],x['text']) for x in s['dialog_controls']]==[
            ('StaticPopup1Button1','Okay'),('StaticPopup1Button2','Cancel')] and
        not a['state'].get('pet_popups') and not a['state'].get('panels') and
        not a['state'].get('lua_errors') and not a['state'].get('blocked_actions') and not abandon_events,
        'stock dialog outcome or archived no-request boundary differs')
    baseline=old['retained_class_pets']
    require([(x['id'],x['owner'],x['entry'],x['name'],x['slot'],x['active'],x['CreatedBySpell']) for x in baseline]==[
        (4,6,42717,'Harnesswolf',5,0,883),(6,6,299,'Wolf',0,1,883)] and
        identities(baseline,s['retained_pet_before']) and identities(s['retained_pet_before'],a['retained_pet_after']) and
        identities(a['retained_pet_after'],p['retained_class_pets']) and c['retained_pets']==p['retained_class_pets'] and
        p['retained_class_fixture']['online']==0 and p['retained_class_saved']==e['entered_saved'] and
        a['state']['world_position']==s['initial_position'] and
        a['state']['target'].get('guid')==s['initial_target'].get('guid') and
        a['public_pet']['exists'] is True and a['public_pet']['name']=='Wolf' and
        a['public_pet']['guid']==s['pet_menu']['source_control']['guid'],
        'saved/public disposable pet preservation differs')
    stop=data['primary_user_stop_source01.json'];whole(stop,'user_requested_primary_client_stopped',8)
    require(digests['primary_user_stop_source01.json']==refs[6]['sha256']==c['primary_stop_source']['sha256'] and
        stop['before']==stop['after'] and stop['input_sent'] is False and stop['actor']['guid']==1 and
        stop['finished_at']<old['started_at'] and
        all(stop['runtime'][k]==e['runtime'][k] for k in ('worldserver','modern_world')) and
        c['checks']['primary_intentionally_stopped'],'exact user-requested primary absence differs')
    frame(s,refs[2]);frame(a,refs[3]);frame(c,{'path':str(directory/CLOSURE)})
    return {'operation':'pets.abandon_cancel','owner':6,'disposable_pet_number':6,'named_pet_preserved':4,
        'dialog_checks':11,'cancel_checks':12,'closure_checks':18,'abandon_requests':0,
        'ordinary_cancel':True,'primary_stopped_by_user':True,'scripts_blocked':True,'all_protected_actors_preserved':True}
