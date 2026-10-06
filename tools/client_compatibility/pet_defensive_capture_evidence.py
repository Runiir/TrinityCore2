"""Fail-closed geometry and rejection checks for a stock Defensive capture."""
from .interaction_pet_follow_capture import follow_request
from .world.gameobjects import modern_guid


def button(probe,pet):
    rows=[r for r in probe.get('actions',[]) if r.get('name')=='PET_MODE_DEFENSIVE'
        and r.get('slot')==9 and r.get('is_token') is True and r.get('available') is True]
    if len(rows)!=1:raise RuntimeError('requires one readable stock Defensive button9')
    row=rows[0];frame=row.get('frame',{})
    from .interaction_pet_command_probe import expected_guid
    if (probe.get('owner_guid')!='Player-1-00000005' or probe.get('pet_guid')!=expected_guid(pet)
        or frame.get('button')!='PetActionButton9'
        or not all(frame.get(k) is True for k in ('available','visible','enabled'))
        or any(type(frame.get(k)) is not int or not 0<=frame[k]<65535 for k in ('x','y'))):
        raise RuntimeError('Defensive button lacks current owned visible enabled geometry')
    return row,[round(frame['x']/65535*1280),round(frame['y']/65535*720)]


def request_checks(requests,pet):
    modern=[p for p in requests if p.get('name')=='CMSG_PET_ACTION' and p.get('direction')=='from_client']
    decoded=follow_request(modern[0]) if len(modern)==1 else None
    return {'one_modern_defensive':bool(decoded and decoded['guid']==list(modern_guid(pet['guid'],pet['map']))
        and decoded['word']==0x03000001 and decoded['target']==[0,0] and decoded['position']==[0.,0.,0.]),
        'no_native_command':not any(p.get('direction')=='to_native' for p in requests),
        'no_abandon':not any(p.get('name')=='CMSG_PET_ABANDON' for p in requests)},decoded
