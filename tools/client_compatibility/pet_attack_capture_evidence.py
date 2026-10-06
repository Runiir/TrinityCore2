"""Require an observed owned Attack button and an actual selected passive target."""
from .interaction_pet_command_probe import expected_guid
from .interaction_pet_target import pair
from .world.objects import INDEX


def target_guid(target):
    guid=target['guid']
    return f"Creature-0-1-{target['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"


def target_checks(target,state,owner):
    fields=target.get('fields',{}) if target else {};guid=target.get('guid',0) if target else 0
    expected=target_guid(target) if target else None
    return {'native_dummy_identity':bool(target and target.get('kind')==3 and guid>>52==0xf13
            and guid>>32&0xfffff==44548 and guid&0xffffffff==279984 and target.get('map')==0),
        'living_native_dummy':fields.get(INDEX['UNIT_FIELD_HEALTH'],0)>0,
        'native_selection':bool(guid and pair(owner,'UNIT_FIELD_TARGET')==guid),
        'public_dummy_identity':bool(expected and state.get('target',{}).get('guid')==expected
            and state['target'].get('name')=='Training Dummy' and state['target'].get('visible') is True),
        'public_dummy_health':bool(fields.get(INDEX['UNIT_FIELD_HEALTH'],0)>0 and
            state.get('target',{}).get('health')==fields.get(INDEX['UNIT_FIELD_HEALTH']) and
            state['target'].get('max_health')==fields.get(INDEX['UNIT_FIELD_MAXHEALTH']))}


def button(probe,pet):
    rows=[r for r in probe.get('actions',[]) if r.get('slot')==1 and r.get('name')=='PET_ACTION_ATTACK']
    if len(rows)!=1:raise RuntimeError('observed stock Attack button is absent or ambiguous')
    row=rows[0];frame=row.get('frame',{})
    if (probe.get('owner_guid')!='Player-1-00000005' or probe.get('pet_guid')!=expected_guid(pet) or
        probe.get('modified_click') is not False or row.get('usable') is not True or
        row.get('available') is not True or row.get('is_token') is not True or
        frame.get('button')!='PetActionButton1' or
        not all(frame.get(k) is True for k in ('available','visible','enabled')) or
        any(type(frame.get(k)) is not int or not 0<=frame[k]<65535 for k in ('x','y'))):
        raise RuntimeError('current owned usable Attack control or geometry differs')
    return row,[round(frame['x']/65535*1280),round(frame['y']/65535*720)]
