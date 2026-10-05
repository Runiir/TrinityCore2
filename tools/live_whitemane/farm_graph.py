"""Persist the farm's guarded state transitions, separately from model choices."""
import hashlib
import json
import time
import fcntl
import os
from . import runtime
from . import pending_find,world_facts
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


def refresh(path,row,*,latch=None):
    """An observation changes current state without an action or event."""
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(path.read_text())
        if state['runtime']!=row['runtime']:raise RuntimeError('farm graph belongs to another client')
        state.setdefault('last_action_node',state['current'])
        state.update(world_facts.reduce(row,latch));state['current']=state['activity']
        state['action_dependency']=False
        save(path,state)
    return state


def save(path,state):
    temp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    runtime.write(temp,state);temp.replace(path)


def transition(path,action,row,*,pending=None,outcome=None,target=None):
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return record(path,action,row,pending=pending,outcome=outcome,target=target)


def record(path,action,row,*,pending=None,outcome=None,target=None):
    node=NODES.get(action,action);config=json.loads(CONFIG.read_text())
    state=json.loads(path.read_text()) if path.exists() else {'schema':config['schema'],
        'current':config['initial'],'runtime':row['runtime'],'events':[],
        'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest()}
    if state['runtime']!=row['runtime']:raise RuntimeError('farm graph belongs to another client')
    if state['config_sha256']!=hashlib.sha256(CONFIG.read_bytes()).hexdigest():raise RuntimeError('active graph configuration changed')
    previous=state.get('last_action_node',state['current'])
    resumed_combat=node==previous=='combat'
    if previous in ('jar_found','recipe_found') or node not in config['edges']:
        raise RuntimeError('unsupported farm transition '+previous+' -> '+node)
    guard(node,row,pending)
    state['role']='record Laya decisions and observed outcomes'
    state.update(world_facts.reduce(row,pending))
    state.pop('transition_facts',None)
    if node=='combat':state.setdefault('interrupted_state',previous)
    elif node=='observe' and row['movement'].get('in_combat') and previous!='combat':
        state['interrupted_state']=previous
    if target is not None:state['travel_destination']=target
    event={'at':time.time(),'from':previous,'to':node,'pending_pickup':bool(pending),
        'facts':state['facts'],'condition_results':state['transition_conditions'],'outcome':outcome}
    if resumed_combat:event['resumed_after_repair']=True
    if previous=='combat' and node=='observe' and not row['movement'].get('in_combat'):
        event['resume_state']=state.pop('interrupted_state',None)
    state['events']=(state['events']+[event])[-40:];state['last_action_node']=node
    state['current']=state['activity'];state['action_dependency']=False
    save(path,state)
    return event
