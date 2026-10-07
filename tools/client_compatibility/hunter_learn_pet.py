"""Pure normal Hunter login pet creation and scaling sequence for Wolf16."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct

from .hunter_learn_contract import require
from .world.native_objects import records

_fields = Path(__file__).with_name('world') / 'native_fields.json'
require(hashlib.sha256(_fields.read_bytes()).hexdigest() ==
    '15b87e3f3142d8292cce49c138e46bab167bd86606f9cda1f6c345994ef16b9a', 'native pet field schema differs')
INDEX = json.loads(_fields.read_text())


def pair(fields, name):
    offset = INDEX[name]
    return fields.get(offset, 0) | fields.get(offset + 1, 0) << 32


def packet_key(p):
    return tuple(p.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


def reload_proof(rows, session, since, until, baseline_pet):
    require(tuple(baseline_pet.get(k) for k in ('id', 'owner', 'entry', 'CreatedBySpell', 'level', 'curhealth', 'slot', 'active')) ==
        (16, 6, 299, 13481, 10, 278, 0, 1), 'normal learning login requires the exact normalized Wolf16')
    scoped = [p for p in rows if p.get('session') == session and since <= p.get('time', 0) <= until]
    scoped.sort(key=lambda p: p['time'])
    creations = []
    for packet in scoped:
        if packet.get('direction') != 'from_native' or packet.get('name') != 'SMSG_UPDATE_OBJECT':
            continue
        for obj in records(bytes.fromhex(packet['body'])):
            f = obj.get('fields', {})
            if (obj.get('kind') == 3 and f.get(INDEX['UNIT_FIELD_PETNUMBER']) == 16 and
                pair(f, 'UNIT_FIELD_SUMMONEDBY') == pair(f, 'UNIT_FIELD_CREATEDBY') == 6):
                creations.append({'packet': packet, 'object': obj})
    require(len(creations) == 1, 'one attributed native disposable pet creation is required')
    creation = creations[0]
    obj = creation['object']
    guid = obj['guid']
    fields = deepcopy(obj['fields'])
    initial_max = fields.get(INDEX['UNIT_FIELD_MAXHEALTH'])
    initial_health = fields.get(INDEX['UNIT_FIELD_HEALTH'])
    require(guid >> 52 == 0xf14 and fields.get(INDEX['UNIT_CREATED_BY_SPELL']) == 13481 and
        fields.get(INDEX['OBJECT_FIELD_ENTRY']) == 299 and fields.get(INDEX['UNIT_FIELD_LEVEL']) == 10 and
        initial_max == 198 and initial_health == min(baseline_pet['curhealth'], initial_max),
        'normal LoadPet creation, pre-scaling clamp or identity differs')
    updates = []
    owner = {}
    for packet in scoped:
        if packet.get('direction') != 'from_native':
            continue
        if packet.get('name') == 'SMSG_DESTROY_OBJECT':
            body = bytes.fromhex(packet['body'])
            require(len(body) >= 8 and struct.unpack_from('<Q', body)[0] != guid,
                'normal learned-unit pet was destroyed')
        if packet.get('name') != 'SMSG_UPDATE_OBJECT':
            continue
        touched = False
        for update in records(bytes.fromhex(packet['body'])):
            require(guid not in update.get('removed', []), 'normal learned-unit pet was removed')
            if update.get('guid') == 6:
                owner.update(update.get('fields', {}))
                if INDEX['UNIT_FIELD_SUMMON'] in update.get('fields', {}) or INDEX['UNIT_FIELD_SUMMON'] + 1 in update.get('fields', {}):
                    touched = True
            if update.get('guid') != guid or packet_key(packet) == packet_key(creation['packet']):
                continue
            require(packet['time'] >= creation['packet']['time'] and update.get('update_type') == 0,
                'normal learned-unit pet was recreated')
            changed = update.get('fields', {})
            require(changed.get(INDEX['UNIT_FIELD_HEALTH'], initial_health) in (initial_health, 278) and
                changed.get(INDEX['UNIT_FIELD_MAXHEALTH'], initial_max) in (initial_max, 278) and
                changed.get(INDEX['UNIT_CREATED_BY_SPELL'], 13481) == 13481,
                'normal login pet health or creator changed beyond native scaling')
            fields.update(changed)
            touched = True
        if touched:
            updates.append(packet)
    require(fields.get(INDEX['UNIT_FIELD_HEALTH']) == fields.get(INDEX['UNIT_FIELD_MAXHEALTH']) == 278 and
        fields.get(INDEX['UNIT_CREATED_BY_SPELL']) == 13481 and pair(owner, 'UNIT_FIELD_SUMMON') == guid and
        not any(p.get('direction') == 'to_native' and p.get('name') in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in scoped),
        'normal pet scaling did not reach278/278 without pet input')
    return {'owner': 6, 'pet_number': 16, 'created_by_spell': 13481, 'health': 278, 'max_health': 278,
        'initial_health': initial_health, 'initial_max_health': initial_max, 'native_reload_source_verified': True,
        'packet': creation['packet'], 'object': obj, 'update_packets': updates, 'final_fields': fields,
        'native_pet_guid': guid, 'native_owner_summon': pair(owner, 'UNIT_FIELD_SUMMON')}
