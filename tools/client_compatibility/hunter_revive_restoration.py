"""Freeze actual living pet stats and prove normal quiet-rest restoration."""
from copy import deepcopy
from .interaction_pet_target import pair
from .interaction_pet_dismiss import vitals
from .world.objects import INDEX


def focus_identity(oracle, class_power_rows, dbc_source):
    fields = oracle.player
    identity = fields.get(INDEX['UNIT_FIELD_BYTES_0'])
    creation = oracle.owner_creation
    rows = sorted([list(r) for r in class_power_rows if r[1] == 3])
    powers = [r[2] for r in rows]
    if (oracle.owner != 6 or identity is None or identity & 255 != 1 or identity >> 8 & 255 != 3 or
        identity >> 24 & 255 != 2 or powers != [2, 10] or not creation or
        creation['object']['guid'] != 6 or creation['object']['fields'].get(INDEX['UNIT_FIELD_BYTES_0']) != identity or
        creation['packet'].get('session') != oracle.session or creation['packet'].get('direction') != 'from_native'):
        raise RuntimeError('actual Hunter focus identity or native class power indexing differs')
    return {'owner': 6, 'race': 1, 'class': 3, 'power_type': 2, 'power_index': 0,
        'power_field': INDEX['UNIT_FIELD_POWER1'], 'max_power_field': INDEX['UNIT_FIELD_MAXPOWER1'],
        'class_power_rows': rows, 'dbc_source': dbc_source, 'identity_packet': deepcopy(creation['packet'])}


def living_snapshot(oracle, guid, owner_vitals):
    pet = oracle.pet
    fields = pet['fields'] if pet else {}
    health, maximum = fields.get(INDEX['UNIT_FIELD_HEALTH'], 0), fields.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0)
    current_owner = vitals(oracle)
    if (not oracle.present() or pet['guid'] != guid or fields.get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or
        fields.get(INDEX['OBJECT_FIELD_ENTRY']) != 299 or pair(fields, 'UNIT_FIELD_SUMMONEDBY') != 6 or
        fields.get(INDEX['UNIT_CREATED_BY_SPELL']) not in (13481, 883) or not 0 < health <= maximum or
        current_owner['UNIT_FIELD_HEALTH'] != owner_vitals['UNIT_FIELD_HEALTH'] or
        current_owner['UNIT_FIELD_MAXHEALTH'] != owner_vitals['UNIT_FIELD_MAXHEALTH'] or
        current_owner['UNIT_FIELD_MAXPOWER1'] != owner_vitals['UNIT_FIELD_MAXPOWER1'] or
        not 0 <= current_owner['UNIT_FIELD_POWER1'] <= current_owner['UNIT_FIELD_MAXPOWER1']):
        raise RuntimeError('living native pet or owner changed during ordinary rest')
    return {'guid': guid, 'health': health, 'max_health': maximum, 'full_health': health == maximum,
        'owner_object_vitals': current_owner}


def restored_maximum(oracle, guid):
    """Bind the final maximum to the actual update, including later aura scaling."""
    pet = oracle.pet
    maximum = pet['fields'].get(INDEX['UNIT_FIELD_MAXHEALTH']) if pet else None
    updates = [r for r in oracle.pet_max_health_updates if r['guid'] == guid]
    source = updates[-1]['packet'] if updates else {}
    if (not oracle.present() or pet['guid'] != guid or not updates or
        source.get('session') != oracle.session or source.get('direction') != 'from_native' or
        source.get('name') != 'SMSG_UPDATE_OBJECT' or
        updates[-1]['max_health'] != maximum or pet['fields'].get(INDEX['UNIT_FIELD_HEALTH']) != maximum):
        raise RuntimeError('full living maximum lacks its actual native stat update')
    return maximum, deepcopy(updates[-1])
