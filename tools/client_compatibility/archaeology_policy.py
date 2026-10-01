"""Archaeology choices with public facts and all seven actions available.

Arithmetic and physical input durations belong to the controller. The adapted
Laya head selects the next action without a supplied next-action instruction.
"""
import json
import math
import random
from . import lab_runtime as lab
from .archaeology_controller import MODEL, REVISION, DESCRIPTIONS

CONFIG = lab.REPO/'experiments/configs/client_harness/laya_archaeology_training_v1.json'
ACTIONS = ['survey','turn_left','turn_right','forward_short','forward_long','loot','observe']
INSTRUCTIONS = 'Choose the next archaeology action from the player and survey observations. Recover the visible find. Wait while casting or unavailable. Survey after walking. Face a fresh telescope before walking; green calls for a short walk, red or yellow a longer walk.'


def question(order=ACTIONS):
    return {'type':'choice','instructions':INSTRUCTIONS,'criteria':{k:DESCRIPTIONS[k] for k in order}}


def label(state):
    if not state['available'] or state['casting']: return 'observe'
    if state['artifact_visible']: return 'loot'
    if not state['instrument_current']: return 'survey'
    direction=state['telescope']['heading_relative_to_player']
    if direction=='left':return 'turn_left'
    if direction=='right':return 'turn_right'
    return 'forward_short' if state['telescope']['color']=='green' else 'forward_long'


def observed_state(movement,travel,tcp,history):
    last_survey=next((s for s in reversed(history) if s['action']=='survey' and s['session']==tcp['session']),None)
    after=history[history.index(last_survey)+1:] if last_survey else history
    walked=any(s['action'].startswith('forward_') for s in after)
    tool=tcp['tool']
    current=bool(last_survey and tool and tool['seen_at']>=last_survey['started_at'] and not walked)
    direction=None
    if tool:
        error=tool['turn_error_radians']
        direction='aligned' if abs(error)<=.10 else 'left' if error>0 else 'right'
    return {'task':'recover an archaeology find','available':movement['in_world'] and not any(movement[k] for k in ['dead','in_combat','on_taxi']),
        'casting':travel['casting'], 'artifact_visible':bool(tcp['finds']), 'instrument_current':current,
        'telescope':{'color':tool['color'],'heading_relative_to_player':direction} if tool else None}


def dataset(config):
    splits={}
    for split_index,split in enumerate(['train','validation','test']):
        rng=random.Random(config['seed']+split_index)
        rows=[]
        for action in ACTIONS:
            for index in range(config[split+'_per_action']):
                state={'task':'recover an archaeology find','available':True,'casting':False,
                    'artifact_visible':False,'instrument_current':True,
                    'telescope':{'color':rng.choice(['red','yellow','green']),
                                 'heading_relative_to_player':rng.choice(['left','right','aligned'])}}
                if action=='observe':
                    state['available']=rng.choice([False,True]);state['casting']=not state['available'] or rng.choice([True,False])
                    if state['available']:state['casting']=True
                    state['artifact_visible']=rng.choice([False,True])
                    state['instrument_current']=rng.choice([False,True])
                elif action=='loot':state['artifact_visible']=True;state['instrument_current']=rng.choice([False,True])
                elif action=='survey':state['instrument_current']=False
                else:
                    state['telescope']['heading_relative_to_player']=action[5:] if action.startswith('turn_') else 'aligned'
                    if action=='forward_short':state['telescope']['color']='green'
                    elif action=='forward_long':state['telescope']['color']=rng.choice(['red','yellow'])
                if rng.choice([False,True]) and not state['instrument_current']:state['telescope']=None
                assert label(state)==action
                order=list(ACTIONS);rng.shuffle(order)
                rows.append({'id':f'{split}_{action}_{index}','state':state,'question':question(order),'label':action,
                    'source':'synthetic public telescope control policy; no private find positions'})
        rng.shuffle(rows);splits[split]=rows
    return splits


def base_agent():
    import laya
    from huggingface_hub import snapshot_download
    snapshot=snapshot_download('convaiinnovations/laya',revision=REVISION,allow_patterns=['typed-decisions/*'])
    agent=laya.load(snapshot,subfolder='typed-decisions',device='cuda')
    return agent


def load_adapter(directory):
    from safetensors.torch import load_file
    directory=lab.ROOT/'models'/directory if not hasattr(directory,'is_dir') else directory
    metadata=json.loads((directory/'receipt.json').read_text())
    if metadata['parent_revision']!=REVISION or lab.sha256(directory/'adapter.safetensors')!=metadata['adapter_sha256']:
        raise ValueError('adapter identity mismatch')
    agent=base_agent()
    weights=load_file(str(directory/'adapter.safetensors'))
    if any(k.startswith('encoder.') for k in weights):raise ValueError('adapter unexpectedly replaces the encoder')
    result=agent.model.load_state_dict(weights,strict=False)
    if result.unexpected_keys or any(not k.startswith('encoder.') for k in result.missing_keys):raise ValueError('incomplete decision head')
    # Parent temperatures were calibrated on different workflows. This adapter
    # reports ordinary softmax scores and is evaluated on this task separately.
    agent.temperature=[1.,1.,1.];agent.temperature_by_options={}
    return agent,metadata
