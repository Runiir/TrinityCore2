"""Pin two public installed spell tables, using local CASC without downloads."""
import argparse
import ctypes as ct
import json
import struct
from pathlib import Path
from . import lab_runtime as lab


TABLES = {'SpellEffect': 0x7F31EDF7, 'SkillLineAbility': 0x738BFEE1}


def extract(directory):
    directory = directory.resolve()
    if not directory.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require an owned evidence destination')
    if '4.4.2.60895' not in (lab.BASE.parent/'.build.info').read_text():
        raise RuntimeError('require installed build60895')
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    lib = ct.CDLL(str(lab.ROOT/'tools/CascLib-build/libcasc.so.1.0.0'))
    handle = ct.c_void_p
    lib.CascOpenStorage.argtypes = [ct.c_char_p, ct.c_uint32, ct.POINTER(handle)]
    lib.CascOpenStorage.restype = ct.c_bool
    lib.CascOpenFile.argtypes = [handle, ct.c_char_p, ct.c_uint32, ct.c_uint32, ct.POINTER(handle)]
    lib.CascOpenFile.restype = ct.c_bool
    lib.CascGetFileSize.argtypes = [handle, ct.POINTER(ct.c_uint32)]
    lib.CascGetFileSize.restype = ct.c_uint32
    lib.CascReadFile.argtypes = [handle, ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_uint32)]
    lib.CascReadFile.restype = ct.c_bool
    lib.CascCloseFile.argtypes = [handle]
    lib.CascCloseStorage.argtypes = [handle]
    storage = handle()
    # Existing local enUS storage only; strict data verification, no online flags.
    if not lib.CascOpenStorage(str(lab.BASE.parent).encode(), 2, ct.byref(storage)):
        raise RuntimeError('local public CASC storage is unavailable')
    try:
        for name, layout in TABLES.items():
            source = 'DBFilesClient/'+name+'.db2';file = handle()
            if not lib.CascOpenFile(storage, source.encode(), 2, 16, ct.byref(file)):
                raise RuntimeError('local public table is absent: '+name)
            try:
                size = lib.CascGetFileSize(file, None)
                if not 244 <= size < 64_000_000:
                    raise RuntimeError('public table exceeds its bounded size')
                data = ct.create_string_buffer(size);received = ct.c_uint32()
                if not lib.CascReadFile(file, data, size, ct.byref(received)) or received.value != size:
                    raise RuntimeError('strict public table read failed: '+name)
                if data.raw[:8] != b'WDC5\x05\0\0\0':
                    raise RuntimeError('unexpected installed table schema')
                header = struct.unpack_from('<9I2H7I', data.raw, 136)
                if header[5] != layout:
                    raise RuntimeError('installed table layout differs from pinned60895 definition')
                out = directory/(name+'.db2');out.write_bytes(data.raw)
                record = {'build':60895, 'source':'local_read_only_CASC', 'path':source,
                    'bytes':size, 'sha256':lab.sha256(out), 'layout':hex(layout),
                    'header':list(header), 'limits':'Static base table only; no client hotfix replay or gameplay.'}
                lab.private_write(directory/(name+'.source.json'), json.dumps(record, indent=2)+'\n')
                print(json.dumps(record), flush=True)
            finally:
                lib.CascCloseFile(file)
    finally:
        lib.CascCloseStorage(storage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    extract(parser.parse_args().directory)
