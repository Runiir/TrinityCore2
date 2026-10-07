"""Independent retained-data oracle for one owned Heroic Throw damage outcome."""
from .world.buffer import Reader,player_high
from .world.native_objects import guid
from .world.gameobjects import modern_guid
from .world.objects import INDEX
from .pet_attack_capture_evidence import target_guid


def require(condition,message):
    if not condition:raise RuntimeError(message)


def closed(e,field,count):
    require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at'),
        'whole closed accepted receipt required')
    require(len(e.get(field,{}))==count and all(e[field].values()),'whole '+field+' guards required')


def packet(e,name,direction):
    rows=[p for p in e['packets'] if p['name']==name and p['direction']==direction]
    require(len(rows)==1,'requires exactly one '+direction+' '+name)
    p=rows[0]
    require(p.get('session')==e['session'] and e['started_at']<=p['time']<=e['finished_at'],
        'packet is outside the owned login or capture interval')
    return Reader(bytes.fromhex(p['body']))


def verify(e,stage,entry):
    closed(e,'restoration_checks',10);closed(stage,'checks',13);closed(entry,'reentry_checks',15)
    require(e['actor']==stage['actor']==entry['actor'] and e['actor']['guid']==1 and
        e['actor']['character_name']=='Harnessone','owned primary identity differs')
    require(e['runtime']==stage['runtime']==entry['runtime'] and
        e['session']==stage['session']==entry['session'],'runtime/login epoch differs')
    require(e.get('public_errors')==[] and e.get('bridge_rejections')==[] and
        e.get('request_counts')=={'modern':1,'native':1},'ability rejection or repeated request')
    target=stage['target'];native_target=target['guid'];spell=57755
    r=packet(e,'CMSG_CAST_SPELL','to_native');counter,request,_,flags,mask=r.unpack('BiiBI')
    require(request==spell and flags==0 and mask==2 and guid(r)==native_target,
        'native cast target/spell differs');r.end()
    r=packet(e,'SMSG_SPELL_START','from_native')
    require(guid(r)==1 and guid(r)==1,'native start is not owned')
    start_counter,start_spell,_,_,duration=r.unpack('BiIII')
    require(start_counter==counter and start_spell==spell and duration==0,'native instant start differs')
    r=packet(e,'SMSG_SPELL_GO','from_native')
    require(guid(r)==1 and guid(r)==1 and r.unpack('Bi')==(counter,spell),'native completion differs')
    r=packet(e,'SMSG_SPELL_GO','to_client');r.guid();unit=r.guid();cast=r.guid()
    require(unit==(1,player_high()) and r.unpack('iI')==(spell,347658),'client completion differs')
    r=packet(e,'SMSG_SPELLNONMELEEDAMAGELOG','from_native')
    require(guid(r)==native_target and guid(r)==1,'native damage identity differs')
    native_spell,damage,overkill,school,absorbed,resisted,periodic,unused,blocked,hit,debug=r.unpack('IIIBIIBBIIB');r.end()
    require(native_spell==spell and not(periodic or unused or debug or hit&~2) and damage>0,
        'unsupported native direct damage')
    r=packet(e,'SMSG_SPELL_NON_MELEE_DAMAGE_LOG','to_client')
    expected=tuple(modern_guid(native_target,target['map']))
    require(r.guid()==expected and r.guid()==(1,player_high()) and r.guid()==cast,
        'client damage identity/cast differs')
    require(r.unpack('IIIIIBIII')==(spell,347658,damage,0,overkill,school,absorbed,resisted,blocked),
        'client damage fields differ from native')
    require([r.bits(n) for n in (1,7,1,1,1)]==[0,hit,0,0,0],'client optional damage flags differ');r.end()
    before=stage['target']['fields'].get(str(INDEX['UNIT_FIELD_HEALTH']),
        stage['target']['fields'].get(INDEX['UNIT_FIELD_HEALTH']))
    after=e.get('native_target_after',{})
    require(after.get('guid')==native_target and after.get('health')==max(0,before-damage) and
        overkill==max(0,damage-before),'native health/overkill accounting differs')
    public_before=e['public_combat_log_before'];public=e['public_combat_log_after']
    events=[v for v in public.get('events',[]) if v.get('event')=='SPELL_DAMAGE' and
        v.get('sequence',0)>public_before['event_sequence']]
    require(len(events)==1,'requires one fresh public SPELL_DAMAGE')
    v=events[0]
    require(v.get('source_guid')=='Player-1-00000001' and v.get('destination_guid')==target_guid(target) and
        v.get('spell_id')==spell and v.get('spell_name')=='Heroic Throw' and
        v.get('amount')==damage and v.get('overkill')==overkill and v.get('school')==school and
        v.get('absorbed')==absorbed and v.get('resisted')==resisted and v.get('blocked')==blocked and
        v.get('critical')==bool(hit&2),'public damage fields differ')
    require(public['saved_settings']==public_before['saved_settings'],'combat filters changed')
    return {'spell':spell,'target':native_target,'damage':damage,'overkill':overkill,
        'native_health_before':before,'native_health_after':after['health'],'public_sequence':v['sequence'],
        'scope':'One stationary owned Heroic Throw instant damage outcome; other abilities and combat variants remain open.'}
