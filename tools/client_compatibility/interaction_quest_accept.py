"""Manually accept a native kill quest, read it and abandon it through stock UI."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_macros import require
from .interaction_operations import controls,click_case
from .interaction_quest_fixture import quest_state,restore_autoaccepted
from .interaction_trade import inventory
from .npc_fixture import NpcFixture

QUEST=52
TITLE='Protect the Frontier'


def suite(t,point,stage_only):
    actors.session_entry(t.fixture);t.clean_panels()
    baseline=quest_state(1);items=inventory();fixture=NpcFixture(t.out,t.fixture,261,2)
    if any(q['quest']==QUEST for group in baseline.values() for q in group):
        raise RuntimeError('requires the registered manual quest to be neither active nor rewarded')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT q.Flags,q.StartItem,a.RequiredMoney,a.MaxLevel,a.AllowableClasses,a.AllowableRaces '
            'FROM client442_world.quest_template q JOIN client442_world.quest_template_addon a ON q.ID=a.ID WHERE q.ID=%s',(QUEST,))
        row=q.fetchone()
    if not row or row[0]&0x80000 or row[1] or row[2] or row[3] or row[4] or row[5]:
        raise RuntimeError('manual kill-quest contract changed')
    t.receipt['baseline']={'quests':baseline,'inventory_money':items,'quest':QUEST};t.persist()
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('manual_giver_staged');t.receipt['staging']={'state':state,'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('manual questgiver is not visibly targeted')
        if stage_only:return
        require(t.step('quests.manual_interact','Speak to nearby Guard Thomas.',
            {'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the reviewed visible Guard Thomas.'}},
            lambda b,a,s:{'status':'questgiver_open_pass' if s=='interact' and any(p in a['panels'] for p in ['QuestFrame','GossipFrame']) else
                'client_or_protocol_failure','oracle':{'panels':a['panels'],'errors':a['errors']}},
            diagnostic_action='interact'),'questgiver_open_pass')
        t.receipt['giver_controls']=controls(t);t.persist()
        state,_=t.observe('manual_offered')
        if state.get('quest_giver',{}).get('id')!=QUEST:
            require(click_case(t,'quests.manual_select','Read the offered '+TITLE+' quest.',lambda c:TITLE in c['text'],
                lambda b,a,s:{'status':'quest_details_open_pass' if s and a.get('quest_giver',{}).get('id')==QUEST else
                    'client_or_protocol_failure'}),'quest_details_open_pass')
        if quest_state(1)!=baseline:raise RuntimeError('quest became active before the manual Accept input')
        def accepted(b,a,s):
            native=quest_state(1);added=[q for q in native['active'] if q['quest']==QUEST]
            passed=s and len(added)==1 and added[0]['status']==3 and any(q.get('id')==QUEST for q in a.get('quests',[]))
            return {'status':'quest_manual_accept_pass' if passed else 'client_or_protocol_failure',
                'oracle':{'native':native,'native_was_absent_before_accept':True,'quests':a.get('quests')}}
        require(click_case(t,'quests.manual_accept','Accept '+TITLE+'.',
            lambda c:c['name']=='QuestFrameAcceptButton' and c['text']=='Accept',accepted),'quest_manual_accept_pass')
        t.clean_panels();state,_=t.observe('accepted_log_binding')
        if not state.get('quest_log_keys'):raise RuntimeError('no observed quest-log binding')
        require(t.step('quests.manual_log','Open the quest log.',
            {'log':{'kind':'key','value':binding_key(state['quest_log_keys'][0]),'description':'Use the observed quest-log binding.'}},
            lambda b,a,s:{'status':'quest_log_open_pass' if 'QuestLogFrame' in a['panels'] else 'client_or_protocol_failure'},
            diagnostic_action='log'),'quest_log_open_pass')
        state,_=t.observe('manual_log_open')
        if any(h.get('title')=='Elwynn Forest' and h.get('collapsed') for h in state.get('quest_headers',[])):
            require(click_case(t,'quests.manual_expand','Expand the Elwynn Forest quests.',lambda c:c['text'].strip()=='Elwynn Forest',
                lambda b,a,s:{'status':'quest_zone_expand_pass' if s and any(q.get('id')==QUEST for q in a.get('quests',[])) else
                    'client_or_protocol_failure'}),'quest_zone_expand_pass')
        require(click_case(t,'quests.manual_read_log','Read '+TITLE+' in the quest log.',lambda c:c['text'].strip()==TITLE,
            lambda b,a,s:{'status':'quest_log_details_pass' if s and a.get('quest_log_selection',{}).get('id')==QUEST else
                'client_or_protocol_failure','oracle':{'selection':a.get('quest_log_selection')}}),'quest_log_details_pass')
        state,_=t.observe('manual_abandon_guard')
        if state.get('quest_log_selection',{}).get('abandon_name')!=TITLE:raise RuntimeError('manual quest abandonment is not correctly selected')
        require(click_case(t,'quests.manual_abandon_prompt','Abandon only the trial '+TITLE+' quest.',
            lambda c:c['name']=='QuestLogFrameAbandonButton',
            lambda b,a,s:{'status':'quest_abandon_prompt_pass' if s and any(p.get('which')=='ABANDON_QUEST' and TITLE in p.get('text','')
                for p in a.get('quest_popups',[])) else 'client_or_protocol_failure'}),'quest_abandon_prompt_pass')
        require(click_case(t,'quests.manual_abandon_confirm','Confirm abandoning the trial quest.',
            lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Abandon','Yes'],
            lambda b,a,s:{'status':'quest_abandon_pass' if s and quest_state(1)==baseline and inventory()==items else
                'client_or_protocol_failure'}),'quest_abandon_pass')
    finally:
        try:t.clean_panels();restore_autoaccepted(t,baseline,quest=QUEST)
        finally:fixture.restore()
        t.receipt['restoration']={'quests_restored':quest_state(1)==baseline,'inventory_money_restored':inventory()==items};t.persist()
        if not all(t.receipt['restoration'].values()):raise RuntimeError('manual quest trial requires restoration')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2);p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):
        p.error('requires the separately reviewed bounded questgiver point')
    t=Trial(a.output,controller='code')
    try:suite(t,a.point,a.stage_only);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
