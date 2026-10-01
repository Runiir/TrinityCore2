"""Archive closed travel/archaeology episodes and sync their DVC checkpoint."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from dvclive import Live
from . import lab_runtime as lab
from .checkpoint_archaeology import training_metrics


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True)
    p.add_argument('--episode',action='append',default=[])
    p.add_argument('--incremental',action='store_true',help='models are already in the preceding checkpoint')
    p.add_argument('--preceding-checkpoint',default='442_archaeology_boundaries_20261001.tar.gz.dvc');a=p.parse_args()
    if Path(a.preceding_checkpoint).name!=a.preceding_checkpoint:raise ValueError('invalid preceding checkpoint')
    if not a.name.replace('_','').isalnum():raise ValueError('invalid checkpoint name')
    target=lab.REPO/'artifacts/client_harness'/(a.name+'.tar.gz')
    if target.exists() or Path(str(target)+'.dvc').exists():raise ValueError('checkpoint exists')
    paths=[] if a.incremental else [lab.ROOT/'models/travel-head-v1',lab.ROOT/'models/travel-head-v2',lab.ROOT/'models/travel-head-v3',lab.ROOT/'models/travel-head-startup-failure']
    paths.extend(lab.ROOT/'evidence'/name for name in ['world_packets.jsonl','client_monitor.json',
        'pretravel_world_packets.jsonl.gz','pretravel_modern_world.jsonl.gz','travel_ready.png','travel_start.png',
        'travel_protocol_tests.xml','flightmaster_test_dependency_failure.xml','travel_live_validation.json','travel_serving_preflight.json',
        'taxi_stall.png','taxi_relogin.png','taxi_retry_ready.png','taxi_query_login.png',
        'taxi_hotfix_login.png','taxi_hotfix_ready.png','travel_live_ready.png','travel_combat_stop.png',
        'steep_ground_repair.json','travel_repair_cleanup.json','client442_portal_tables',
        'portal_hotfix_login.png','portal_hotfix_character.png','portal_hotfix_character_ready.png',
        'portal_connect_login.png','portal_connect_character.png','portal_connect_ready.png',
        'travel_portal_validation.json','portal_contact_geometry.json',
        'portal_contact_login.png','portal_contact_character.png','portal_contact_ready.png',
        'portal_roundtrip_login.png','portal_roundtrip_character.png','portal_roundtrip_ready.png',
        'portal_return_login.png','portal_return_character.png','portal_return_ready.png',
        'portal_overhang_ground.json','overhang_recovery_start.png',
        'flight_recovery_collection_failure.xml','flight_recovery_fixture_failure.xml',
        'flat_landing_repair.json','flat_landing_repair_25.json','outland_loop_validation.json',
        'outland_combat_stop.png','outland_attack_probe.png','loot_pose_check.png',
        'combat_login.png','combat_character_login.png','combat_world_login.png',
        'observation_refactor_collection_failure.xml','landing_recovery_collection_failure.xml',
        'landing_slope_regression_failure.xml','ground_wall_repair.json',
        'water_repair_before.png','water_repair_after.png','water_repair.json','water_loop_completion.json',
        'loot_tooltip_occlusion_56.png','loot_tooltip_hover_56.png','loot_tooltip_hover_56.json',
        'ground_corner_after_59.png','navigation_collection_repairs_cleanup.json',
        'collection_interrupt_61.png','collection_interrupt_guard_failure.xml',
        'tooltip_hover_diagnostic.png','tooltip_hover_diagnostic.json','outland_repairs_cleanup.json','water_repairs_cleanup.json',
        'creature_movement_login.png','creature_movement_character.png','creature_movement_world.png',
        'creature_position_login.png','creature_position_character.png','creature_position_world.png',
        'creature_movement_now.png','outland_loop_now.png'])
    paths.append(lab.ROOT/'data/dbc/enUS/AreaTrigger.dbc')
    paths.append(lab.ROOT/'logs/modern_world.jsonl')
    paths.extend(sorted((lab.ROOT/'evidence').glob('world_packets.jsonl.part-*')))
    paths.extend(sorted((lab.ROOT/'logs').glob('modern_world.jsonl.part-*')))
    paths.append(lab.ROOT/'bin/navmesh_probe')
    paths.extend(lab.ROOT/'evidence/reference'/name for name in ['MovementHandler_4_4_0.cs','SplineFlag_6_0_2.cs'])
    episodes=[]
    totals=[]
    for name in a.episode:
        if Path(name).name!=name:raise ValueError('invalid episode name')
        path=lab.ROOT/'evidence'/name
        receipt=json.loads((path/'episode.json').read_text())
        if not receipt.get('finished_at'):raise ValueError('episode still open')
        paths.append(path);episodes.append(receipt)
        children=[json.loads(p.read_text()) for p in path.rglob('episode.json')]
        site_finds={}
        for step in receipt['steps']:
            if step.get('kind')!='dig':continue
            child=json.loads((path/step['episode']/'episode.json').read_text())
            sid=step['site'];site_finds[sid]=site_finds.get(sid,0)+len(child.get('finds',[]))
        water=[json.loads(p.read_text()) for p in path.rglob('water_transit_*.json')]
        totals.append({'model_actions':sum(sum('action' in s for s in r['steps']) for r in children),
            'travel_legs':sum(len(r.get('legs_completed',[])) for r in children),
            'safety_recoveries':sum(len(r.get('safety_recoveries',[])) for r in children),
            'model_rejected_decisions':sum(len(r.get('rejected_decisions',[])) for r in children),
            'fresh_sites_fully_completed':sum(site_finds.get(s['site'],0)>=3 for s in receipt.get('sites_completed',[])),
            'water_transits_completed':sum(r['completed'] for r in water),
            'swimming_observations':sum(o['travel']['swimming'] for r in water for o in r['observations'])})
    with tempfile.TemporaryDirectory(dir=lab.ROOT/'run/tmp') as scratch:
        scratch=Path(scratch)
        training_metrics(lab.ROOT/'models/travel-head-v3',scratch/'training')
        with Live(dir=str(scratch/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            for name,r,total in zip(a.episode,episodes,totals):
                live.log_param('episode',name)
                live.log_metric('completed',int(r.get('completed',False)))
                live.log_metric('steps',len(r['steps']))
                live.log_metric('model_actions',total['model_actions'])
                live.log_metric('collected_finds',len(r.get('finds',[])))
                live.log_metric('travel_legs',total['travel_legs'])
                live.log_metric('safety_recoveries',total['safety_recoveries'])
                live.log_metric('model_rejected_decisions',total['model_rejected_decisions'])
                live.log_metric('fresh_sites_fully_completed',total['fresh_sites_fully_completed'])
                live.log_metric('water_transits_completed',total['water_transits_completed'])
                live.log_metric('swimming_observations',total['swimming_observations'])
                live.log_metric('fragments_awarded',sum(f['quantity'] for f in r.get('finds',[])))
                live.log_metric('sites_completed',len(r.get('sites_completed',[])))
                live.log_metric('duration_seconds',r['finished_at']-r['started_at']);live.next_step()
        metadata={'schema':'client442_travel_checkpoint_v1','code_commit':subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),'closed_episodes':a.episode,
            'preceding_checkpoint':a.preceding_checkpoint,'models_included':not a.incremental,
            'authentication_and_credentials_excluded':True}
        (scratch/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with tarfile.open(target,'w:gz',compresslevel=6) as archive:
            for path in paths:
                if path.exists():archive.add(path,arcname=str(path.relative_to(lab.ROOT)))
            archive.add(scratch,arcname='tracking')
    relative=str(target.relative_to(lab.REPO))
    for command in [['dvc','add',relative],['dvc','status',relative+'.dvc'],['dvc','push',relative+'.dvc']]:
        subprocess.run(command,cwd=lab.REPO,check=True)
    print(json.dumps({'file':relative,'sha256':lab.sha256(target),'bytes':target.stat().st_size}))


if __name__=='__main__':main()
