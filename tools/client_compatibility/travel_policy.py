"""Bounded travel decisions over public route, movement and interface facts."""
import random
from .archaeology_policy import base_agent,load_adapter,MODEL,REVISION
from . import lab_runtime as lab

CONFIG=lab.REPO/'experiments/configs/client_harness/laya_travel_training_v1.json'
ACTIONS=['mount','takeoff','cruise','land','dismount','interact','taxi','portal','arrived','observe']
DESCRIPTIONS=dict(zip(ACTIONS,['Mount when on foot along flight route.','Ascend when mounted below safe flight height.',
    'Fly toward waypoint at safe height.','Land when airborne near destination.',
    'Dismount on destination ground.','Open nearby flight master before taxi map.',
    'Select destination in open taxi map.','Walk through portal at entrance.',
    'Finish a confirmed arrival.','Wait while unavailable, casting or in transit.']))
INSTRUCTIONS='Choose the next safe travel action from the observed transport, movement, location and interface facts.'


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


def model_state(s):
    """Describe measured facts; do not include a recommended action or mask."""
    availability='ready'
    if not s['available']:availability='unavailable'
    elif s['casting']:availability='casting'
    elif s['on_taxi']:availability='in taxi transit'
    movement='on foot'
    if s['flying']:movement='airborne at safe route height' if s['at_route_height'] else 'airborne below route height'
    elif s['falling']:movement='falling'
    elif s['mounted']:movement='mounted on ground'
    location='near destination' if s['near_destination'] else 'along route'
    if s['mode']!='flight' and s['destination_reached']:location='arrival confirmed'
    elif s['mode']=='flight' and s['near_destination'] and not s['flying'] and not s['falling']:
        location='on destination ground'
    interface='none'
    if s['mode']=='taxi':interface='open taxi map' if s['taxi_map_open'] else 'near flight master'
    elif s['mode']=='portal':interface='near portal entrance'
    return {'transport':s['mode'],'availability':availability,'movement':movement,'location':location,'interface':interface}


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
                rows.append({'id':f'{split}_{action}_{i}','state':model_state(s),'observed_flags':s,'question':question(order),
                    'label':action,'source':'synthetic public travel policy; no hidden game state'})
        rng.shuffle(rows);splits[split]=rows
    return splits
