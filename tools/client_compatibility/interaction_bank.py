"""Open the existing Stormwind banker through ordinary model-selected input."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .npc_fixture import NpcFixture


def suite(t,point,stage_only):
    actors.session_entry(t.fixture);t.clean_panels()
    fixture=NpcFixture(t.out,t.fixture,2455,131072)
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('banker_staged');t.receipt['staging']={'target':state['target'],'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('banker is not visibly targeted')
        if stage_only:return
        require(t.step('bank.interact','Speak to the nearby banker Olivia Burnside.',{
            'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby banker Olivia Burnside.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your character equipment.'}},
            lambda b,a,s:{'status':'npc_interaction_pass' if s=='interact' and any(p in a['panels'] for p in ['BankFrame','GossipFrame']) else
                ('controller_failure' if s!='interact' else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}},
            diagnostic_action='interact'),'npc_interaction_pass')
        state,_=t.observe('banker_response')
        if 'GossipFrame' in state['panels']:
            require(click_case(t,'bank.gossip','Open your bank account.',lambda c:'bank' in c['text'].lower(),
                lambda b,a,s:{'status':'bank_open_pass' if s and 'BankFrame' in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}}),'bank_open_pass')
        state,frame=t.observe('bank_open');t.receipt['bank_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if 'BankFrame' not in state['panels']:raise RuntimeError('bank window is absent')
        require(t.step('bank.close','Close the bank window.',{
            'close':{'kind':'key','value':'Escape','description':'Press Escape to close the bank.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'bank_close_pass' if s=='close' and 'BankFrame' not in a['panels'] else
                ('controller_failure' if s!='close' else 'client_or_protocol_failure')},diagnostic_action='close'),'bank_close_pass')
    finally:
        t.clean_panels();fixture.restore();state,frame=t.observe('restored')
        t.receipt['restoration']={'frame':frame,'world_position':state['world_position']};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2);p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):p.error('requires a bounded observed NPC point')
    t=Trial(a.output,controller='code' if a.stage_only else 'laya')
    try:suite(t,a.point,a.stage_only);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
