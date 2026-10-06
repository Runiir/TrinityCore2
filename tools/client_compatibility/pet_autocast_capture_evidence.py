"""Owned stock autocast geometry and raw diagnostic evidence, without wire guesses."""
from .interaction_pet_command_probe import expected_guid
from .world.buffer import Reader

SPELLS={3110:4,6307:5}
REQUEST_NAMES={'CMSG_PET_SPELL_AUTOCAST','CMSG_PET_SET_ACTION','CMSG_PET_ACTION'}


def button(probe,pet,spell,enabled):
    if (spell not in SPELLS or type(enabled) is not bool or
            probe.get('owner_guid')!='Player-1-00000005' or probe.get('pet_guid')!=expected_guid(pet)):
        raise RuntimeError('autocast control requires the exact current owned Imp')
    rows=[r for r in probe.get('actions',[]) if r.get('spell_id')==spell and r.get('slot')==SPELLS[spell]]
    if len(rows)!=1:raise RuntimeError('stock autocast spell row is absent or ambiguous')
    row=rows[0];frame=row.get('frame',{})
    if (row.get('available') is not True or row.get('is_token') is not False or
            row.get('autocast_allowed') is not True or row.get('autocast_enabled') is not enabled or
            frame.get('button')!='PetActionButton'+str(SPELLS[spell]) or
            not all(frame.get(k) is True for k in ('available','visible','enabled')) or
            any(type(frame.get(k)) is not int or not 0<=frame[k]<65535 for k in ('x','y'))):
        raise RuntimeError('stock autocast button state or visible enabled viewport point differs')
    return row,[round(frame['x']/65535*1280),round(frame['y']/65535*720)]


def native_buttons(catalog,pet):
    packet=catalog.get('packet',{})
    if packet.get('direction')!='from_native' or packet.get('name')!='SMSG_PET_SPELLS':
        raise RuntimeError('requires an actual native pet catalog')
    r=Reader(bytes.fromhex(packet['body']));guid=r.unpack('Q')[0]
    family,duration,react,command,flags=r.unpack('HIBBH');words=r.unpack('10I')
    if guid!=pet['guid'] or react!=3 or command!=1:
        raise RuntimeError('native catalog does not belong to the current Assist/Follow pet')
    return [{'slot':i+1,'spell_id':word&0xffffff,'action_type':word>>24} for i,word in enumerate(words)]


def request_checks(rows,session,since,until):
    scoped=[p for p in rows if p.get('session')==session and since<=p.get('time',0)<=until]
    modern=[p for p in scoped if p.get('direction')=='from_client' and p.get('name') in REQUEST_NAMES]
    native=[p for p in scoped if p.get('direction')=='to_native' and
        p.get('name') in REQUEST_NAMES|{'CMSG_PET_ABANDON'}]
    checks={'actual_modern_request':1<=len(modern)<=2,
        'raw_bodies_captured':bool(modern) and all(isinstance(p.get('body'),str) and len(p['body'])>=2
            and len(p['body'])%2==0 and all(c in '0123456789abcdef' for c in p['body']) for p in modern),
        'no_native_autocast_or_action':not native,
        'no_abandon':not any(p.get('name')=='CMSG_PET_ABANDON' for p in scoped)}
    return checks,modern,native
