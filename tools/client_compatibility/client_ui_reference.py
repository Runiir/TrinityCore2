"""Pin public UI sources from the installed 60895 CASC without online flags."""
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import PurePosixPath
from . import lab_runtime as lab


def extract(paths):
    if '4.4.2.60895' not in (lab.BASE.parent/'.build.info').read_text():
        raise RuntimeError('require the pinned installed client build')
    for path in paths:
        name=PurePosixPath(path)
        if not path.startswith('Interface/') or '..' in name.parts or name.suffix not in ['.lua','.xml','.toc']:
            raise ValueError('require a public Interface source path')
    lib=ct.CDLL(str(lab.ROOT/'tools/CascLib-build/libcasc.so.1.0.0'));handle=ct.c_void_p
    lib.CascOpenStorage.argtypes=[ct.c_char_p,ct.c_uint32,ct.POINTER(handle)];lib.CascOpenStorage.restype=ct.c_bool
    lib.CascOpenFile.argtypes=[handle,ct.c_char_p,ct.c_uint32,ct.c_uint32,ct.POINTER(handle)];lib.CascOpenFile.restype=ct.c_bool
    lib.CascGetFileSize.argtypes=[handle,ct.POINTER(ct.c_uint32)];lib.CascGetFileSize.restype=ct.c_uint32
    lib.CascReadFile.argtypes=[handle,ct.c_void_p,ct.c_uint32,ct.POINTER(ct.c_uint32)];lib.CascReadFile.restype=ct.c_bool
    lib.CascCloseFile.argtypes=[handle];lib.CascCloseStorage.argtypes=[handle]
    storage=handle()
    # Locale enUS, existing local storage, strict data checks. No download flags.
    if not lib.CascOpenStorage(str(lab.BASE.parent).encode(),2,ct.byref(storage)):
        raise RuntimeError('local public storage is unavailable')
    try:
        for path in paths:
            file=handle()
            if not lib.CascOpenFile(storage,path.encode(),2,16,ct.byref(file)):
                print(json.dumps({'path':path,'present':False}),flush=True);continue
            try:
                size=lib.CascGetFileSize(file,None)
                if not 0<size<2_000_000:raise RuntimeError('public source exceeds bound')
                data=ct.create_string_buffer(size);count=ct.c_uint32()
                if not lib.CascReadFile(file,data,size,ct.byref(count)) or count.value!=size:
                    raise RuntimeError('public source failed strict local read')
                out=lab.ROOT/'reference/local-60895/ui'/path
                if out.exists() and out.read_bytes()!=data.raw:
                    raise RuntimeError('preserve a differently pinned existing source')
                out.parent.mkdir(exist_ok=True,parents=True);out.write_bytes(data.raw)
                record={'build':60895,'path':path,'sha256':hashlib.sha256(data.raw).hexdigest(),
                    'source':'local_read_only_CASC'}
                lab.private_write(out.with_name(out.name+'.source.json'),json.dumps(record)+'\n')
                print(json.dumps(record),flush=True)
            finally:lib.CascCloseFile(file)
    finally:lib.CascCloseStorage(storage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('paths',nargs='+')
    extract(p.parse_args().paths)
