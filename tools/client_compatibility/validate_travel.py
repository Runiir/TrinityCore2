"""Score closed live travel/archaeology receipts without private server state."""
import argparse
import json
import re
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
        'frames':0,'frame_hash_failures':[],'model_revisions':[],'source_commits':[],
        'site_find_counts':{},'fresh_sites_fully_completed':[],'model_rejected_decisions':0,
        'water_transits':[],'mounted_corridor_checks':0,'localization_views':0,'ground_escapes':[]}
    for step in root.get('steps',[]):
        if step.get('kind')!='dig':continue
        child=json.loads((directory/step['episode']/'episode.json').read_text())
        sid=str(step['site'])
        summary['site_find_counts'][sid]=summary['site_find_counts'].get(sid,0)+len(child.get('finds',[]))
    summary['fresh_sites_fully_completed']=[s['site'] for s in summary['sites_completed']
        if summary['site_find_counts'].get(str(s['site']),0)>=3]
    for path,receipt in children:
        if not receipt.get('finished_at'):raise ValueError('open child episode: '+str(path))
        summary['source_commits'].append(receipt.get('code_commit'))
        if receipt.get('model'):summary['model_revisions'].append(receipt['model']['revision'])
        summary['manual_gameplay_interventions']+=receipt.get('manual_gameplay_interventions',0)
        summary['recoveries'].extend(receipt.get('safety_recoveries',[]))
        summary['model_rejected_decisions']+=len(receipt.get('rejected_decisions',[]))
        summary['travel_legs'].extend(receipt.get('legs_completed',[]))
        if receipt.get('plan',{}).get('schema')=='public_survey_mounted_move_v1':
            ancestor=next((p for p in path.parents if re.search(r'_site_\d+$',p.name)),None)
            if ancestor is None:raise ValueError('mounted survey has no attributable digsite')
            sid=int(ancestor.name.rsplit('_',1)[1]);polygon=site_boundaries.sites()[sid]['polygon']
            positions=[s['facts']['position'] for s in receipt['steps'] if s.get('facts',{}).get('position')]
            for index,position in enumerate(positions):
                summary['mounted_corridor_checks']+=1
                if not site_boundaries.contains(polygon,position) or (index and
                    not site_boundaries.inside_segment(polygon,positions[index-1],position)):
                    summary['boundary_failures'].append({'episode':str(path.parent.relative_to(directory)),
                        'observation':index,'position':position,'site':sid})
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
                if step['action'].startswith('forward_') and ((kind=='walks' and colour!='green') or (kind=='mounted_moves' and colour=='green')):
                    raise ValueError('mounted movement policy mismatch')
            if step['action']=='loot':
                observed=step['travel']['digsite_ids']
                for find in step['tcp']['finds']:
                    containing=[s['id'] for s in site_boundaries.sites().values() if s['id'] in observed
                        and s['map']==find['map'] and site_boundaries.contains(s['polygon'],find['position'])]
                    summary['artifact_boundary_checks'].append({'guid':find['guid'],'position':find['position'],
                        'inside_assigned_sites':containing,'step':step['index']})
    for path in sorted(directory.rglob('water_transit_*.json')):
        receipt=json.loads(path.read_text());polygon=site_boundaries.sites()[receipt['route']['boundary_guard']['site_id']]['polygon']
        observations=receipt['observations']
        summary['water_transits'].append({'file':str(path.relative_to(directory)),
            'completed':receipt['completed'],'failure':receipt['failure'],
            'swimming_observations':sum(o['travel']['swimming'] for o in observations),
            'dry_arrival':bool(receipt['completed'] and observations and not observations[-1]['travel']['swimming'])})
        positions=[o['position'] for o in observations]
        if any(not site_boundaries.contains(polygon,p) for p in positions) or any(
            not site_boundaries.inside_segment(polygon,a,b) for a,b in zip(positions,positions[1:])):
            summary['boundary_failures'].append({'episode':str(path.relative_to(directory)),'kind':'water_transit'})
    for path in sorted(directory.rglob('find_localization_*.json')):
        receipt=json.loads(path.read_text());sid=int(path.parent.name.rsplit('_',1)[1])
        polygon=site_boundaries.sites()[sid]['polygon']
        for view in receipt['views']:
            frame=path.parent/view['frame'];summary['frames']+=1;summary['localization_views']+=1
            if not frame.exists() or lab.sha256(frame)!=view['sha256']:
                summary['frame_hash_failures'].append(str(frame.relative_to(directory)))
            positions=[view['position']]
            if view.get('next_stance'):
                stance=view['next_stance'];positions.extend([*stance['public_ground_route']['points'],stance['after']])
            if any(not site_boundaries.contains(polygon,p) for p in positions) or any(
                not site_boundaries.inside_segment(polygon,a,b) for a,b in zip(positions,positions[1:])):
                summary['boundary_failures'].append({'episode':str(path.relative_to(directory)),'kind':'find_localization'})
    for path in sorted(directory.rglob('ground_escape_*.json')):
        receipt=json.loads(path.read_text());polygon=site_boundaries.sites()[receipt['site_id']]['polygon']
        summary['ground_escapes'].append({'file':str(path.relative_to(directory)),
            'completed':receipt['completed'],'failure':receipt['failure'],'probes':len(receipt['probes'])})
        positions=[receipt['before']]
        for probe in receipt['probes']:
            positions.extend(o['position'] for o in probe.get('observations',[]))
            positions.append(probe['after'])
        if any(not site_boundaries.contains(polygon,p) for p in positions) or any(
            not site_boundaries.inside_segment(polygon,a,b) for a,b in zip(positions,positions[1:])):
            summary['boundary_failures'].append({'episode':str(path.relative_to(directory)),'kind':'ground_escape'})
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
