"""Pure complete archive proof for disposable Wolf6 Abandon and normal parking."""
from pathlib import Path
from .hunter_pair_identity import identities
from .hunter_abandon_identity import named_preserved,exact_requests
from .world.objects import INDEX
from .review_native_feedback_checkpoint import require,packet_key

CLOSURE='hunter_abandon_close01/episode.json'


def proof(data,digests,packets,events):
    c=data[CLOSURE];directory=Path(c['sources'][0]['path']).parent.parent
    def whole(e,phase,n,key='checks'):
        require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at') and
            (phase is None or e.get('phase')==phase) and len(e.get(key,{}))==n and all(e[key].values()),
            'whole disposable Abandon source differs')
    def linked(ref):
        path=Path(ref['path']);require(path.is_relative_to(directory),'foreign Abandon source')
        key=str(path.relative_to(directory));require(digests.get(key)==ref['sha256'],'Abandon source digest differs')
        return data[key]
    def frame(e,ref,display):
        f=e['frame'];key=str(Path(ref['path']).parent.relative_to(directory)/f['file']);m=f['monitor'];i=m['input_isolation']
        require(digests.get(key)==f['sha256'] and m['second_monitor_verified'] and m['monitor']['name']=='HDMI-1' and
            i['actor']=='scout' and i['display']==display and i['host_activation_sent'] is False and
            m['pid']==e['runtime']['client']['pid'],'current owned Abandon frame/monitor/input differs')
    whole(c,'owned_abandon_parked_boundary',19);refs=c['sources']
    old,e,s,a,p,f=[linked(r) for r in refs[:6]];deploy=linked(refs[7])
    whole(e,'owned_class_entered',9);whole(s,'owned_test_pet_abandon_dialog',11)
    whole(a,'owned_disposable_pet_abandoned',16);whole(p,'await_original_selection_review',4);whole(f,None,5)
    require(old['completed'] and not old.get('failure') and old['phase']=='await_owned_class_lobby_review' and
        old['origin_actor']['guid']==2 and old['class_actor']==e['actor'] and
        (e['actor']['guid'],e['actor']['class'],e['actor']['level'])==(6,3,10) and
        e['finished_at']<s['started_at']<s['finished_at']<a['started_at']<a['finished_at']<p['started_at']<p['finished_at']<f['started_at'],
        'fresh Hunter entry/confirmation/parking chain differs')
    for v in (e,s,a,p,f,c,old):
        require(v['runtime']==e['runtime'] and v['model'] is None and v['controller']=='code_diagnostic_ordinary_inputs' and
            v['custom_script_permission']=='blocked_by_user','Abandon runtime/controller/script boundary differs')
    for v in (e,s,a,p,f):require(v['fixture_source']==refs[0],'same preparation digest differs')
    require(a['native_session']==s['native_session']==e['native_session'] and a['source']==refs[2] and
        a['abandon_confirmation_sent'] is True and a['ordinary_input']=={'kind':'click','value':[579,192],'hold':.4},
        'one reviewed disposable Okay input differs')
    review=linked(a['screen_review'])
    require(review['reviewed'] is True and review['control']=='Confirm Abandon Wolf6' and review['point']==[579,192] and
        review['source']==refs[2] and review['frame']==s['frame'] and review['fixture_source_sha256']==refs[0]['sha256'],
        'exact pre-input stock Okay review differs')
    pet=a['native_pet_before'];guid=pet['guid'];fields=pet['fields']
    require(pet==s['native_pet'] and guid>>52==0xf14 and (guid>>32)&0xfffff==299 and pet['map']==0 and
        fields[str(INDEX['UNIT_FIELD_PETNUMBER'])]==6 and fields[str(INDEX['OBJECT_FIELD_ENTRY'])]==299 and
        len(s['state']['pet_popups'])==1 and s['state']['pet_popups'][0]['which']=='ABANDON_PET' and
        sorted(r['text'] for r in s['dialog_controls'])==['Cancel','Okay'],'exact disposable native pet/dialog differs')
    require(len(a['capture_packets'])==2 and all(exact_requests(a['capture_packets'],guid).values()) and
        {packet_key(v) for v in a['capture_packets']}==packets and len(events)==2 and
        sorted(v[2] for v in events)==['from_client','to_native'],'actual remote request count/bytes differ')
    config=a['capture_config']
    require(config['schema']=='client442_owned_pet_abandon_probe_v1' and config['owner']==6 and config['pet_number']==6 and
        config['native_pet_guid']==guid and config['session']==e['native_session'] and
        0<config['expires_at']-config['created_at']<=90 and a['capture_disarmed'] is True and
        all(config['created_at']<=v['time']<config['expires_at'] for v in a['capture_packets']),
        'bounded disposable capture differs')
    require(identities(old['retained_class_pets'],a['retained_pet_before']) and
        named_preserved(a['retained_pet_before'],a['retained_pet_after']) and
        named_preserved(a['retained_pet_before'],p['retained_class_pets']) and c['retained_pets']==p['retained_class_pets'] and
        guid in a['native_removed'] and
        a['native_player_after'][str(INDEX['UNIT_FIELD_SUMMON'])]==0 and
        a['native_player_after'][str(INDEX['UNIT_FIELD_SUMMON']+1)]==0 and
        a['public_pet']['exists'] is False and not a['state'].get('pet_popups') and not a['state'].get('panels') and
        not a['state'].get('lua_errors') and not a['state'].get('blocked_actions') and
        a['state']['world_position']==s['initial_position'] and p['retained_class_saved']==e['entered_saved'] and
        p['retained_class_fixture']['online']==0 and all(p['retained_class_fixture'][k]==e['entered_native'][k] for k in
            ('money','level','xp','health','position_x','position_y','position_z','orientation','map')),
        'native/public/saved removal or named-pet/owner preservation differs')
    stop=data['primary_user_stop_source01.json'];pause=data['scout_resource_pause_source01.json']
    whole(stop,'user_requested_primary_client_stopped',8);whole(pause,'parked_scout_resource_paused',8)
    require(digests['primary_user_stop_source01.json']==refs[6]['sha256']==c['primary_stop_source']['sha256']==deploy['primary_stop_source']['sha256'] and
        digests['scout_resource_pause_source01.json']==deploy['source']['sha256'] and
        stop['before']==stop['after']==pause['after']['1']==deploy['offline_baselines']['1'] and
        pause['before']==pause['after']==deploy['offline_baselines'] and
        deploy['schema']=='client442_resource_paused_scout_deployment_v1' and deploy['completed'] and deploy['native_unchanged'] and
        deploy['primary_stopped'] and deploy['native']==e['runtime']['worldserver']==stop['runtime']['worldserver'] and
        deploy['before']==pause['runtime']['modern_world']==stop['runtime']['modern_world'] and
        deploy['after']==e['runtime']['modern_world'] and deploy['after']!=deploy['before'] and
        deploy['scout_lifetime']==e['runtime']['client'] and deploy['scout_lifetime']!=pause['runtime']['client'] and
        set(deploy['parked_reconnect_attempt'])=={'scout'} and
        deploy['build']==e['runtime']['modern_world']['build'] and deploy['build']['build_jobs']==1 and
        deploy['build']['available_memory_kib_before']>=6291456,
        'exact six-actor pause, compiled deployment or stopped primary boundary differs')
    attempt=deploy['parked_reconnect_attempt']['scout'];restored=linked({'path':attempt['episode'],'sha256':attempt['sha256']})
    whole(restored,'single_scout_parked_reconnected',7,'restoration_checks')
    require(restored['all_offline_snapshot']==deploy['offline_baselines'] and restored['runtime']==e['runtime'] and
        restored['actor']==old['origin_actor'] and restored['session']==attempt['session'],'closed fresh scout restoration differs')
    display=deploy['launch_monitor']['input_isolation']['display']
    require(display.startswith(':') and deploy['launch_monitor']['input_isolation']['host_activation_sent'] is False,
        'new private scout display is absent')
    for v,ref in ((s,refs[2]),(a,refs[3]),(c,{'path':str(directory/CLOSURE)})):frame(v,ref,display)
    return {'operation':'pets.abandon','owner':6,'disposable_pet_number':6,'native_disposable_removed':True,
        'named_pet_preserved':4,'confirmation_checks':16,'closure_checks':19,'modern_requests':1,'native_requests':1,
        'one_scout_client':True,'primary_stopped_by_user':True,'scripts_blocked':True,'all_protected_actors_preserved':True}
