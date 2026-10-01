"""Bounded travel decisions over public route, movement and interface facts."""
import random
from .archaeology_policy import base_agent,load_adapter,MODEL,REVISION
from . import lab_runtime as lab

CONFIG=lab.REPO/'experiments/configs/client_harness/laya_travel_training_v1.json'
ACTIONS=['mount','takeoff','cruise','land','dismount','interact','taxi','portal','arrived','observe']
DESCRIPTIONS=dict(zip(ACTIONS,['Summon flying mount.','Ascend to route height.','Fly toward waypoint.',
    'Descend to destination ground.','Remove mount while grounded.','Open nearby flight master.',
    'Click destination in taxi map.','Walk into portal.','Finish completed leg.','Wait while unavailable.']))
INSTRUCTIONS='Choose the next safe travel action. Mount before flying. Ascend before cruising. Land near the waypoint and dismount. Use taxi or portal only at its interface. Wait during casting or transfer.'


def question(order=ACTIONS):
    return {'type':'choice','instructions':INSTRUCTIONS,'criteria':{k:DESCRIPTIONS[k] for k in order}}


def label(s):
    if not s['available'] or s['casting'] or s['on_taxi']:return 'observe'
    if s['mode']=='flight':
        if s['near_destination']:
            if s['flying'] or s['falling']:return 'land'
            return 'dismount' if s['mounted'] else 'arrived'
        if not s['mounted']:return 'mount'
        return 'cruise' if s['at_route_height'] and s['flying'] else 'takeoff'
    if s['destination_reached']:return 'arrived'
    if s['flying'] or s['falling']:return 'land'
    if s['mounted']:return 'dismount'
    if s['mode']=='taxi':return 'taxi' if s['taxi_map_open'] else 'interact'
    return 'portal'


def dataset(config):
    splits={}
    for j,split in enumerate(['train','validation','test']):
        rng=random.Random(config['seed']+j);rows=[]
        for action in ACTIONS:
            for i in range(config[split+'_per_action']):
                while True:
                    s={'mode':rng.choice(['flight','taxi','portal']),
                       'available':rng.random()>.05,'casting':rng.random()<.05,'on_taxi':rng.random()<.05,
                       'mounted':rng.choice([True,False]),'flying':rng.choice([True,False]),
                       'falling':rng.random()<.1,'at_route_height':rng.choice([True,False]),
                       'near_destination':rng.choice([True,False]),'destination_reached':rng.random()<.2,
                       'taxi_map_open':rng.choice([True,False])}
                    # Physically possible movement combinations only.
                    if s['flying'] and not s['mounted']:continue
                    if s['at_route_height'] and not s['flying']:continue
                    if s['taxi_map_open'] and (s['flying'] or s['mode']!='taxi'):continue
                    if label(s)==action:break
                order=list(ACTIONS);rng.shuffle(order)
                rows.append({'id':f'{split}_{action}_{i}','state':s,'question':question(order),
                    'label':action,'source':'synthetic public travel policy; no hidden game state'})
        rng.shuffle(rows);splits[split]=rows
    return splits
