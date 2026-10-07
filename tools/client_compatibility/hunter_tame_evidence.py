"""Join one captured ordinary Tame, modern stable delivery and full parked closure."""
from pathlib import Path
from . import lab_runtime as lab
from .hunter_tame_boundary import successful_chain,retained_tame_pets
from .scout_pause_lineage import transition
from .tame_stable_projection import prove
from .review_native_feedback_checkpoint import require,packet_key,whole


NAMES={k:'hunter_tame_'+v+'/episode.json' for k,v in (
    ('preparation','prepare02'),('entry','entry02'),('stored','stored02'),('stage','wolf_stage01'),
    ('refresh','review_refresh01'),('cast','cast01'),('restore','pose_restore01'),
    ('park','park01'),('finish','original_finish01'))}
CLOSURE='hunter_tame_success_close01/episode.json'
BEFORE='hunter_tame_stable_before02/episode.json'
AFTER='hunter_tame_stable_after01/episode.json'


def proof(data,digests,tracking):
    c=data[CLOSURE];whole(c,'checks',20)
    require(c.get('phase')=='owned_tame_diagnostic_parked_boundary' and
        c.get('input_sent') is False and c.get('qualification_added') is False,'parked Tame boundary differs')
    rows={k:data[v] for k,v in NAMES.items()};cast=rows['cast'];old=rows['preparation']
    directory=Path(cast['staging_source']['path']).parent.parent
    require(directory.parent==lab.ROOT/'evidence','owned Tame batch differs')
    def ref(key):return {'path':str(directory/key),'sha256':digests[key]}
    def link(value,key):require(value==ref(key),'Tame source digest differs: '+key)
    refs={k:ref(v) for k,v in NAMES.items()}
    require(c.get('sources',[])[:9]==list(refs.values()) and len(c.get('sources',[]))==11,
        'full Tame closure source set differs')
    stop=data['carried_primary_stop01.json'];primary_ref=c['sources'][9]
    require(primary_ref==c.get('primary_stop_source') and primary_ref.get('sha256')==
        digests['carried_primary_stop01.json'],'carried primary shutdown digest differs')
    deployment_key=str(Path(c['sources'][10]['path']).relative_to(directory));d=data[deployment_key]
    link(c['deployment_source'],deployment_key);link(c['sources'][10],deployment_key)
    pause_key=str(Path(d['source']['path']).relative_to(directory));pause=data[pause_key]
    restore_key=str(Path(d['parked_reconnect_attempt']['scout']['episode']).relative_to(directory))
    restored=data[restore_key];lineage={'pause':pause,'restored':restored,
        'refs':{'pause':ref(pause_key),'restoration':ref(restore_key)}}
    transition(d,c['runtime'],pause,restored,lineage['refs'])
    successful_chain(old,c['runtime'],{k:v for k,v in rows.items() if k!='preparation'},
        refs,stop,d,primary_ref,lineage)
    require(rows['finish']['finished_at']<c['started_at'] and
        retained_tame_pets(cast,c['retained_pets']) and
        c['retained_pets']==rows['park']['retained_class_pets']==c['all_offline_snapshot']['6']['pets'],
        'parked named/new pet persistence differs')
    saved=c['all_offline_snapshot']
    require(set(saved)=={'1','2','3','4','5','6'} and all(v['native']['online']==0 for v in saved.values()) and
        all(saved[k]==v for k,v in old['protected_baseline'].items()) and saved['1']==stop['after'] and
        saved['6']['native']==rows['park']['retained_class_fixture'] and
        saved['6']['saved']==rows['park']['retained_class_saved']==rows['entry']['entered_saved'],
        'complete offline actor preservation differs')
    before=data[BEFORE];after=data[AFTER]
    for key,row,phase in ((BEFORE,before,'baseline'),(AFTER,after,'projection')):
        whole(row,'checks',11)
        require(row.get('phase')=='owned_tame_stable_'+phase and row.get('runtime')==cast['runtime'] and
            row.get('actor')==cast['actor'] and row.get('native_session')==cast['native_session'] and
            row.get('gameplay_input_sent') is False and row.get('qualification_added') is False,
            'whole passive stable proof differs')
        link(row['fixture_source'],NAMES['preparation']);link(row['entry_source'],NAMES['entry'])
    link(after['before_source'],BEFORE);link(after['cast_source'],NAMES['cast'])
    require(rows['stored']['finished_at']<before['started_at']<before['finished_at']<rows['stage']['started_at'] and
        cast['finished_at']<after['started_at']<after['finished_at']<rows['restore']['started_at'],
        'stable projection chronology differs')
    wire=prove(cast,before['public_stable'],after['public_stable'])
    require(wire==after['wire_projection'],'actual recorded stable projection differs')
    for key,row in [*[(NAMES[k],v) for k,v in rows.items()],(BEFORE,before),(AFTER,after),(CLOSURE,c)]:
        require(row.get('custom_script_permission')=='blocked_by_user' and row.get('model') is None,
            'code controller or script boundary differs')
        frame=row.get('frame') or row.get('outcome_frame')
        if frame:
            file=str(Path(key).parent/frame['file']);m=frame['monitor'];i=m['input_isolation']
            require(digests.get(file)==frame['sha256'] and m['second_monitor_verified'] is True and
                m['monitor']['name']=='HDMI-1' and i['actor']=='scout' and i['host_activation_sent'] is False,
                'owned second-monitor frame differs')
    require({packet_key(p) for p in cast['capture_packets']}==tracking['raw'] and
        all(packet_key(p) in tracking['packets'] for p in cast['cast_packets']),
        'actual archived Tame packet journal differs')
    from .world.buffer import Reader,player_high
    from .world.native_objects import guid as native_guid
    channels=[p for p in cast['capture_packets'] if p['name']!='SMSG_PET_ADDED']
    require(len(channels)==4 and len(tracking['instances'])==1,'actual channel or physical instance differs')
    for p in channels:
        r=Reader(bytes.fromhex(p['body']));native=p['direction']=='from_native'
        require((native_guid(r)==6 if native else r.guid()==(6,player_high())),'channel owner differs')
        if p['name'].endswith('START'):
            require(r.unpack('i')[0]==1515,'channel spell differs')
            if not native:require(r.unpack('I')[0]==238368,'channel visual differs')
            require(r.unpack('I')[0]==10000 and
                (r.unpack('BB')==(0,0) if native else r.bits(1)==r.bits(1)==0),'channel duration or flags differ')
        else:require(r.unpack('I')[0]==0,'channel final update differs')
        r.end()
    for p in cast['capture_packets']:
        matches=[r for r in tracking['events'] if (r.get('name'),r.get('direction'),r.get('bytes'))==
            (p['name'],p['direction'],len(bytes.fromhex(p['body']))) and 0<=p['time']-r['time']<.1]
        require(len(matches)==1,'physical native/modern Tame metadata differs')
    samples=cast['public_channel_samples'];events=samples[-1]['player_channel']['events']
    require(len(samples)==8 and all(s['player_channel'].get('active') is True for s in samples[:-1]) and
        samples[-1]['player_channel'].get('active') is False and [e['event'] for e in events]==
        ['UNIT_SPELLCAST_CHANNEL_START','UNIT_SPELLCAST_CHANNEL_STOP'] and
        all(e['spell']==1515 for e in events) and 9.8<events[1]['observed_at']-events[0]['observed_at']<10.2,
        'public Tame channel differs')
    return {'operation':'pets.tame','new_pet_number':cast['native_pet_after']['fields']['69'],
        'native_requests':1,'captured_channel_packets':4,'captured_native_added':True,
        'modern_stable_deliveries':1,'public_stable_projection':True,'closure_checks':20,
        'all_six_offline':True,'primary_stopped':True,'named_pet_preserved':True,
        'scope':'One ordinary native Tame1515, stock channel, owned new pet and stable-cache persistence; other pets/slots and revive remain open.'}


def collect(member,lines,data,tracking):
    """Keep only the exact bounded cast window while streaming a remote archive."""
    cast=data[NAMES['cast']];entry=data[NAMES['entry']];session=cast['native_session']
    since=cast['capture_config']['created_at'];until=cast['finished_at']
    for p in lines:
        if member=='tracking/events.jsonl':
            if (p.get('event')=='instance_authenticated' and p.get('account_id')==2 and
                    entry['started_at']<=p.get('time',0)<=entry['finished_at']):
                tracking['instances'].add(p['session'])
            if (p.get('session') in {session}|tracking['instances'] and since<=p.get('time',0)<=until and
                    p.get('name') in {r['name'] for r in cast['capture_packets']} and
                    p.get('event') in ('native_packet','modern_packet')):
                tracking['events'].append(p)
        elif p.get('session')==session and since<=p.get('time',0)<=until:
            destination='raw' if member=='tracking/owned_tame_request_packets.jsonl' else 'packets'
            tracking[destination].add(packet_key(p))
        require(len(tracking['raw'])<=8 and len(tracking['packets'])<=256 and
            len(tracking['events'])<=16 and len(tracking['instances'])<=1,'Tame journal bound exceeded')
