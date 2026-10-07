"""Build the current compatibility native server with one memory-guarded job."""
import argparse
import json
import subprocess
import time
from pathlib import Path

from . import lab_runtime as lab
from .interaction_bridge_deploy import identity


def build(output):
    if output.exists() or not output.resolve().is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires new private native build receipt')
    cache = (lab.ROOT / 'build/CMakeCache.txt').read_text()
    if f'CMAKE_HOME_DIRECTORY:INTERNAL={lab.REPO}\n' not in cache:
        raise RuntimeError('native build source is not the current compatibility checkout')
    if subprocess.check_output(['git','status','--porcelain'], cwd=lab.REPO, text=True).strip():
        raise RuntimeError('commit current native experiment source before building')
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])
    if available < 6 * 1024 * 1024:
        raise RuntimeError('one-job native build requires at least 6 GiB available memory')
    binary = lab.ROOT / 'build/src/server/worldserver/worldserver'
    native = identity('worldserver')
    report = {'schema':'client442_native_core_build_v1', 'started_at':time.time(), 'jobs':1,
        'available_memory_kib_before':available, 'native_before':native,
        'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'combat_source_sha256':lab.sha256(lab.REPO/'src/server/game/Handlers/CombatHandler.cpp'),
        'pet_slot_source_sha256':lab.sha256(lab.REPO/'src/server/game/Handlers/PetHandler.cpp'),
        'completed':False}
    lab.private_write(output, json.dumps(report,indent=2)+'\n')
    with output.with_suffix('.log').open('w') as log:
        result = subprocess.run(['cmake','--build',str(lab.ROOT/'build'), '--target','worldserver',
                                 '--parallel','1'],cwd=lab.REPO,stdout=log,stderr=subprocess.STDOUT)
    report.update(finished_at=time.time(), exit_code=result.returncode,
                  binary_sha256=lab.sha256(binary), native_unchanged=identity('worldserver')==native)
    report['completed'] = result.returncode == 0 and report['native_unchanged']
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    if not report['completed']:
        raise RuntimeError('native build failed or changed the live server lifetime')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
