"""Prove the fresh owned pet4 slot round trip and its closed preservation chain."""
import struct
from pathlib import Path
from . import lab_runtime as lab
from .world.buffer import Reader,Writer
from .world.gameobjects import modern_guid
from .world.native_objects import guid as native_guid
from .review_native_feedback_checkpoint import require,packet_key


NAMES={
    'entry':'hunter_slot_entry01','stage':'hunter_slot_trial_stage01','open':'hunter_slot_trial_open01',
    'forward_stage':'hunter_slot_trial_forward_stage01','forward':'hunter_slot_trial_forward01',
    'back_stage':'hunter_slot_trial_back_stage01','back':'hunter_slot_trial_back01',
    'recon':'hunter_slot_trial_call_pet_recon01','restore':'hunter_slot_trial_finish01',
    'park':'hunter_slot_final_park01','finish':'hunter_slot_origin_finish01','close':'hunter_slot_final_close01'}


def whole(e,phase,checks):
    require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at') and
        e.get('phase')==phase,'whole accepted phase differs: '+phase)
    for key,count in checks.items():
        require(len(e.get(key,{}))==count and all(e[key].values()),key+' differs')


def same_pet(before,after,slot,active,until):
    require(len(before)==len(after)==1 and set(before[0])==set(after[0]),'pet row shape differs')
    b,a=before[0],after[0]
    require((b['id'],b['owner'],b['entry'],b['name'],b['renamed'],b['CreatedBySpell'])==
        (4,6,42717,'Harnesswolf',1,883),'fresh retained Call Pet baseline differs')
    require(a['slot']==slot and a['active']==active and 0<b['savetime']<=a['savetime']<=until and
        {k:v for k,v in b.items() if k not in ('slot','active','savetime')}==
        {k:v for k,v in a.items() if k not in ('slot','active','savetime')},'retained pet state differs')


def slot_packets(e,source,destination,master,session):
    cfg=e['capture_config'];rows=e['capture_packets']
    require(cfg['owner']==6 and cfg['session']==session and cfg['native_master_guid']==master and
        cfg['modern_master_guid']==list(modern_guid(master,0)) and cfg['slot_roundtrip']==
        {'pet_number':4,'slots':[0,5]} and 0<cfg['expires_at']-cfg['created_at']<=90 and
        e['capture_disarmed'] is True,'exact bounded slot capture differs')
    require(all(p['session']==session and cfg['created_at']<=p['time']<=cfg['expires_at'] for p in rows),
        'slot packet is outside its private capture')
    def get(direction,name):return [p for p in rows if p['direction']==direction and p['name']==name]
    public=get('from_client','CMSG_SET_PET_SLOT');native=get('to_native','CMSG_SET_PET_SLOT')
    update=get('from_native','SMSG_PET_SLOT_UPDATED');result=get('from_native','SMSG_STABLE_RESULT')
    delivered=get('to_client','SMSG_PET_STABLE_RESULT')
    request=Writer().pack('IB',4,destination).guid(*modern_guid(master,0)).finish().hex()
    require(len(public)==len(native)==len(update)==len(result)==len(delivered)==1 and
        public[0]['body']==request,'exact single owned slot packet chain differs')
    r=Reader(bytes.fromhex(native[0]['body']));number,slot=r.unpack('IB');octets=[0]*8
    for i in (3,2,0,7,5,6,1,4):octets[i]=r.bits(1)
    for i in (5,3,1,7,4,0,6,2):
        if octets[i]:octets[i]=r.unpack('B')[0]^1
    r.end()
    require((number,slot,int.from_bytes(bytes(octets),'little'))==(4,destination,master),
        'exact native pet/master/destination differs')
    require(update[0]['body']==struct.pack('<4I',4,destination,0,source).hex() and
        result[0]['body']==delivered[0]['body']=='08' and
        public[0]['time']<=native[0]['time']<=update[0]['time']<=result[0]['time']<=delivered[0]['time'],
        'native ordered slot success differs')


