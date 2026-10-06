"""Compare owned Attack requests and native/client combat pairs independently."""
import struct
from types import SimpleNamespace
from .interaction_pet_follow_capture import follow_request
from .world import combat
from .world.buffer import Reader
from .world.native_objects import guid
from .world.gameobjects import modern_guid


def request_checks(packets,session,since,until,pet,target):
    names={'CMSG_PET_ACTION','CMSG_PET_ABANDON','CMSG_PET_SET_ACTION','CMSG_CAST_SPELL'}
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in names]
    modern=[p for p in rows if p['direction']=='from_client'];native=[p for p in rows if p['direction']=='to_native']
    decoded=follow_request(modern[0]) if len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION' else None
    body=struct.pack('<QIQfff',pet['guid'],0x07000002,target['guid'],0,0,0).hex()
    checks={'one_owned_attack_request':bool(decoded and decoded['guid']==list(modern_guid(pet['guid'],pet['map']))
        and decoded['word']==0x03800002 and decoded['target']==list(modern_guid(target['guid'],target['map']))
        and decoded['position']==[0.,0.,0.]),
        'one_exact_native_attack':len(modern)==len(native)==1 and native[0]['name']=='CMSG_PET_ACTION'
            and native[0]['body']==body and 0<=native[0]['time']-modern[0]['time']<2,
        'no_other_owner_or_pet_request':len(rows)==2 and all(p['name']=='CMSG_PET_ACTION' for p in rows)}
    return checks,rows


def combat_pairs(packets,session,since,until,pet,target,name):
    if name not in ('SMSG_ATTACK_START','SMSG_ATTACK_STOP'):raise ValueError('unknown combat outcome')
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name')==name]
    owner=SimpleNamespace(character={'map':pet['map']});pairs=[]
    for p in rows:
        if p.get('direction')!='from_native':continue
        body=bytes.fromhex(p['body']);r=Reader(body)
        attacker,victim=r.unpack('QQ') if name=='SMSG_ATTACK_START' else (guid(r),guid(r))
        if (attacker,victim)!=(pet['guid'],target['guid']):continue
        expected=combat.response(owner,name,body)[1].hex()
        delivered=[c for c in rows if c.get('direction')=='to_client' and c['body']==expected
            and 0<=c['time']-p['time']<2]
        pairs.append({'native':p,'expected_client_body':expected,'client':delivered[0] if len(delivered)==1 else None})
    return pairs
