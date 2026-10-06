"""Independent owned native pet spell, aura, and public buff evidence."""
import struct
from .world.buffer import Reader,Writer
from .world.native_objects import guid as native_guid
from .world.gameobjects import modern_guid
from .world.objects import player_high
from .interaction_pet_summon import cast_identity


def buffs(state):
    value=state.get('buffs')
    if value in ([],{}):return []
    if not isinstance(value,list) or any(type(x) is not int or not 0<x<1<<31 for x in value):
        raise ValueError('public buff identity list is absent or invalid')
    return value


def native_aura(packet,owner):
    if packet.get('direction')!='from_native' or packet.get('name') not in ('SMSG_AURA_UPDATE','SMSG_AURA_UPDATE_ALL'):
        raise ValueError('requires actual native aura update')
    r=Reader(bytes.fromhex(packet['body']));unit=native_guid(r)
    if unit!=owner:return None
    values=[];seen=set()
    while r.pos<len(r.data):
        slot,spell=r.unpack('Bi')
        if len(values)>=255 or slot in seen or spell<0:raise ValueError('invalid native aura entries')
        seen.add(slot);row={'slot':slot,'spell':spell}
        if spell:
            flags,level,applications=r.unpack('HBB');caster=unit if flags&8 else native_guid(r)
            duration=list(r.unpack('ii')) if flags&32 else None
            points=[r.unpack('i')[0] for bit in (1,2,4) if flags&64 and flags&bit]
            row.update(flags=flags,level=level,applications=applications,caster=caster,duration=duration,points=points)
        values.append(row)
    r.end();return {'unit':unit,'all':packet['name']=='SMSG_AURA_UPDATE_ALL','entries':values}


def request_checks(rows,session,since,until,pet):
    names={'CMSG_PET_ACTION','CMSG_PET_ABANDON','CMSG_PET_SET_ACTION','CMSG_PET_SPELL_AUTOCAST',
        'CMSG_CAST_SPELL','SMSG_SPELL_GO','SMSG_CAST_FAILED'}
    scoped=[p for p in rows if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in names]
    modern=[p for p in scoped if p.get('direction')=='from_client' and p['name']=='CMSG_PET_ACTION']
    native=[p for p in scoped if p.get('direction')=='to_native' and p['name']=='CMSG_PET_ACTION']
    expected_modern=Writer().guid(*modern_guid(pet['guid'],pet['map'])).pack('I',0xc08018a3).guid().pack('3f',0.,0.,0.).finish().hex()
    expected_native=struct.pack('<QIQfff',pet['guid'],0xc10018a3,0,0.,0.,0.).hex()
    completed=[];failed=[]
    for p in scoped:
        if p.get('direction')!='from_native' or p['name'] not in ('SMSG_SPELL_GO','SMSG_CAST_FAILED'):continue
        row=cast_identity(p)
        if row['spell']!=6307:continue
        if p['name']=='SMSG_CAST_FAILED':failed.append(p)
        elif row['caster']==row['unit']==pet['guid']:completed.append({'packet':p,'decoded':row})
    checks={'one_exact_owned_modern_cast':len(modern)==1 and modern[0].get('body')==expected_modern,
        'one_exact_owned_native_cast':len(native)==1 and native[0].get('body')==expected_native,
        'native_cast_pair':len(modern)==len(native)==1 and 0<=native[0]['time']-modern[0]['time']<2,
        'one_owned_native_completion':len(completed)==1,
        'completion_follows_native_request':len(native)==len(completed)==1
            and 0<=completed[0]['packet']['time']-native[0]['time']<10,
        'no_native_failure':not failed,
        'no_other_native_pet_or_owner_cast':not any(p.get('direction')=='to_native' and
            p['name']!='CMSG_PET_ACTION' for p in scoped),
        'no_other_modern_pet_or_owner_cast':not any(p.get('direction')=='from_client' and
            p['name']!='CMSG_PET_ACTION' for p in scoped),
        'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in scoped)}
    return checks,{'modern':modern,'native':native,'completed':completed,'failed':failed}


def cancel_request_checks(rows,session,since,until,pet,owner=5):
    names={'CMSG_CANCEL_AURA','CMSG_PET_CANCEL_AURA','CMSG_PET_ACTION','CMSG_PET_ABANDON',
        'CMSG_PET_SET_ACTION','CMSG_PET_SPELL_AUTOCAST','CMSG_CAST_SPELL'}
    scoped=[p for p in rows if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in names]
    modern=[p for p in scoped if p.get('direction')=='from_client']
    native=[p for p in scoped if p.get('direction')=='to_native']
    expected_modern=Writer().pack('I',6307).guid(owner,player_high()).finish().hex()
    expected_native=struct.pack('<QI',pet['guid'],6307).hex()
    checks={'one_exact_stock_owner_cancel':len(modern)==1 and modern[0]['name']=='CMSG_CANCEL_AURA'
            and modern[0].get('body')==expected_modern,
        'one_exact_current_pet_cancel':len(native)==1 and native[0]['name']=='CMSG_PET_CANCEL_AURA'
            and native[0].get('body')==expected_native,
        'native_cancel_pair':len(modern)==len(native)==1 and 0<=native[0]['time']-modern[0]['time']<2,
        'no_player_cancel_cast_or_abandon':not any(p.get('direction')=='to_native'
            and p['name']!='CMSG_PET_CANCEL_AURA' for p in scoped)}
    return checks,{'modern':modern,'native':native}
