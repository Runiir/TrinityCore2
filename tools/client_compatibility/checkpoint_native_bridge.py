"""Checkpoint closed C++ bridge trials, safe journals and compatibility inventories."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from dvclive import Live
from . import lab_runtime as lab
from .observation.journal import entries


def checkpoint(name,since):
    if not re.fullmatch(r'[A-Za-z0-9_]+',name):raise ValueError('invalid checkpoint name')
    if subprocess.check_output(['git','status','--porcelain'],cwd=lab.REPO,text=True):
        raise RuntimeError('commit experiment code/configuration before checkpointing')
    target=lab.REPO/'artifacts/client_harness'/(name+'.tar.gz')
    if target.exists() or Path(str(target)+'.dvc').exists():raise ValueError('checkpoint already exists')
    paths=sorted((lab.ROOT/'evidence').glob('cpp_*'))
    for path in paths:
        for receipt in [path/'episode.json',path/'cohort.json'] if path.is_dir() else []:
            if receipt.exists() and not json.loads(receipt.read_text()).get('finished_at'):
                raise RuntimeError('cannot archive an open run: '+str(receipt))
    paths+=sorted((lab.ROOT/'evidence').glob('native_bridge_*.xml'))
    paths+=sorted((lab.ROOT/'evidence').glob('coverage_*failure.xml'))
    paths+=[lab.ROOT/'evidence/cohort_focus_race_tests.xml',
        lab.ROOT/'evidence/native_bridge_self_check.json',
        lab.ROOT/'evidence/native_content_census_20261002.json.gz',
        lab.ROOT/'evidence/compatibility_inventory_20261002.json']
    paths+=[lab.ROOT/f'build/{directory}/build_receipt.json' for directory in ['native_bridge','native_bridge_asan']]
    tests=ET.parse(lab.ROOT/'evidence/native_bridge_final_full_tests.xml').getroot()
    suites=list(tests.iter('testsuite'))
    passed=sum(int(s.attrib['tests'])-int(s.attrib.get('failures',0))-int(s.attrib.get('errors',0)) for s in suites)
    cohort=json.loads((lab.ROOT/'evidence/cpp_two_actor_probe_03/cohort.json').read_text())
    metadata={'schema':'client442_native_bridge_checkpoint_v1','since':since,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'native_worldserver_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'native_worldserver':lab.owned_process('worldserver'),'bridge':lab.owned_process('modern_world'),
        'credentials_and_authentication_bodies_excluded':True,'full_suite_passed':passed,
        'two_actor_probe_completed':cohort['completed'],
        'limits':['These are bounded compatibility diagnostics, not learned autonomy or whole-game coverage.',
            'Console fixture transfers do not prove autonomous portal/taxi navigation.',
            'The historical Laya proof remains in its earlier checkpoint.']}
    with tempfile.TemporaryDirectory(dir=lab.ROOT/'run') as folder:
        folder=Path(folder)
        for source,name in [(lab.ROOT/'logs/modern_world.jsonl','world_events.jsonl'),
            (lab.ROOT/'evidence/world_packets.jsonl','world_packets.jsonl')]:
            with (folder/name).open('w') as output:
                for row in entries(source):
                    if row.get('time',0)<since:continue
                    opcode=row.get('name','')
                    if 'body' in row and ('AUTH' in opcode or 'ENCRYPT' in opcode or opcode=='SMSG_CONNECT_TO'):
                        raise RuntimeError('authentication body is not admissible')
                    output.write(json.dumps(row,separators=(',',':'))+'\n')
        (folder/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with Live(dir=str(folder/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            live.log_param('code_commit',metadata['code_commit'])
            live.log_param('engine','cpp')
            live.log_metric('full_suite_passed',passed)
            live.log_metric('two_actor_probe_completed',int(cohort['completed']))
            live.log_metric('qualified_whole_game_cases',0)
            live.next_step()
        with tarfile.open(target,'w:gz',compresslevel=6) as archive:
            for path in paths:
                if path.exists():archive.add(path,arcname=str(path.relative_to(lab.ROOT)))
            archive.add(folder,arcname='tracking')
            binary=lab.ROOT/'build/native_bridge/client442_bridge'
            archive.add(binary,arcname='bin/client442_bridge')
    relative=str(target.relative_to(lab.REPO));pointer=relative+'.dvc'
    for command in [['dvc','add',relative],['dvc','status',pointer],['dvc','push',pointer],['dvc','status','--cloud',pointer]]:
        subprocess.run(command,cwd=lab.REPO,check=True)
    print(json.dumps({'file':relative,'bytes':target.stat().st_size,'sha256':lab.sha256(target)}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True);parser.add_argument('--since',type=float,required=True)
    args=parser.parse_args();checkpoint(args.name,args.since)


if __name__=='__main__':main()
