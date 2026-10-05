"""Build only the independent C++ private-input sender."""
import hashlib,json,subprocess
from pathlib import Path
from .. import lab_runtime as lab

SOURCE=lab.REPO/'tools/client_compatibility/native_input'
BUILD=lab.ROOT/'build/native_input'
BINARY=BUILD/'client442_input'
RECEIPT=BUILD/'build_receipt.json'


def source_digest():
    paths=sorted(SOURCE.glob('*.cpp'))+sorted(SOURCE.glob('*.txt'))
    paths += [lab.REPO/'tools/client_compatibility/native_bridge'/n for n in ['json.cpp','json.hpp']]
    digest=hashlib.sha256()
    for p in paths:digest.update(str(p.relative_to(lab.REPO)).encode()+b'\0'+p.read_bytes())
    return digest.hexdigest()


def build():
    with Path('/proc/meminfo').open() as stream:
        available=next(int(line.split()[1]) for line in stream if line.startswith('MemAvailable:'))
    if available<1024*1024:raise RuntimeError('input sender build requires at least 1 GiB available memory')
    include=lab.ROOT/'tools/libei-dev/usr/include/libei-1.0'
    subprocess.run(['cmake','-S',str(SOURCE),'-B',str(BUILD),'-DCMAKE_BUILD_TYPE=Release',
        '-DLIBEI_INCLUDE_DIR='+str(include)],check=True)
    subprocess.run(['cmake','--build',str(BUILD),'-j','1'],check=True)
    receipt={'schema':'client442_native_input_build_v1','engine':'cpp_libei',
        'source_digest':source_digest(),'binary_sha256':lab.sha256(BINARY),
        'libei_header_sha256':lab.sha256(include/'libei.h'),
        'build_jobs':1,'available_memory_kib_before':available,
        'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip()}
    lab.private_write(RECEIPT,json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)


def verified():
    r=json.loads(RECEIPT.read_text())
    if r['source_digest']!=source_digest() or r['binary_sha256']!=lab.sha256(BINARY):
        raise RuntimeError('rebuild the independent native input sender after source/binary changes')
    return BINARY,r


if __name__=='__main__':build()
