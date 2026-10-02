"""Read-only native content census; IDs are work inventory, never coverage evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import time
from . import lab_runtime as lab
from .observation import map_data

SQL_TABLES={'quests':('quest_template','Id'),'items':('item_template','entry'),
    'creature_templates':('creature_template','entry'),'gameobject_templates':('gameobject_template','entry'),
    'creature_spawns':('creature','guid'),'gameobject_spawns':('gameobject','guid'),
    'instance_templates':('instance_template','map')}
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
            for name,(table,column) in SQL_TABLES.items():
                cursor.execute(f'SELECT DISTINCT `{column}` FROM `client442_world`.`{table}` ORDER BY `{column}`')
                domains[name]=[int(row[0]) for row in cursor.fetchall()]
                sources[name]={'kind':'legacy_world_database','table':table,'key':column,'schema':'client442_world'}
        finally:connection.rollback()
    for name,table in DBC_TABLES.items():
        path=map_data.DBC/(table+'.dbc')
        if not path.exists():missing.append({'domain':name,'source':table+'.dbc'});continue
        rows,_=map_data.table(table);domains[name]=sorted({r[0] for r in rows})
        sources[name]={'kind':'public_legacy_dbc','table':table,'sha256':lab.sha256(path)}
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
