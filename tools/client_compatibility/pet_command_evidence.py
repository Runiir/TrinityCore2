"""Keep command admission, public range change and native motion independent."""
import math,struct
from .interaction_pet_follow_capture import follow_request
from .interaction_pet_command_probe import follow_row,expected_guid
from .pet_movement_evidence import following_paths
from .world.gameobjects import modern_guid


def command_checks(requests,pet,command):
    modern=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='from_client']
    native=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='to_native']
    decoded=follow_request(modern[0]) if len(modern)==1 else None
    expected=struct.pack('<QIQfff',pet['guid'],0x07000000|command,0,0,0,0).hex()
    return {'one_owned_modern_command':bool(decoded and decoded['guid']==list(modern_guid(pet['guid'],pet['map']))
        and decoded['word']==0x03800000|command and decoded['target']==[0,0] and decoded['position']==[0.,0.,0.]),
        'one_exact_native_command':len(modern)==1 and len(native)==1 and native[0]['body']==expected
            and 0<=native[0]['time']-modern[0]['time']<2,
        'no_abandon':not any(r['name']=='CMSG_PET_ABANDON' for r in requests)}


def range_state(probe,wanted):
    return all(sum(r.get('index')==i and r.get('available') is True and r.get('in_range') is wanted
        for r in probe.get('interaction_ranges',[]))==1 for i in (2,3))


def public_checks(sample,pet,following,near):
    p=sample['probe'];row=follow_row(p)
    return {'public_owned_pet':p.get('pet_guid')==expected_guid(pet) and p.get('owner_guid')=='Player-1-00000005',
        'public_follow_selected':bool(row and row.get('active') is following),
        'public_pet_range':range_state(p,near),'public_pet_visible':p.get('pet_visible') is True,
        'public_pet_idle':p.get('pet_speed')==0,'public_owner_idle':p.get('player_speed')==0,
        'public_ui_clean':sample['ui_clean']}


def stay_motion_checks(pairs,near,far,owner_before,owner_after):
    return {'owner_separated':10<math.dist(owner_before[:2],owner_after[:2])<18,
        'public_range_changed_to_far':range_state(near,True) and range_state(far,False),
        'native_pet_did_not_follow':not following_paths(pairs),
        'owned_splines_supported':all(not p['unsupported'] for p in pairs),
        'owned_splines_delivered':all(p['client'] is not None for p in pairs)}


def follow_range_checks(pairs,far,near,owner_position):
    paths=following_paths(pairs)
    return {'owned_native_moving_path':bool(paths),
        'owned_splines_supported':bool(pairs) and all(not p['unsupported'] for p in pairs),
        'owned_splines_delivered':bool(pairs) and all(p['client'] is not None for p in pairs),
        'native_endpoint_near_owner':bool(paths) and math.dist(paths[-1]['endpoint'],owner_position[:3])<4,
        'public_range_changed_to_near':range_state(far,False) and range_state(near,True)}
