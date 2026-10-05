"""Deploy a map-boundary extension using hashed public 60895 DB2 evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from . import runtime


def prepare(directory):
    comparison=json.loads((directory/'comparison.json').read_text())
    if comparison['client_build']!=60895:raise RuntimeError('wrong public table build')
    for name,record in comparison['client_tables'].items():
        if hashlib.sha256((directory/(name+'.db2')).read_bytes()).hexdigest()!=record['sha256']:
            raise RuntimeError('public digsite table identity changed')
    rows=['-- Public 4.4.2 map blobs; no live artifact positions.','local _, A = ...',
          'A.liveBoundaryData = {build=60895,source="public 60895 DB2 polygons; addon blob identity checked",sites={']
    for key,site in sorted(comparison['sites'].items(),key=lambda r:int(r[0])):
        polygon='{'+','.join('{'+','.join(map(str,p))+'}' for p in site['polygon'])+'}'
        rows.append(f"[{int(key)}]={{map={site['map']},blob={site['poi_blob']},polygon={polygon}}},")
    rows.append('}}')
    output=runtime.ROOT/'evidence/boundary_data'
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=output/'LiveBoundaryData.lua';data.write_text('\n'.join(rows)+'\n')
    runtime.write(output/'polygons.json',comparison['sites'])
    target=Path.home()/'Games/_whitemane-60895_/Interface/AddOns/CanopicHelper'
    shutil.copy2(data,target/data.name)
    shutil.copy2(runtime.REPO/'tools/live_whitemane/addon/Boundary.lua',target/'LiveBoundary.lua')
    toc=target/'CanopicHelper.toc'
    lines=[line for line in toc.read_text().splitlines() if line not in ('LiveBoundaryData.lua','LiveBoundary.lua')]
    toc.write_text('\n'.join([*lines,'LiveBoundaryData.lua','LiveBoundary.lua'])+'\n')
    runtime.write(output/'receipt.json',{'schema':'whitemane_public_boundary_extension_v1',
        'client_build':60895,'source':'public tables from local 60895 reference client',
        'live_client_blob_match_required':True,'table_hashes':comparison['client_tables'],
        'source_comparison_sha256':hashlib.sha256((directory/'comparison.json').read_bytes()).hexdigest(),
        'extension_sha256':hashlib.sha256((target/'LiveBoundary.lua').read_bytes()).hexdigest(),
        'data_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
        'private_artifact_positions':False,'inward_margin_yards':8})
    return {'sites':len(comparison['sites']),'reload_needed':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    print(json.dumps(prepare(parser.parse_args().directory)))
