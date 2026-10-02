"""Read-only native content census; IDs are work inventory, never coverage evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import time
from . import lab_runtime as lab
from .observation import map_data

SQL_TABLES={'quests':('world','quest_template','Id'),'items_hotfix':('hotfixes','item','ID'),
    'creature_templates':('world','creature_template','entry'),'gameobject_templates':('world','gameobject_template','entry'),
    'creature_spawns':('world','creature','guid'),'gameobject_spawns':('world','gameobject','guid'),
    'instance_templates':('world','instance_template','map')}
DBC_TABLES={'spells':'Spell','maps':'Map','areas':'AreaTable','classes':'ChrClasses','races':'ChrRaces',
    'skills':'SkillLine','skill_abilities':'SkillLineAbility','achievements':'Achievement',
    'achievement_criteria':'Achievement_Criteria','taxi_nodes':'TaxiNodes','taxi_paths':'TaxiPath',
    'digsites':'ResearchSite','encounters':'DungeonEncounter','dungeon_finder_entries':'LFGDungeons'}


def census():
    domains={};sources={};missing=[]
    # connection() independently verifies the dedicated DB instance and account.
    # Fixed identifiers below cannot select any mainline database or private dig target.
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        try:
            for name,(role,table,column) in SQL_TABLES.items():
                try:
                    cursor.execute(f'SELECT DISTINCT `{column}` FROM `client442_{role}`.`{table}` ORDER BY `{column}`')
                except Exception as error:
                    if not error.args or error.args[0] not in [1054,1146]:raise
                    missing.append({'domain':name,'source':f'client442_{role}.{table}.{column}','database_error_code':error.args[0]})
                    continue
                domains[name]=[int(row[0]) for row in cursor.fetchall()]
                sources[name]={'kind':'legacy_database','table':table,'key':column,'schema':f'client442_{role}'}
        finally:connection.rollback()
    for name,table in DBC_TABLES.items():
        path=map_data.DBC/(table+'.dbc')
        if not path.exists():missing.append({'domain':name,'source':table+'.dbc'});continue
        rows,_=map_data.table(table);domains[name]=sorted({r[0] for r in rows})
        sources[name]={'kind':'public_legacy_dbc','table':table,'sha256':lab.sha256(path)}
    path=map_data.DBC/'Item.db2'
    if not path.exists():missing.append({'domain':'items_dbc','source':'Item.db2'})
    else:
        data=path.read_bytes()
        magic,count,fields,width,strings,_,build,_,minimum,maximum,_,_=struct.unpack_from('<4s11I',data)
        offset=48+(maximum-minimum+1)*6 if maximum else 48
        if magic!=b'WDB2' or fields!=8 or width!=32 or build!=15595 or offset+count*width+strings>len(data):
            raise ValueError('unexpected native item inventory layout')
        domains['items_dbc']=sorted({struct.unpack_from('<I',data,offset+i*width)[0] for i in range(count)})
        sources['items_dbc']={'kind':'public_legacy_db2','table':'Item','sha256':lab.sha256(path)}
    fingerprint=hashlib.sha256(json.dumps({'domains':domains,'sources':sources},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema':'client442_native_content_census_v1','time':time.time(),
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'client_build_target':60895,'native_build':15595,'inventory_sha256':fingerprint,
        'counts':{k:len(v) for k,v in domains.items()},'sources':sources,'missing_sources':missing,
        'domains':domains,'qualified_content_passes':0,
        'limits':['This enumerates native backend records, including unused/deprecated/internal rows.',
            'The installed 60895 client data must also be inventoried and reconciled; this is not that census.',
            'IDs do not enumerate all eligibility, class/spec, phase, difficulty, timing or script variants.',
            'No gameplay was executed; no content correctness or coverage percentage is established.',
            'Data drift invalidates the census fingerprint and requires a new checkpoint.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('use a fresh census output path')
    result=census();a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with gzip.open(a.output,'wt') as handle:json.dump(result,handle,separators=(',',':'))
    a.output.chmod(0o600)
    print(json.dumps({k:result[k] for k in ['inventory_sha256','counts','missing_sources','qualified_content_passes']}))


if __name__=='__main__':main()
