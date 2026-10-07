"""Prove a fresh occupied stable swap from the actual closed remote archive."""
import struct
from pathlib import Path
from . import lab_runtime as lab
from .review_native_feedback_checkpoint import require,packet_key
from .world.buffer import Reader,Writer
from .world.gameobjects import modern_guid
from .world.native_objects import guid as native_guid
from .interaction_hunter_stable_pair import identities,public_rows,expected_rows
CLOSURE='hunter_pair_close02/episode.json'


def whole(e,phase,key,count):
    require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at') and
        e.get('phase')==phase and len(e.get(key,{}))==count and all(e[key].values()),
        'fresh whole occupied pair differs: '+phase)


def proof(data,digests,packets):
    closure=data[CLOSURE]
    whole(closure,'fresh_occupied_pair_parked_boundary','checks',23)
    directory=Path(closure['sources'][0]['path']).parent.parent
    require(directory.parent==lab.ROOT/'evidence','private occupied pair archive differs')
    def linked(ref):
        p=Path(ref['path']);require(p.is_relative_to(directory),'foreign occupied pair source')
        key=str(p.relative_to(directory))
        require(digests.get(key)==ref.get('sha256') and key in data,'archived occupied pair source digest differs')
        return data[key]
    def frame(e,ref,field='frame',actor='scout'):
        f=e[field];key=str(Path(ref['path']).parent.relative_to(directory)/f['file'])
        require(digests.get(key)==f['sha256'],'occupied pair frame digest differs')
        m=f['monitor'];i=m['input_isolation']
        require(m['second_monitor_verified'] and m['monitor']['name']=='HDMI-1' and
            i['actor']==actor and i['host_activation_sent'] is False and
            i['display']==(':'+str(3 if actor=='scout' else 2)), 'owned monitor/input boundary differs')
    refs=closure['sources'];prep,entry,m1,c1,m2,c2,park,finish,deployment=[linked(r) for r in refs[:9]]
    whole(entry,'owned_class_entered','checks',9)
    require(prep['completed'] and deployment['completed'] and deployment['kind']=='pet_slot' and
        deployment['native_restarted'] and deployment['bridge_unchanged'] and deployment['config_unchanged'] and
        entry['runtime']['worldserver']==deployment['native'], 'fresh native pet-slot deployment differs')
    session=entry['native_session'];baseline=m1['retained_pet_before']
    require(set(r['id'] for r in baseline)=={4,6} and
        all(r['owner']==6 and r['CreatedBySpell']==883 for r in baseline) and
        identities(prep['retained_class_pets'],baseline) and
        [(r['id'],r['entry'],r['name'],r['renamed'],r['slot'],r['active']) for r in baseline]==
        [(4,42717,'Harnesswolf',1,5,0),(6,299,'Wolf',0,0,1)] and
        m1['finished_at']<c1['started_at']<c1['finished_at']<m2['started_at']<m2['finished_at']<c2['started_at'] and
        identities(c1['retained_pet_after'],m2['retained_pet_before']),
        'fresh two-pet Call Pet baseline/ordering differs')
    for index,(m,c,source,dest,active) in enumerate(((m1,c1,5,0,4),(m2,c2,0,5,6))):
        mref,cref=refs[2+index*2],refs[3+index*2]
        whole(m,'owned_pair_slot_swap_verified','move_checks',12)
        whole(c,'owned_pair_active_pet_restored','call_checks',7)
        for e in (m,c):
            require(e['actor']==entry['actor'] and e['runtime']==entry['runtime'] and
                e['native_session']==session and e['fixture_source']==refs[0] and
                e['entry_source']==refs[1] and e['model'] is None and
                e['custom_script_permission']=='blocked_by_user','same owned pair runtime/source differs')
        stage=linked(m['source']);whole(stage,'await_owned_pair_slot_review','open_checks',8)
        reviewed=linked(m['screen_review']);require(reviewed['source']==m['source'] and
            reviewed['frame']==stage['frame'] and reviewed['control']=='Swap Harnesswolf' and
            reviewed['destination']==dest and m['ordinary_input']==
            {'kind':'drag','start':reviewed['point'],'end':reviewed['end'],'duration':.8} and
            0<=m['started_at']-stage['finished_at']<120,'fresh reviewed occupied drag differs')
        frame(stage,m['source']);frame(m,mref)
        cfg=m['capture_config'];rows=m['capture_packets'];master=m['native_master_guid']
        require((m['number'],m['source_slot'],m['destination'],m['swap_number'])==(4,source,dest,6) and
            m['input_sent'] is True and m['capture_disarmed'] is True and cfg['owner']==6 and
            cfg['session']==session and cfg['native_master_guid']==master and
            cfg['slot_swap']=={'pet_numbers':[4,6],'slots':[0,5]} and
            0<cfg['expires_at']-cfg['created_at']<=90 and
            all(p['session']==session and cfg['created_at']<=p['time']<=cfg['expires_at'] for p in rows),
            'exact private occupied pair capture differs')
        def get(direction,name):return [p for p in rows if p['direction']==direction and p['name']==name]
        public=get('from_client','CMSG_SET_PET_SLOT');native=get('to_native','CMSG_SET_PET_SLOT')
        update=get('from_native','SMSG_PET_SLOT_UPDATED');result=get('from_native','SMSG_STABLE_RESULT')
        delivered=get('to_client','SMSG_PET_STABLE_RESULT')
        require(len(public)==len(native)==len(update)==len(result)==len(delivered)==1 and
            public[0]['body']==Writer().pack('IB',4,dest).guid(*modern_guid(master,0)).finish().hex(),
            'one actual modern occupied request differs')
        r=Reader(bytes.fromhex(native[0]['body']));number,slot=r.unpack('IB');octets=[0]*8
        for i in (3,2,0,7,5,6,1,4):octets[i]=r.bits(1)
        for i in (5,3,1,7,4,0,6,2):
            if octets[i]:octets[i]=r.unpack('B')[0]^1
        r.end()
        require((number,slot,int.from_bytes(bytes(octets),'little'))==(4,dest,master) and
            update[0]['body']==struct.pack('<4I',4,dest,6,source).hex() and
            result[0]['body']==delivered[0]['body']=='08' and
            public[0]['time']<=native[0]['time']<=update[0]['time']<=result[0]['time']<=delivered[0]['time'],
            'actual ordered native occupied success differs')
        slots={4:dest,6:source};actives={4:0,6:0}
        require(identities(baseline,m['retained_pet_after'],slots,actives) and
            public_rows(m['state']['stable_probe'])==expected_rows(m['retained_pet_after']) and
            identities(m['retained_pet_after'],c['retained_pet_after'],slots,{4:int(active==4),6:int(active==6)},active),
            'complete saved/public occupied pair identity differs')
        recon=linked(c['source']);whole(recon,'owned_call_pet_caption_observed','origin_checks',3)
        require(recon['source']==mref and recon['call_pet_spell']['id']==883 and
            recon['call_pet_spell']['known'] is True and c['active_pet_number']==active,
            'ordinary active-pet recovery source differs')
        call=c['call_pet_packets'];requests=[];completed=[];loaded=[]
        for p in call:
            require(packet_key(p) in packets and p['session']==session and
                c['call_pet_started_at']<=p['time']<=c['finished_at'],'actual archived Call Pet packet differs')
            r=Reader(bytes.fromhex(p['body']))
            if (p['direction'],p['name'])==('to_native','CMSG_CAST_SPELL'):
                requests.append(r.unpack('BI'))
            elif (p['direction'],p['name'])==('from_native','SMSG_SPELL_GO'):
                caster=native_guid(r);unit=native_guid(r);counter,spell=r.unpack('Bi')
                if counter==0:
                    flags,zero,_=r.unpack('III');r.end()
                    require((caster,unit,spell,flags,zero)==(6,6,883,256,0),'pet-load cooldown notification differs')
                    loaded.append(p)
                else:completed.append((caster,counter,spell))
            else:raise RuntimeError('foreign pair Call Pet packet')
        require(len(requests)==1 and requests[0][0]>0 and requests[0][1]==883 and
            completed==[(6,*requests[0])] and len(loaded)==1 and
            c['native_save_command']['command']=='saveall' and
            c['call_pet_started_at']<c['native_save_command']['started_at']<c['finished_at'],
            'one ordinary Call Pet request/completion and native flush differs')
    whole(park,'await_original_selection_review','checks',4)
    require(finish['completed'] and len(finish['checks'])==5 and all(finish['checks'].values()) and
        park['retained_class_fixture']['online']==0 and identities(c2['retained_pet_after'],park['retained_class_pets']) and
        closure['retained_pets']==park['retained_class_pets'],'closed original/retained pair preservation differs')
    if closure.get('primary_stop_source'):
        stop=linked(closure['primary_stop_source'])
        whole(stop,'user_requested_primary_client_stopped','checks',8)
        require(stop['deployment_source']==refs[8] and stop['input_sent'] is False and
            stop['finished_at']<m1['started_at'] and stop['before']==stop['after'] and
            closure['checks']['primary_intentionally_stopped'],'user-requested primary absence differs')
        frame(stop,closure['primary_stop_source'],actor='primary')
    frame(closure,{'path':str(directory/CLOSURE)},'scout_frame')
    return {'operation':'pets.stable_swap','owner':6,'pet_numbers':[4,6],
        'native_slot_roundtrips':{'4':[5,0,5],'6':[0,5,0]},'native_success_results':[8,8],
        'move_checks_each':12,'ordinary_call_pet_checks_each':7,'closure_checks':23,
        'originals_preserved':True,'scripts_blocked':True,
        'primary_stopped_by_user':bool(closure.get('primary_stop_source'))}
