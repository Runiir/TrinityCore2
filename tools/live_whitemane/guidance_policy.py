"""Laya archaeology actions over an explicit recorded-marker or telescope guide."""
from tools.client_compatibility import archaeology_policy as parent
import random
from pathlib import Path

ACTIONS=parent.ACTIONS
MODEL,REVISION,base_agent=parent.MODEL,parent.REVISION,parent.base_agent
CONFIG=Path(__file__).resolve().parents[2]/'experiments/configs/client_harness/laya_live_guidance_training_v1.json'
INSTRUCTIONS='Choose the next archaeology action. Visit the selected recorded minimap marker before searching untracked ground. Face the guide before advancing. Survey on arrival or when there is no guide. Loot a visible find. Wait while unavailable or casting.'
DESCRIPTIONS={'survey':'Survey at the reached marker or without a guide.',
    'turn_left':'Turn left to face the guide.','turn_right':'Turn right to face the guide.',
    'forward_short':'Approach a nearby guide or green telescope.','forward_long':'Approach a distant guide or red or yellow telescope.',
    'loot':'Collect the visible archaeology find.','observe':'Wait while casting or unavailable.'}


def question(order=ACTIONS):
    return {'type':'choice','instructions':INSTRUCTIONS,'criteria':{k:DESCRIPTIONS[k] for k in order}}


def label(state):
    if not state['available'] or state['casting']: return 'observe'
    if state['artifact_visible']: return 'loot'
    guide=state['guide']
    if not guide or guide['arrived']: return 'survey'
    direction=guide['heading_relative_to_player']
    if direction=='left': return 'turn_left'
    if direction=='right': return 'turn_right'
    return 'forward_short' if guide['distance_yards']<=40 or guide['color']=='green' else 'forward_long'


def dataset(config):
    splits={}
    for split_index,split in enumerate(('train','validation','test')):
        rng=random.Random(config['seed']+split_index);rows=[]
        for action in ACTIONS:
            for index in range(config[split+'_per_action']):
                color=rng.choice(('green','yellow','red'))
                distance=rng.uniform(4,39) if color=='green' else rng.uniform(41,79) if color=='yellow' else rng.uniform(81,250)
                guide={'source':rng.choice(('GatherMate marker','Survey telescope')),
                    'distance_yards':round(distance,1),'color':color,
                    'heading_relative_to_player':rng.choice(('left','right','aligned')),'arrived':False}
                state={'task':'finish the current digsite','available':True,'casting':False,'artifact_visible':False,'guide':guide}
                if action=='observe':
                    state['available']=rng.choice((True,False));state['casting']=not state['available'] or True
                    state['artifact_visible']=rng.choice((True,False))
                elif action=='loot': state['artifact_visible']=True
                elif action=='survey':
                    if rng.choice((True,False)): state['guide']=None
                    else: guide.update(arrived=True,distance_yards=round(rng.uniform(0,3),1))
                elif action.startswith('turn_'): guide['heading_relative_to_player']=action[5:]
                else:
                    guide['heading_relative_to_player']='aligned'
                    if action=='forward_short': guide.update(color='green',distance_yards=round(rng.uniform(4,39),1))
                    else: guide.update(color=rng.choice(('red','yellow')),distance_yards=round(rng.uniform(41,250),1))
                assert label(state)==action
                order=list(ACTIONS);rng.shuffle(order)
                rows.append({'id':f'{split}_{action}_{index}','state':state,'question':question(order),
                             'label':action,'source':'synthetic public marker/telescope guidance contract; no hidden find positions'})
        rng.shuffle(rows);splits[split]=rows
    return splits
