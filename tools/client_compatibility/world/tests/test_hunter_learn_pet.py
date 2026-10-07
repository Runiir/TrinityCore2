"""Normal login clamps the same pet before scaling; no Call Pet or health grant."""
from copy import deepcopy
import struct

import pytest

from tools.client_compatibility import hunter_learn_pet as pet
from tools.client_compatibility.hunter_learn_pet import INDEX

GUID = (0xf14 << 52) | (299 << 32) | 16


def fixture(monkeypatch):
    base = {'id': 16, 'owner': 6, 'entry': 299, 'CreatedBySpell': 13481,
        'level': 10, 'curhealth': 278, 'slot': 0, 'active': 1}
    fields = {INDEX[k]: v for k, v in {'UNIT_FIELD_PETNUMBER': 16, 'UNIT_CREATED_BY_SPELL': 13481,
        'OBJECT_FIELD_ENTRY': 299, 'UNIT_FIELD_LEVEL': 10, 'UNIT_FIELD_MAXHEALTH': 198,
        'UNIT_FIELD_HEALTH': 198, 'UNIT_FIELD_SUMMONEDBY': 6, 'UNIT_FIELD_CREATEDBY': 6}.items()}
    objects = {b'\x01': [{'guid': GUID, 'kind': 3, 'update_type': 2, 'fields': fields}],
        b'\x02': [{'guid': 6, 'update_type': 0, 'fields': {INDEX['UNIT_FIELD_SUMMON']: GUID & 0xffffffff,
            INDEX['UNIT_FIELD_SUMMON'] + 1: GUID >> 32}},
            {'guid': GUID, 'update_type': 0, 'fields': {INDEX['UNIT_FIELD_HEALTH']: 278, INDEX['UNIT_FIELD_MAXHEALTH']: 278}}]}
    rows = [{'session': 'hunter', 'time': 10 + n * .1, 'direction': 'from_native',
        'name': 'SMSG_UPDATE_OBJECT', 'body': bytes([n]).hex()} for n in (1, 2)]
    monkeypatch.setattr(pet, 'records', lambda body: objects[body])
    return base, objects, rows


def test_normal_login_replays_one_creation_then_same_guid_scaling(monkeypatch):
    base, objects, rows = fixture(monkeypatch)
    value = pet.reload_proof(rows, 'hunter', 10, 11, base)
    assert value['initial_health'] == value['initial_max_health'] == 198
    assert value['health'] == value['max_health'] == 278 and value['created_by_spell'] == 13481
    assert value['native_owner_summon'] == GUID and len(value['update_packets']) == 1


def test_separate_owner_summon_packet_is_retained_for_local_rederivation(monkeypatch):
    base, objects, rows = fixture(monkeypatch)
    objects[b'\x03'] = [objects[b'\x02'].pop(0)]
    rows.append({**rows[-1], 'body': '03', 'time': 10.3})
    value = pet.reload_proof(rows, 'hunter', 10, 11, base)
    assert [p['body'] for p in value['update_packets']] == ['02', '03']
    assert pet.reload_proof([value['packet'], *value['update_packets']], 'hunter', 10, 11, base) == value


@pytest.mark.parametrize('fault', ['already_scaled_creation', 'other_initial_max', 'duplicate_creation',
    'removed', 'destroyed', 'call_creator', 'wrong_final_health', 'missing_scaling', 'foreign_session', 'pet_cast', 'owner_link'])
def test_reload_refuses_other_pet_health_lifecycle_or_call_input(monkeypatch, fault):
    base, objects, rows = fixture(monkeypatch)
    creation = objects[b'\x01'][0]['fields']
    final = objects[b'\x02'][1]['fields']
    if fault == 'already_scaled_creation': creation[INDEX['UNIT_FIELD_HEALTH']] = 278
    elif fault == 'other_initial_max': creation[INDEX['UNIT_FIELD_MAXHEALTH']] = 197
    elif fault == 'duplicate_creation': objects[b'\x02'].append(deepcopy(objects[b'\x01'][0]))
    elif fault == 'removed': objects[b'\x02'].append({'removed': [GUID]})
    elif fault == 'destroyed': rows.append({**rows[1], 'name': 'SMSG_DESTROY_OBJECT', 'body': struct.pack('<Q', GUID).hex()})
    elif fault == 'call_creator': final[INDEX['UNIT_CREATED_BY_SPELL']] = 883
    elif fault == 'wrong_final_health': final[INDEX['UNIT_FIELD_HEALTH']] = 279
    elif fault == 'missing_scaling': objects[b'\x02'].pop()
    elif fault == 'foreign_session': rows[0]['session'] = 'foreign'
    elif fault == 'pet_cast': rows.append({**rows[1], 'direction': 'to_native', 'name': 'CMSG_CAST_SPELL', 'body': '00'})
    else: objects[b'\x02'].pop(0)
    with pytest.raises(RuntimeError): pet.reload_proof(rows, 'hunter', 10, 11, base)
