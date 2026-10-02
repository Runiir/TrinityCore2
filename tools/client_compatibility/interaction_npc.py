"""Probe one existing NPC service through normal observed mouse inputs."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .npc_fixture import NpcFixture


SERVICES={'merchant':{'entry':1285,'flag':128,'panel':'MerchantFrame','caption':'goods'}}


def suite(t,service,point,stage_only):
    spec=SERVICES[service];actors.session_entry(t.fixture);t.clean_panels()
    fixture=NpcFixture(t.out,t.fixture,spec['entry'],spec['flag'])
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('npc_staged');t.receipt['staging']={'target':state['target'],'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('service NPC is not visibly targeted')
        if stage_only:return
        require(t.step(service+'.interact','Speak to the nearby '+service+' '+fixture.npc[2]+'.',{
            'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby '+service+' '+fixture.npc[2]+'.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your character equipment.'}},
            lambda b,a,s:{'status':'npc_interaction_pass' if s=='interact' and any(p in a['panels'] for p in [spec['panel'],'GossipFrame']) else
                ('controller_failure' if s!='interact' else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}},
            diagnostic_action='interact'),'npc_interaction_pass')
        state,_=t.observe('npc_response')
        if 'GossipFrame' in state['panels']:
            require(click_case(t,service+'.gossip','Open the '+service+' service.',lambda c:spec['caption'] in c['text'].lower(),
                lambda b,a,s:{'status':'service_open_pass' if s and spec['panel'] in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}}),'service_open_pass')
        state,frame=t.observe('service_open');t.receipt['service_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if spec['panel'] not in state['panels']:raise RuntimeError('service window is absent')
        require(t.step(service+'.close','Close the '+service+' window.',{
            'close':{'kind':'key','value':'Escape','description':'Press Escape to close the '+service+' window.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'service_close_pass' if s=='close' and spec['panel'] not in a['panels'] else
                ('controller_failure' if s!='close' else 'client_or_protocol_failure')},diagnostic_action='close'),'service_close_pass')
    finally:
        t.clean_panels();fixture.restore();state,frame=t.observe('restored')
        t.receipt['restoration']={'frame':frame,'world_position':state['world_position']};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--service',choices=SERVICES,required=True);p.add_argument('--point',type=int,nargs=2)
    p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):p.error('requires a bounded observed NPC point')
    t=Trial(a.output,controller='code' if a.stage_only else 'laya')
    try:suite(t,a.service,a.point,a.stage_only);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
