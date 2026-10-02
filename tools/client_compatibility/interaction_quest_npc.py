"""Open and inspect an existing questgiver through owned ordinary inputs."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .npc_fixture import NpcFixture


def suite(t,point,stage_only,details=False):
    actors.session_entry(t.fixture);t.clean_panels();fixture=NpcFixture(t.out,t.fixture,197,2)
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('npc_staged');t.receipt['staging']={'target':state['target'],'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('questgiver is not visibly targeted')
        if stage_only:return
        require(t.step('quests.interact','Speak to nearby questgiver '+fixture.npc[2]+'.',{
            'interact':{'kind':'click','value':point,'button':3,'description':'Right-click visible nearby questgiver '+fixture.npc[2]+'.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open character equipment.'}},
            lambda b,a,s:{'status':'questgiver_open_pass' if s=='interact' and any(p in a['panels'] for p in ['QuestFrame','GossipFrame']) else
                ('controller_failure' if s!='interact' else 'client_or_protocol_failure'),
                'oracle':{'panels':a['panels'],'errors':a['errors']}},diagnostic_action='interact'),'questgiver_open_pass')
        state,frame=t.observe('questgiver_open');t.receipt['questgiver_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if details:
            require(click_case(t,'quests.select_giver_quest','Read the offered Beating Them Back! quest.',
                lambda c:'Beating Them Back!' in c['text'],
                lambda b,a,s:{'status':'quest_details_open_pass' if s and 'QuestFrame' in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),
                    'oracle':{'panels':a['panels'],'errors':a['errors']}}),'quest_details_open_pass')
            state,frame=t.observe('quest_details');t.receipt['quest_details']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        require(t.step('quests.close_giver','Close the questgiver dialog.',{
            'close':{'kind':'key','value':'Escape','description':'Press Escape to close the questgiver dialog.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'questgiver_close_pass' if s=='close' and not any(p in a['panels'] for p in ['QuestFrame','GossipFrame']) else
                ('controller_failure' if s!='close' else 'client_or_protocol_failure')},diagnostic_action='close'),'questgiver_close_pass')
    finally:
        try:t.clean_panels()
        finally:fixture.restore()
        state,frame=t.observe('restored');t.receipt['restoration']={'frame':frame,'world_position':state['world_position']};t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stage-only',action='store_true');p.add_argument('--details',action='store_true');p.add_argument('--point',type=int,nargs=2);a=p.parse_args()
    if a.details and a.stage_only:p.error('details requires an input trial')
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):
        p.error('requires a bounded observed questgiver point')
    t=Trial(a.output,controller='code' if a.stage_only else 'laya')
    try:suite(t,a.point,a.stage_only,a.details);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))


if __name__=='__main__':main()
