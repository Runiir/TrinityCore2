"""Compile and compare the native sampler on public DBC digsite perimeters."""
import argparse,json,shlex,subprocess
from pathlib import Path
from . import lab_runtime as lab
from .observation.map_data import catalog


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    root=lab.REPO/'src/server/game/Skills/Archaeology';fixture=lab.REPO/'tests/fixtures/archaeology_geometry.cpp'
    commands=json.loads((lab.ROOT/'build/compile_commands.json').read_text())
    command=next(row for row in commands if row['file']==str(root/'SitePolygonGraph.cpp'))
    flags=shlex.split(command['command']);flags=flags[:flags.index('-o')]
    sites=list(catalog()['sites'].values())
    sites.append({'id':99999,'polygon':[[0,0],[10,0],[10,2],[2,2],[2,10],[0,10]]})
    data=f'{len(sites)} 1000\n'+''.join(f"{s['id']} {len(s['polygon'])}\n"+''.join(f'{x} {y}\n' for x,y in s['polygon']) for s in sites)
    (a.output/'public_perimeters.txt').write_text(data)
    receipt={'schema':'native_archaeology_geometry_v1','sites':len(sites),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),'variants':{}}
    for variant in ['original','fixed']:
        source=root/'SitePolygonGraph.cpp'
        if variant=='original':
            source=a.output/'original_graph.cpp';source.write_bytes(subprocess.check_output(['git','show','cd860ebe6c90:src/server/game/Skills/Archaeology/SitePolygonGraph.cpp'],cwd=lab.REPO))
        binary=a.output/variant
        args=[*flags,*(['-DTEST_CONTAINS'] if variant=='fixed' else []),str(source),str(root/'SitePolygonGeometry.cpp'),str(fixture),'-o',str(binary)]
        subprocess.run(args,check=True,cwd=lab.ROOT/'build')
        result=subprocess.run([str(binary)],input=data,text=True,capture_output=True,timeout=30)
        (a.output/f'{variant}.log').write_text(result.stderr)
        receipt['variants'][variant]={'exit_code':result.returncode,'result':json.loads(result.stdout),'source_sha256':lab.sha256(source)}
        binary.unlink()
    lab.private_write(a.output/'receipt.json',json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
    if receipt['variants']['fixed']['exit_code']:raise RuntimeError('native sampler returned points outside the perimeter')


if __name__=='__main__':main()
