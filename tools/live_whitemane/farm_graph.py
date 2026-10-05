"""Persist the farm's guarded state transitions, separately from model choices."""
import hashlib
import json
import time
from . import runtime
from . import pending_find
from tools.client_compatibility.archaeology_inputs import FIND_NAMES

CONFIG=runtime.REPO/'experiments/configs/client_harness/whitemane_farm_graph_v1.json'
NODES={'dig':'observe','minimap':'scan_minimap','jar':'open_jar','recipe':'recipe_found',
    'turn_left':'approach','turn_right':'approach','forward_short':'approach','forward_long':'approach',
    'loot':'gather','mouseover_interact':'gather','inspect':'scan_minimap','camera_forward':'observe'}


def guard(node,row,pending):
    a=row['archaeology']
    if node=='survey' and ((row.get('farm_ui') or {}).get('survey') or {}).get('ready') is False:
        raise RuntimeError('Survey is still on cooldown')
    if node=='gather' and not (pending or a['loot_open'] or
        ((row.get('farm_ui') or {}).get('soft_interact') or {}).get('name') in FIND_NAMES):
        raise RuntimeError('graph gather requires a public find observation')
    if node=='jar_found' and not a['canopic_jars_in_bags']:
        raise RuntimeError('graph jar completion requires the item in bags')


def transition(path,action,row,*,pending=None,outcome=None,target=None):
    node=NODES.get(action,action);config=json.loads(CONFIG.read_text())
    state=json.loads(path.read_text()) if path.exists() else {'schema':config['schema'],
        'current':config['initial'],'runtime':row['runtime'],'events':[],
        'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest()}
    if state['runtime']!=row['runtime']:raise RuntimeError('farm graph belongs to another client')
    if state['config_sha256']!=hashlib.sha256(CONFIG.read_bytes()).hexdigest():raise RuntimeError('active graph configuration changed')
    resumed_combat=node==state['current']=='combat'
    if state['current'] in ('jar_found','recipe_found') or node not in config['edges']:
        raise RuntimeError('unsupported farm transition '+state['current']+' -> '+node)
    guard(node,row,pending)
    state['role']='record Laya decisions and observed outcomes'
    state['pickup_facts']=pending_find.facts(row,pending)
    state['activity']='combat' if row['movement']['in_combat'] else 'pickup' if state['pickup_facts']['uncollected'] else 'dig' if row['archaeology']['can_survey'] else 'travel'
    state.pop('transition_facts',None)
    state['facts']={key:row['archaeology'].get(key) for key in ('mounted','flying','falling','casting','loot_open')}
    state['facts'].update(combat=row['movement']['in_combat'],
        artifact_uncollected=state['pickup_facts']['uncollected'],
        artifact_named=state['pickup_facts']['named_target'],
        survey_ready=((row.get('farm_ui') or {}).get('survey') or {}).get('ready'))
    state['transition_conditions']={'onward_travel':not state['facts']['artifact_uncollected'],
        'survey':state['facts']['survey_ready'] is True and not state['facts']['artifact_uncollected'],
        'combat':state['facts']['combat']}
    if node=='combat':state.setdefault('interrupted_state',state['current'])
    elif node=='observe' and row['movement'].get('in_combat') and state['current']!='combat':
        state['interrupted_state']=state['current']
    if target is not None:state['travel_destination']=target
    event={'at':time.time(),'from':state['current'],'to':node,'pending_pickup':bool(pending),
        'facts':state['facts'],'condition_results':state['transition_conditions'],'outcome':outcome}
    if resumed_combat:event['resumed_after_repair']=True
    if state['current']=='combat' and node=='observe' and not row['movement'].get('in_combat'):
        event['resume_state']=state.pop('interrupted_state',None)
    state['events']=(state['events']+[event])[-40:];state['current']=node
    runtime.write(path,state)
    return event
