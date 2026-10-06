"""Require the actual owned ground request and delivered movement to its destination."""
import math,struct
from .interaction_pet_follow_capture import follow_request
from .pet_movement_evidence import following_paths
from .world.gameobjects import modern_guid


def request_checks(packets,session,since,until,pet):
    names={'CMSG_PET_ACTION','CMSG_PET_ABANDON','CMSG_PET_SET_ACTION','CMSG_CAST_SPELL'}
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until
        and p.get('name') in names]
    modern=[p for p in rows if p.get('direction')=='from_client']
    native=[p for p in rows if p.get('direction')=='to_native']
    decoded=None
    if len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION':
        try:decoded=follow_request(modern[0])
        except (ValueError,IndexError,struct.error):pass
    valid=bool(decoded and decoded['guid']==list(modern_guid(pet['guid'],pet['map']))
        and decoded['word']==0x03800004 and decoded['target']==[0,0]
        and all(math.isfinite(v) and abs(v)<=17067 for v in decoded['position'])
        and any(v!=0 for v in decoded['position']))
    expected=(struct.pack('<QIQfff',pet['guid'],0x07000004,0,*decoded['position']).hex() if valid else None)
    checks={'one_owned_ground_request':valid,
        'one_exact_native_ground_command':valid and len(native)==1 and native[0]['name']=='CMSG_PET_ACTION'
            and native[0]['body']==expected and 0<=native[0]['time']-modern[0]['time']<2,
        'no_other_owner_or_pet_command':len(modern)==len(native)==1
            and all(p['name']=='CMSG_PET_ACTION' for p in rows)}
    return checks,{'modern':modern,'native':native,'decoded':decoded}


def motion_checks(pairs,requests):
    decoded=requests.get('decoded');native=requests.get('native',[])
    paths=following_paths(pairs)
    matched=[p for p in paths if decoded and len(native)==1 and
        p['native']['time']>=native[0]['time'] and math.dist(p['endpoint'],decoded['position'])<.3]
    return {'owned_native_path_to_submitted_destination':len(matched)==1,
        'all_owned_splines_supported':bool(pairs) and all(not p['unsupported'] for p in pairs),
        'all_owned_splines_delivered':bool(pairs) and all(p['client'] is not None for p in pairs)}
