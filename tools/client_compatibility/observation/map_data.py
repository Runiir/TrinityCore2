"""Public static map, digsite boundary and flight-node metadata from native DBC.

These are client table records. This module never queries archaeology's private
next-find coordinates or selects a digsite on behalf of the decision model.
"""
import struct
from pathlib import Path
from .. import lab_runtime as lab

DBC = lab.BASE / 'data/dbc/enUS'


def table(name):
    data = (DBC / (name + '.dbc')).read_bytes()
    magic, count, fields, width, strings_size = struct.unpack_from('<4s4I', data)
    if magic != b'WDBC' or width != fields * 4 or len(data) != 20 + count * width + strings_size:
        raise ValueError('unexpected DBC layout: ' + name)
    strings = data[20 + count * width:]
    rows = [struct.unpack_from('<' + 'I' * fields, data, 20 + index * width) for index in range(count)]
    def text(offset):
        return strings[offset:strings.find(b'\0', offset)].decode('utf-8')
    return rows, text


def floating(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def signed(bits):
    return bits - 2**32 if bits >= 2**31 else bits


def catalog():
    blobs, _ = table('QuestPOIBlob')
    blob_map = {r[0]: {'map': r[2], 'world_map_area': r[3]} for r in blobs}
    points, _ = table('QuestPOIPoint')
    polygons = {}
    for r in points: polygons.setdefault(r[3], []).append([signed(r[1]), signed(r[2])])
    sites, text = table('ResearchSite')
    site_map = {}
    for r in sites:
        polygon = polygons.get(r[2], [])
        if not polygon: continue
        site_map[r[0]] = {'id': r[0], 'map': r[1], 'name': text(r[3]), 'poi_blob': r[2],
            'polygon': polygon, 'world_map_area': blob_map[r[2]]['world_map_area'],
            'center': [sum(p[i] for p in polygon)/len(polygon) for i in range(2)],
            'source': 'ResearchSite/QuestPOIBlob/QuestPOIPoint.dbc'}
    nodes, text = table('TaxiNodes')
    taxi = {r[0]: {'id': r[0], 'map': r[1], 'position': [floating(v) for v in r[2:5]],
        'name': text(r[5]), 'flags': r[8], 'mounts': list(r[6:8])} for r in nodes}
    paths, _ = table('TaxiPath')
    areas, text = table('WorldMapArea')
    maps = {r[0]: {'id': r[0], 'map': r[1], 'area': r[2], 'name': text(r[3]),
        'bounds': [floating(v) for v in r[4:8]]} for r in areas}
    names = ['ResearchSite', 'QuestPOIBlob', 'QuestPOIPoint', 'TaxiNodes', 'TaxiPath', 'WorldMapArea']
    return {'schema': 'client442_public_map_catalog_v1', 'native_build': 15595, 'sites': site_map,
        'taxi_nodes': taxi, 'taxi_paths': [dict(zip(['id','source','destination','cost'], r)) for r in paths],
        'world_map_areas': maps, 'sources': {name: lab.sha256(DBC/(name+'.dbc')) for name in names}}


def mount_spells():
    """Learnable mount-skill spells matching the owned human warrior's masks."""
    abilities, _ = table('SkillLineAbility')
    effects, _ = table('SpellEffect')
    mounted = {r[24] for r in effects if r[1] == 6 and r[3] == 78}
    return sorted({r[2] for r in abilities if r[1] == 777 and r[2] in mounted
        and (not r[3] or r[3] & 1) and (not r[4] or r[4] & 1)})
