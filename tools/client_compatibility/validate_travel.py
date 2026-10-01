"""Score closed live travel/archaeology receipts without private server state."""
import argparse
import json
from . import lab_runtime as lab, site_boundaries


def score(directory):
    root=json.loads((directory/'episode.json').read_text())
    if not root.get('finished_at'):raise ValueError('cannot validate an open loop')
    children=[(p,json.loads(p.read_text())) for p in sorted(directory.rglob('episode.json')) if p.parent!=directory]
    summary={'episode':directory.name,'completed':root.get('completed',False),'failure':root.get('failure'),
        'duration_seconds':root['finished_at']-root['started_at'],'finds':root.get('finds',[]),
        'fragments_awarded':sum(f['quantity'] for f in root.get('finds',[])),
        'sites_completed':root.get('sites_completed',[]),'model_actions':0,'model_policy_matches':0,
        'walks':0,'mounted_moves':0,'boundary_failures':[],'artifact_boundary_checks':[],
        'travel_legs':[],'recoveries':[],'manual_gameplay_interventions':root.get('manual_gameplay_interventions',0),
        'frames':0,'frame_hash_failures':[],'model_revisions':[],'source_commits':[]}
    for path,receipt in children:
        if not receipt.get('finished_at'):raise ValueError('open child episode: '+str(path))
        summary['source_commits'].append(receipt.get('code_commit'))
        if receipt.get('model'):summary['model_revisions'].append(receipt['model']['revision'])
        summary['manual_gameplay_interventions']+=receipt.get('manual_gameplay_interventions',0)
        summary['recoveries'].extend(receipt.get('safety_recoveries',[]))
        summary['travel_legs'].extend(receipt.get('legs_completed',[]))
        for frame in receipt.get('frames',[]):
            file=path.parent/frame['file'];summary['frames']+=1
            if not file.exists() or lab.sha256(file)!=frame['sha256']:
                summary['frame_hash_failures'].append(str(file.relative_to(directory)))
        for step in receipt.get('steps',[]):
            if 'action' not in step:continue
            summary['model_actions']+=1;summary['model_policy_matches']+=int(step.get('policy_match',False))
            route=(step.get('input') or {}).get('ground_route')
            if route:
                kind='mounted_moves' if route.get('mounted_travel_episode') else 'walks'
                summary[kind]+=1
                if not route['boundary_guard']['observed_after_inside']:
                    summary['boundary_failures'].append({'episode':str(path.parent.relative_to(directory)),'step':step['index']})
                colour=(step.get('tcp',{}).get('tool') or {}).get('color')
                if (kind=='walks' and colour!='green') or (kind=='mounted_moves' and colour=='green'):
                    raise ValueError('mounted movement policy mismatch')
            if step['action']=='loot':
                observed=step['travel']['digsite_ids']
                for find in step['tcp']['finds']:
                    containing=[s['id'] for s in site_boundaries.sites().values() if s['id'] in observed
                        and s['map']==find['map'] and site_boundaries.contains(s['polygon'],find['position'])]
                    summary['artifact_boundary_checks'].append({'guid':find['guid'],'position':find['position'],
                        'inside_assigned_sites':containing,'step':step['index']})
    summary['source_commits']=sorted(set(c for c in summary['source_commits'] if c))
    summary['model_revisions']=sorted(set(summary['model_revisions']))
    summary['model_policy_agreement']=summary['model_policy_matches']/summary['model_actions'] if summary['model_actions'] else None
    summary['all_collected_artifacts_inside']=bool(summary['artifact_boundary_checks']) and all(c['inside_assigned_sites'] for c in summary['artifact_boundary_checks'])
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--episode',action='append',required=True)
    a=p.parse_args()
    for name in a.episode:
        if '/' in name or '\\' in name:raise ValueError('episode must be a directory name')
    results=[score(lab.ROOT/'evidence'/name) for name in a.episode]
    report={'schema':'client442_outland_loop_validation_v1','episodes':results,
        'interpretation':'bounded live trials; model agreement is not an independent general skill metric'}
    lab.private_write(lab.ROOT/'evidence/outland_loop_validation.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps([{'episode':r['episode'],'completed':r['completed'],'finds':len(r['finds']),
        'sites':len(r['sites_completed']),'fragments':r['fragments_awarded'],'model_actions':r['model_actions'],
        'frame_hash_failures':len(r['frame_hash_failures']),'boundary_failures':len(r['boundary_failures'])} for r in results]))


if __name__=='__main__':main()
