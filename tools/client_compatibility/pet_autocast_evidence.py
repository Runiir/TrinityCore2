"""Exact owned native switch and independent catalog/persistence readback evidence."""
import struct
from .pet_autocast_capture_evidence import SPELLS
from .world.buffer import Reader
from .world.gameobjects import modern_guid


def decode_request(body):
    r=Reader(bytes.fromhex(body));guid=r.guid();slot,word,tail=r.unpack('IIB');r.end()
    return {'guid':list(guid),'slot':slot,'word':word,'tail':tail}


def request_checks(rows,session,since,until,pet,spell,enabled):
    if spell not in SPELLS or type(enabled) is not bool:raise ValueError('requires a captured autocast switch')
    names={'CMSG_PET_SET_ACTION','CMSG_PET_ACTION','CMSG_PET_SPELL_AUTOCAST','CMSG_PET_ABANDON'}
    scoped=[p for p in rows if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in names]
    modern=[p for p in scoped if p.get('direction')=='from_client' and p.get('name')=='CMSG_PET_SET_ACTION']
    native=[p for p in scoped if p.get('direction')=='to_native' and p.get('name')=='CMSG_PET_SET_ACTION']
    decoded=None
    if len(modern)==1:
        try:decoded=decode_request(modern[0]['body'])
        except (ValueError,KeyError,struct.error):pass
    slot=SPELLS[spell]-1;word=(0x181 if enabled else 0x101)<<23|spell
    expected=struct.pack('<QII',pet['guid'],slot,(0xc1 if enabled else 0x81)<<24|spell).hex()
    checks={'one_exact_owned_modern_switch':len(modern)==1 and decoded=={
            'guid':list(modern_guid(pet['guid'],pet['map'])),'slot':slot,'word':word,'tail':0},
        'one_exact_owned_native_switch':len(native)==1 and native[0].get('body')==expected,
        'native_switch_pair':len(modern)==len(native)==1 and 0<=native[0]['time']-modern[0]['time']<2,
        'no_other_native_pet_action':not any(p.get('direction')=='to_native' and p['name']!='CMSG_PET_SET_ACTION' for p in scoped),
        'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in scoped)}
    return checks,{'modern':modern,'native':native,'decoded':decoded}


def saved_buttons(persisted):
    words=persisted['abdata'].split()
    if len(words)!=20 or any(not w.isdecimal() for w in words):raise ValueError('invalid native saved pet bar')
    pairs=[(int(words[i]),int(words[i+1])) for i in range(0,20,2)]
    if any(not 0<=kind<=255 or not 0<=spell<=0xffffff for kind,spell in pairs):
        raise ValueError('saved native pet action exceeds its width')
    return [{'slot':i+1,'spell_id':spell,'action_type':kind} for i,(kind,spell) in enumerate(pairs)]


def native_catalog(catalog):
    p=catalog['packet']
    if p.get('direction')!='from_native' or p.get('name')!='SMSG_PET_SPELLS':
        raise ValueError('requires an actual native pet catalog')
    r=Reader(bytes.fromhex(p['body']));guid,family,duration,react,command,flags=r.unpack('QHIBBH')
    buttons=r.unpack('10I');count=r.unpack('B')[0];actions=r.unpack('I'*count)
    cooldown_count=r.unpack('B')[0];cooldowns=[r.unpack('iHii') for _ in range(cooldown_count)];r.end()
    return {'guid':guid,'family':family,'duration':duration,'react':react,'command':command,'flags':flags,
        'buttons':[{'slot':i+1,'spell_id':word&0xffffff,'action_type':word>>24} for i,word in enumerate(buttons)],
        'actions':list(actions),'cooldowns':cooldowns}


def modern_word(word):
    action=word&0xffffff;kind=word>>24
    if action>0x7fffff or kind not in (0,1,6,7,0x81,0xc1):raise ValueError('unsupported native pet action')
    return {0x81:0x101,0xc1:0x181}.get(kind,kind)<<23|action


def catalog_delivery(rows,session,catalog,pet):
    parsed=native_catalog(catalog);packet=catalog['packet'];matches=[]
    for p in rows:
        if (p.get('session')!=session or p.get('direction')!='to_client' or
            p.get('name')!='SMSG_PET_SPELLS_MESSAGE' or not 0<=p.get('time',0)-packet['time']<2):continue
        try:
            r=Reader(bytes.fromhex(p['body']));guid=r.guid();header=r.unpack('HHIBBB');buttons=r.unpack('10I')
            count,cooldown_count,zero=r.unpack('III')
            if count>255 or cooldown_count>255 or zero:raise ValueError('modern pet catalog count exceeds native width')
            actions=r.unpack('I'*count)
            cooldowns=[r.unpack('iiifH') for _ in range(cooldown_count)];r.end()
            expected_buttons=[modern_word(x['action_type']<<24|x['spell_id']) for x in parsed['buttons']]
            expected_cooldowns=[(s,d,cd,1.0,c) for s,c,d,cd in parsed['cooldowns']]
            if (list(guid)==list(modern_guid(pet['guid'],pet['map'])) and parsed['guid']==pet['guid'] and
                header==(parsed['family'],0,parsed['duration'],parsed['command'],parsed['flags'],parsed['react']) and
                list(buttons)==expected_buttons and zero==0 and list(actions)==[modern_word(x) for x in parsed['actions']]
                and cooldowns==expected_cooldowns):matches.append(p)
        except (ValueError,KeyError,struct.error):continue
    return matches
