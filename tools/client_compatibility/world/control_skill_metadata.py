"""Convert four pinned native class-skill records without teaching any spell."""
import hashlib
import json
import struct
from .. import lab_runtime as lab


TABLE = 0xFF4446F6
FORMAT = '<QIHIHIIIHHIBHHH2I'
SPECS = ((21975,354,80388,256),(23872,354,93375,256),(21959,50,79682,4),(23785,50,93321,4))


def convert(native, config):
    if (config.get('schema') != 'client442_control_skill_metadata_v1' or
        config.get('client_build') != 60895 or config.get('native_build') != 15595 or
        config.get('table_hash') != TABLE or config.get('layout_hash') != '738BFEE1' or
        len(native) > 16*1024*1024 or
        hashlib.sha256(native).hexdigest() != config.get('native_source_sha256')):
        raise ValueError('native control skill source or pinned layout differs')
    if len(native) < 20:
        raise ValueError('truncated native control skill header')
    magic, count, fields, width, strings = struct.unpack_from('<4s4I', native)
    if (magic != b'WDBC' or fields != 14 or width != 56 or count > 100000 or
        len(native) != 20+count*width+strings):
        raise ValueError('invalid native control skill DBC boundary')
    source = {}
    for index in range(count):
        values = list(struct.unpack_from('<14I', native, 20+index*width))
        if values[0] in {row[0] for row in SPECS}:
            if values[0] in source:
                raise ValueError('duplicate native control skill record')
            source[values[0]] = values
    records = config.get('records', [])
    if len(source) != len(SPECS) or len(records) != len(SPECS):
        raise ValueError('native control skill allowlist differs')
    rows = []
    for index, (record, skill, spell, class_mask) in enumerate(SPECS):
        spec = records[index];v = source[record];push = 60895004+index
        if (spec.get('record_id') != record or spec.get('push_id') != push or
            spec.get('unique_id') != push or spec.get('native_values') != v or
            v != [record, skill, spell, 0, class_mask, 0, 0, 1, 0, 0, 0, 0, 0, 0]):
            raise ValueError('native control skill identity or semantics differs')
        payload = struct.pack(FORMAT, v[3], v[0], v[1], v[2], v[7], v[4], v[8], v[9],
            v[10], v[11], 0, v[12], v[13], 0, 0, 0, 0)
        rows.append({'push_id':push, 'unique_id':push, 'table_hash':TABLE,
            'record_id':record, 'data':payload.hex()})
    return rows


def records():
    path = lab.ROOT/'data/dbc/enUS/SkillLineAbility.dbc'
    if path.stat().st_size > 16*1024*1024:
        raise ValueError('native control skill table exceeds bound')
    config = json.loads((lab.REPO/'experiments/configs/client_harness/control_skill_metadata_v1.json').read_text())
    return convert(path.read_bytes(), config)
