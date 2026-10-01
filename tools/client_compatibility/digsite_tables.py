"""Read public 60895 digsite DB2 files and prepare isolated legacy boundaries.

WDC5 layouts follow wowdev/WoWDBDefs and wowdev/DBCD. This bounded reader
rejects sparse, encrypted, multi-section and copy-table data rather than
silently treating unsupported rows as coordinates.
"""
import argparse
import ctypes as ct
import json
import struct
from pathlib import Path
from . import lab_runtime as lab
from .observation.map_data import catalog

TABLES = {'ResearchSite': (1134091, 0xBD957EAB),
          'QuestPOIBlob': (1251882, 0xFDC814CF),
          'QuestPOIPoint': (1251883, 0x5CBBEFE7)}


def read(path):
    data = path.read_bytes()
    if data[:8] != b'WDC5\x05\0\0\0': raise ValueError('unsupported DB2 schema')
    h = struct.unpack_from('<9I2H7I', data, 136)
    count, fields, width, strings, table_hash, layout = h[:6]
    if layout != TABLES[path.stem][1] or h[-1] != 1 or h[9] & ~4:
        raise ValueError('unsupported digsite DB2 layout or flags')
    key, base, rows, text_size, sparse_end, ids_size, relations_size, sparse_ids, copies = struct.unpack_from('<Q8I', data, 204)
    if key or sparse_end or sparse_ids or copies or rows != count or text_size != strings:
        raise ValueError('unsupported DB2 section')
    off = 244
    meta = [struct.unpack_from('<hH', data, off+4*i) for i in range(fields)]
    off += 4*fields
    cols = [struct.unpack_from('<HH5I', data, off+24*i) for i in range(fields)]
    off += 24*fields
    palettes = {}
    for i, col in enumerate(cols):
        if col[3] == 3:
            palettes[i] = struct.unpack_from('<'+'I'*(col[2]//4), data, off)
            off += col[2]
        elif col[3] not in (0, 1, 2, 5) or col[2]:
            raise ValueError('unsupported DB2 field compression')
    if off != base: raise ValueError('unexpected DB2 record offset')
    tail = base + rows*width + text_size
    ids = struct.unpack_from('<'+'I'*(ids_size//4), data, tail)
    if ids_size not in (0, count*4): raise ValueError('invalid DB2 ID list')
    tail += ids_size
    relations = {}
    if relations_size:
        relation_count = struct.unpack_from('<I', data, tail)[0]
        if relations_size != 12+8*relation_count: raise ValueError('invalid relationship size')
        for i in range(relation_count):
            value, index = struct.unpack_from('<II', data, tail+12+8*i)
            if index in relations or index >= rows: raise ValueError('invalid relationship index')
            relations[index] = value
    if tail+relations_size != len(data): raise ValueError('unexpected DB2 trailing data')
    result = []
    for index in range(rows):
        pos = base+width*index
        bits = int.from_bytes(data[pos:pos+width], 'little')
        values = []
        for i, (offset, size, extra, compression, a, bw, c) in enumerate(cols):
            if compression == 2: value = a
            else:
                if not size or offset+size > width*8: raise ValueError('invalid packed field')
                value = (bits >> offset) & ((1 << size)-1)
                if compression == 5 and value & (1 << (size-1)): value -= 1 << size
                elif compression == 3: value = palettes[i][value]
            if path.stem == 'ResearchSite' and i == 0:
                address = pos + value
                if not base+rows*width <= address < base+rows*width+text_size:
                    raise ValueError('name outside string table')
                value = data[address:data.index(b'\0', address)].decode('utf-8')
            values.append(value)
        if ids: values.insert(h[10], ids[index])
        if relations_size: values.append(relations[index])
        result.append(values)
    if len({r[0] for r in result}) != count: raise ValueError('duplicate DB2 row ID')
    return result


def extract(directory, library):
    build_info = lab.BASE.parent/'.build.info'
    if '4.4.2.60895' not in build_info.read_text(): raise ValueError('wrong local client build')
    lib = ct.CDLL(str(library))
    handle = ct.c_void_p
    lib.CascOpenStorage.argtypes = [ct.c_char_p, ct.c_uint32, ct.POINTER(handle)]
    lib.CascOpenStorage.restype = ct.c_bool
    lib.CascOpenFile.argtypes = [handle, handle, ct.c_uint32, ct.c_uint32, ct.POINTER(handle)]
    lib.CascOpenFile.restype = ct.c_bool
    lib.CascGetFileSize.argtypes = [handle, ct.POINTER(ct.c_uint32)]
    lib.CascGetFileSize.restype = ct.c_uint32
    lib.CascReadFile.argtypes = [handle, ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_uint32)]
    lib.CascReadFile.restype = ct.c_bool
    lib.CascCloseFile.argtypes = [handle]
    lib.CascCloseStorage.argtypes = [handle]
    storage = handle()
    # Local read only. No online/download flags, build updates or client keys.
    if not lib.CascOpenStorage(str(lab.BASE.parent).encode(), 2, ct.byref(storage)):
        raise RuntimeError('CASC open failed: '+str(lib.GetCascError()))
    directory.mkdir(parents=True, exist_ok=True)
    try:
        for name, (file_id, _) in TABLES.items():
            file = handle()
            if not lib.CascOpenFile(storage, handle(file_id), 2, 3|16, ct.byref(file)):
                raise RuntimeError('missing local public table: '+name)
            try:
                size = lib.CascGetFileSize(file, None)
                if not 200 < size < 2_000_000: raise ValueError('unexpected table size')
                data = ct.create_string_buffer(size); received = ct.c_uint32()
                if not lib.CascReadFile(file, data, size, ct.byref(received)) or received.value != size:
                    raise RuntimeError('CASC table read failed: '+name)
                (directory/(name+'.db2')).write_bytes(data.raw)
            finally: lib.CascCloseFile(file)
    finally: lib.CascCloseStorage(storage)


def compare(directory):
    sites, blobs, points = [read(directory/(n+'.db2')) for n in TABLES]
    polygons = {}
    for r in points: polygons.setdefault(r[-1], []).append(r[1:3])
    native = catalog(lab.BASE/'data/dbc/enUS')['sites']; modern = {}; mismatches = []
    for sid, name, map_id, blob, icon in sites:
        polygon = polygons.get(blob, [])
        if len(polygon) < 3: continue
        modern[sid] = {'id': sid, 'name': name, 'map': map_id, 'poi_blob': blob, 'polygon': polygon}
        if sid in native:
            old = native[sid]
            if old['map'] != map_id or old['poi_blob'] != blob: raise ValueError('digsite identity changed')
            if old['polygon'] != polygon:
                mismatches.append({'id': sid, 'name': name, 'old_polygon': old['polygon'], 'client_polygon': polygon})
    missing = sorted(set(native)-set(modern))
    if missing: raise ValueError('native sites absent from client: '+str(missing))
    return {'schema': 'client442_digsite_boundary_comparison_v1', 'client_build': 60895,
            'client_tables': {n: {'sha256': lab.sha256(directory/(n+'.db2')), 'file_data_id': TABLES[n][0]} for n in TABLES},
            'native_sites': len(native), 'client_sites': len(modern), 'mismatches': mismatches,
            'sites': modern, 'native_point_sha256': lab.sha256(lab.BASE/'data/dbc/enUS/QuestPOIPoint.dbc')}


def prepare(directory):
    receipt = compare(directory)
    client_points = {r[0]: r for r in read(directory/'QuestPOIPoint.db2')}
    source = lab.BASE/'data'; target = lab.ROOT/'data'
    target.mkdir(exist_ok=True)
    for path in source.iterdir():
        if path.name != 'dbc' and not (target/path.name).exists(): (target/path.name).symlink_to(path)
    for path in (source/'dbc').rglob('*'):
        destination = target/'dbc'/path.relative_to(source/'dbc')
        if path.is_dir(): destination.mkdir(parents=True, exist_ok=True)
        elif path.name != 'QuestPOIPoint.dbc' and not destination.exists(): destination.symlink_to(path)
    # Preserve the native layout and unrelated POIs. Replace only coordinates
    # of archaeology point IDs, after checking the blob association.
    data = bytearray((source/'dbc/enUS/QuestPOIPoint.dbc').read_bytes())
    magic, rows, fields, width, _ = struct.unpack_from('<4s4I', data)
    if magic != b'WDBC' or fields != 4 or width != 16: raise ValueError('unexpected legacy point layout')
    changed = 0
    for i in range(rows):
        row_id, x, y, blob = struct.unpack_from('<IiiI', data, 20+i*width)
        if row_id not in client_points: continue
        modern = client_points[row_id]
        if modern[-1] != blob: raise ValueError('point changed blob association')
        if (x, y) != tuple(modern[1:3]):
            struct.pack_into('<ii', data, 24+i*width, *modern[1:3]); changed += 1
    destination = target/'dbc/enUS/QuestPOIPoint.dbc'
    if destination.is_symlink(): raise ValueError('refusing to overwrite a shared DBC')
    destination.write_bytes(data)
    receipt.update(changed_points=changed, isolated_data_directory=str(target),
                   corrected_point_sha256=lab.sha256(destination))
    lab.private_write(directory/'comparison.json', json.dumps(receipt, indent=2)+'\n')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--casc-library', type=Path)
    p.add_argument('--prepare', action='store_true')
    a = p.parse_args()
    if a.casc_library: extract(a.directory, a.casc_library)
    result = prepare(a.directory) if a.prepare else compare(a.directory)
    print(json.dumps({k: v for k, v in result.items() if k not in ('sites', 'mismatches')}, indent=2))


if __name__ == '__main__': main()
