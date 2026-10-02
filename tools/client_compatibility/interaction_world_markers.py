"""Eight world-marker types placed and cleared with model-selected normal inputs."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab,actors
from .interaction_trial import Trial
from .interaction_macros import require
from .interaction_social import actor
from .observation.journal import entries


def suite(output,actor_name,point):
    with actor(actor_name):
        trial=Trial(output)
        try:
            trial.clean_panels();session=actors.session_entry(trial.fixture)['session']
            initial,_=trial.observe('fixture');trial.receipt['fixture']=initial
            if initial['group']['members']!=2:raise RuntimeError('owned two-member group required')
            # Recover the visual marker fixture left by manual/failed probes.
            trial.execute({'kind':'chat','value':'/cwm all'});clean,_=trial.observe('fixture_cleared')
            trial.receipt['cleanup'].append({'source':'code_fixture_cleanup','input':'/cwm all','time':time.time()})
            if any(clean['world_markers']):raise RuntimeError('world marker fixture did not clear')
            for i in range(1,9):
                require(trial.step('raid.world_marker.target.'+str(i),'Select world marker '+str(i)+' for ground placement.',{
                    'place':{'kind':'chat','value':'/wm '+str(i),'description':'Type /wm '+str(i)+' to select this world marker for ground targeting.'},
                    'clear':{'kind':'chat','value':'/cwm '+str(i),'description':'Type /cwm '+str(i)+' to clear this world marker.'},
                    'escape':{'kind':'key','value':'Escape','description':'Press Escape to close or cancel.'}},
                    lambda b,a,s:{'status':'ground_target_requested' if s=='place' else 'controller_failure',
                        'oracle':{'scope':'ordinary input submitted; placement checked separately'}}),'ground_target_requested')
                require(trial.step('raid.world_marker.place.'+str(i),'Place the selected world marker on the visible ground.',{
                    'ground':{'kind':'click','value':point,'description':'Left-click the visible ground near the character.'},
                    'escape':{'kind':'key','value':'Escape','description':'Press Escape to cancel ground targeting.'},
                    'map':{'kind':'key','value':'m','description':'Press M to open the world map.'}},
                    lambda b,a,s:{'status':'world_marker_visible_pass' if s=='ground' and a['world_markers'][i-1] else
                        ('controller_failure' if s!='ground' else 'client_or_protocol_failure')}),'world_marker_visible_pass')
            after,_=trial.observe('all_eight_active')
            if not all(after['world_markers']):raise RuntimeError('not all eight markers remain active together')
            trial.receipt['all_eight_active']=after
            proof=[]
            for name in ['primary','scout']:
                with actor(name):
                    peer=Trial(output/('peer_'+name))
                    try:
                        state,frame=peer.observe('all_markers')
                        if not all(state['world_markers']):raise RuntimeError('peer marker state disagrees')
                        peer.receipt.update(completed=True,observation=state,frame=frame)
                    except BaseException as e:peer.receipt['failure']=f'{type(e).__name__}: {e}';raise
                    finally:peer.receipt['finished_at']=time.time();peer.persist()
            # Original five are confirmed by native masks. Added three are
            # genuine group annotations owned by the modern C++ endpoint.
            for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
                if row.get('session')==session and row['time']>=trial.receipt['started_at'] and row.get('name')=='SMSG_RAID_MARKERS_CHANGED':proof.append(row)
            trial.receipt['marker_packets']=proof
            for command,label in [('/cwm 6','individual'),('/cwm all','all')]:
                require(trial.step('raid.world_marker.clear.'+label,'Clear '+('world marker six.' if label=='individual' else 'all world markers.'),{
                    'clear':{'kind':'chat','value':command,'description':'Type '+command+' to perform this removal.'},
                    'place':{'kind':'chat','value':'/wm 6','description':'Type /wm 6 to place world marker six.'},
                    'escape':{'kind':'key','value':'Escape','description':'Press Escape to close or cancel.'}},
                    lambda b,a,s:{'status':'world_marker_clear_pass' if s=='clear' and
                        (not a['world_markers'][5] and all(a['world_markers'][j] for j in [0,1,2,3,4,6,7]) if label=='individual' else not any(a['world_markers']))
                        else ('controller_failure' if s!='clear' else 'client_or_protocol_failure')}),'world_marker_clear_pass')
            trial.receipt['completed']=True
        except BaseException as e:trial.receipt['failure']=f'{type(e).__name__}: {e}';raise
        finally:
            trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--actor',choices=['primary','scout'],required=True);p.add_argument('--ground',type=int,nargs=2,required=True)
    a=p.parse_args();suite(a.output,a.actor,a.ground)


if __name__=='__main__':main()
