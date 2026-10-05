"""Persist the farm's guarded state transitions, separately from model choices."""
import hashlib
import json
import time
from . import runtime
from tools.client_compatibility.archaeology_inputs import FIND_NAMES

CONFIG=runtime.REPO/'experiments/configs/client_harness/whitemane_farm_graph_v1.json'
NODES={'dig':'observe','minimap':'scan_minimap','jar':'open_jar','recipe':'recipe_found',
    'turn_left':'approach','turn_right':'approach','forward_short':'approach','forward_long':'approach',
    'loot':'gather','inspect':'scan_minimap'}


def guard(node,row,pending):
    a=row['archaeology'];signal=row.get('minimap_finds') or {}
    if node in ('teleport','portal','taxi','flight'):
        if pending or signal.get('confirmed') or signal.get('clear') is not True:
            raise RuntimeError('graph blocks travel until pending finds and minimap checks are cleared')
    if node=='survey' and (pending or ((row.get('farm_ui') or {}).get('survey') or {}).get('ready') is False):
        raise RuntimeError('graph blocks Survey during pickup or its cooldown')
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
    if not resumed_combat and node not in config['edges'][state['current']]:
        raise RuntimeError('unsupported farm transition '+state['current']+' -> '+node)
    guard(node,row,pending)
    if node=='combat':state.setdefault('interrupted_state',state['current'])
    elif node=='observe' and row['movement'].get('in_combat') and state['current']!='combat':
        state['interrupted_state']=state['current']
    if target is not None:state['travel_destination']=target
    event={'at':time.time(),'from':state['current'],'to':node,'pending_pickup':bool(pending),'outcome':outcome}
    if resumed_combat:event['resumed_after_repair']=True
    if state['current']=='combat' and node=='observe':event['resume_state']=state.pop('interrupted_state',None)
    state['events']=(state['events']+[event])[-40:];state['current']=node
    runtime.write(path,state)
    return event