def proof(data,digests,packets):
    rows={k:data[v+'/episode.json'] for k,v in NAMES.items()};e=rows['restore'];opened=rows['open']
    directory=Path(e['opening_source']['path']).parent.parent
    require(directory.parent==lab.ROOT/'evidence','owned evidence directory differs')
    def link(ref,key):
        require(ref.get('path')==str(directory/key) and ref.get('sha256')==digests.get(key),
            'archived source digest differs: '+key)
    def frame(row,key,name):
        f=row[name];link({'path':str(directory/key/f['file']),'sha256':f['sha256']},str(key/f['file']))
        m=f['monitor'];i=m['input_isolation']
        require(m['second_monitor_verified'] is True and m['monitor']['name']=='HDMI-1' and
            i['actor']=='scout' and i['display']==':3' and i['host_activation_sent'] is False,
            'owned scout second-monitor frame differs')
    whole(opened,'await_owned_stable_slot_review',{'outcome_checks':9,'protected_checks':5})
    whole(e,'owned_stable_slot_roundtrip_restored',{'restoration_checks':13,'protected_checks':5})
    require(not e.get('failed_recovery_source') and e.get('call_pet_input_replayed') is not False,
        'failed recovery cannot qualify a fresh roundtrip')
    session=e['native_session'];master=opened['capture_config']['native_master_guid'];baseline=opened['baseline_pets']
    require(master>>52==0xf13 and master>>32&0xfffff==6749 and opened['capture_disarmed'] is True and
        e['baseline_pets']==baseline and e['baseline_resources']==opened['baseline_resources'] and
        e['baseline_saved']==opened['baseline_saved'],'same native opening baseline differs')
    whole(rows['entry'],'owned_class_entered',{'checks':9})
    for key in ('stage','open','forward_stage','forward','back_stage','back','recon','restore'):
        row=rows[key]
        require(row['actor']==e['actor'] and row['runtime']==e['runtime'] and row['native_session']==session and
            row['custom_script_permission']=='blocked_by_user' and row['model'] is None and
            row['fixture_source']==e['fixture_source'],'same actor/runtime/script boundary differs')
    for direction,source,destination in (('forward',0,5),('back',5,0)):
        moved=rows[direction];stage=rows[direction+'_stage'];key=NAMES[direction]
        whole(moved,'owned_stable_slot_move_verified',{'move_checks':12,'protected_checks':5})
        whole(stage,'await_owned_stable_slot_review',{'protected_checks':5})
        require(moved['slot']==stage['slot']==source and moved['destination']==destination and
            moved['input_sent'] is True and moved['ordinary_input']['kind']=='drag',
            'ordinary slot direction differs')
        link(moved['move_source'],NAMES[direction+'_stage']+'/episode.json')
        link(moved['screen_review'],NAMES[direction+'_stage']+'/review.json')
        reviewed=data[NAMES[direction+'_stage']+'/review.json'];link(reviewed['source'],NAMES[direction+'_stage']+'/episode.json')
        require(reviewed['reviewed'] is True and reviewed['control']=='Move Harnesswolf' and
            reviewed['destination']==destination and reviewed['frame']==stage['frame'] and
            reviewed['point']==moved['ordinary_input']['start'] and reviewed['end']==moved['ordinary_input']['end'] and
            0<=moved['started_at']-stage['finished_at']<120,'fresh reviewed ordinary drag differs')
        frame(stage,Path(NAMES[direction+'_stage']),'frame');frame(moved,Path(key),'after_frame')
        link(moved['opening_source'],NAMES['open']+'/episode.json')
        slot_packets(moved,source,destination,master,session)
        same_pet(baseline,moved['retained_pet_after'],destination,0,moved['finished_at'])
        public=moved['after_state']['stable_probe'];pet=public['pets']
        require(public['visible'] is True and public['stable_slots']==16 and len(pet)==1 and
            (pet[0]['slot'],pet[0]['name'],pet[0]['level'],pet[0]['display_id'])==
            (destination+1,'Harnesswolf',10,903),'stock resulting slot differs')
    require(opened['finished_at']<rows['forward']['started_at']<rows['forward']['finished_at']<
        rows['back']['started_at']<rows['back']['finished_at']<e['started_at'],'fresh whole move ordering differs')
    link(e['opening_source'],NAMES['open']+'/episode.json');link(e['return_source'],NAMES['back']+'/episode.json')
    link(e['call_pet_source'],NAMES['recon']+'/episode.json')
    recon=rows['recon'];whole(recon,'owned_call_pet_caption_observed',{'protected_checks':5})
    spell=recon['call_pet_spell']
    require(spell==e['call_pet_spell'] and spell['id']==883 and spell['name']=='Call Pet 1' and
        spell['known'] is True and spell['override']==883,'native-known stock Call Pet caption differs')
    call=e['call_pet_packets']
    require(call and all(packet_key(p) in packets and p['session']==session and
        e['call_pet_started_at']<=p['time']<=e['finished_at'] for p in call),
        'actual archived ordinary recovery packet differs')
    request=[];completed=[]
    for p in call:
        r=Reader(bytes.fromhex(p['body']))
        if (p['direction'],p['name'])==('to_native','CMSG_CAST_SPELL'):
            _,spell=r.unpack('BI');request.append(spell)
        elif (p['direction'],p['name'])==('from_native','SMSG_SPELL_GO'):
            caster=native_guid(r);native_guid(r);_,spell=r.unpack('Bi');completed.append((caster,spell))
        else:raise RuntimeError('foreign recovery packet')
    require(request and set(request)=={883} and completed and set(completed)=={(6,883)},
        'native owned Call Pet883 request/completion differs')
    same_pet(baseline,e['retained_pet_after'],0,1,e['finished_at'])
    require(e['restored_public_pet']['exists'] is True and e['restored_public_pet']['name']=='Harnesswolf' and
        [c['status'] for c in e['cases'] if c['id']=='pets.stable_slot']==['native_owned_stable_slot_roundtrip_pass'],
        'fresh whole public recovery/case differs')
    for key,phase,checks in (('park','await_original_selection_review',{'checks':4}),
        ('close','hunter_stable_slot_closed_boundary',{'checks':22})):
        whole(rows[key],phase,checks)
    finished=rows['finish'];require(finished['completed'] is True and finished['failure'] is None and
        len(finished['checks'])==5 and all(finished['checks'].values()),'original selection finish differs')
    park=rows['park'];closure=rows['close']
    require(e['finished_at']<park['started_at']<finished['started_at']<closure['started_at'] and
        park['retained_class_fixture']['online']==0 and park['retained_class_saved']==opened['baseline_saved'],
        'normal final offline preservation differs')
    same_pet(baseline,park['retained_class_pets'],0,1,park['finished_at'])
    for key in ('park','close'):
        require(rows[key]['runtime']==e['runtime'],'closure runtime differs')
    frame(closure,Path(NAMES['close']),'scout_frame')
    expected_sources={str(directory/(NAMES[k]+'/episode.json')):digests[NAMES[k]+'/episode.json'] for
        k in ('restore','forward','back','park','finish')}
    actual={s['path']:s['sha256'] for s in closure['sources']}
    require(all(actual.get(p)==h for p,h in expected_sources.items()),'whole closure source hashes differ')
    primary=data['stable_slot_bridge_deploy01/primary_after/episode.json']
    require(primary['completed'] is True and primary['failure'] is None and primary['actor']['guid']==1 and
        primary['bridge_native_restoration']['offline'] is True and
        len(primary['bridge_native_restoration']['checks'])==9 and all(primary['bridge_native_restoration']['checks'].values()) and
        primary['runtime']['worldserver']==e['runtime']['worldserver'] and
        primary['runtime']['modern_world']==e['runtime']['modern_world'],'same lifetime protected offline primary differs')
    require(closure['checks']['actor_1_unchanged'] and closure['checks']['primary_lifetime'],
        'primary saved user pose/lifetime differs')
    return {'pet_number':4,'owner':6,'native_slots':[0,5,0],'native_success_results':[8,8],
        'move_checks_each':12,'restoration_checks':13,'closure_checks':22,'ordinary_call_pet':883,
        'hunter_offline':True,'originals_preserved':True,'scripts_blocked':True}
