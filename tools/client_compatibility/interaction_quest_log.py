"""Read and abandon only the disposable accepted kill quest with normal inputs."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .interaction_quest_fixture import quest_state,restore_autoaccepted,QUEST
from .interaction_trade import inventory


def suite(t):
    state,_=t.observe('quest_log_fixture');t.clean_panels();native=quest_state(t.fixture['guid'])
    if t.fixture['guid']!=1 or not any(q['quest']==QUEST and q['status']==3 for q in native['active']):
        raise RuntimeError('requires the existing owned incomplete disposable quest')
    baseline={**native,'active':[q for q in native['active'] if q['quest']!=QUEST]}
    items=inventory();t.receipt['baseline']={'quest_state':native,'restored_quest_state':baseline,'inventory_money':items};t.persist()
    if not state.get('quest_log_keys') or not state.get('quest_probe',{}).get('active'):raise RuntimeError('requires observed quest binding and accepted quest')
    try:
        require(t.step('quests.open_populated_log','Open the quest log to read Beating Them Back!.',{
            'log':{'kind':'key','value':binding_key(state['quest_log_keys'][0]),'description':'Press '+state['quest_log_keys'][0]+': open the quest log.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'quest_log_open_pass' if s=='log' and 'QuestLogFrame' in a['panels'] else
                ('controller_failure' if s!='log' else 'client_or_protocol_failure')},diagnostic_action='log'),'quest_log_open_pass')
        state,_=t.observe('quest_log_open')
        if any(h.get('title')=='Elwynn Forest' and h.get('collapsed') for h in state.get('quest_headers',[])):
            require(click_case(t,'quests.expand_zone','Expand the Elwynn Forest quest section.',lambda c:c['text'].strip()=='Elwynn Forest',
                lambda b,a,s:{'status':'quest_zone_expand_pass' if s and any(q.get('id')==QUEST for q in a.get('quests',[])) else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'quests':a.get('quests'),'headers':a.get('quest_headers')}}),'quest_zone_expand_pass')
        require(click_case(t,'quests.select_log_entry','Read Beating Them Back! from the quest log.',
            lambda c:c['text'].strip()=='Beating Them Back!',
            lambda b,a,s:{'status':'quest_log_details_pass' if s and a.get('quest_log_selection',{}).get('id')==QUEST and
                'McBride' in a['quest_log_selection'].get('description','') and '6 Blackrock' in a['quest_log_selection'].get('objectives','') else
                ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'selection':a.get('quest_log_selection'),'probe':a.get('quest_probe')}}),'quest_log_details_pass')
        state,_=t.observe('abandon_guard')
        if state.get('quest_log_selection',{}).get('abandon_name')!='Beating Them Back!':raise RuntimeError('disposable abandonment selection is not prepared')
        require(click_case(t,'quests.abandon_prompt','Abandon the disposable Beating Them Back! quest.',lambda c:c['name']=='QuestLogFrameAbandonButton',
            lambda b,a,s:{'status':'quest_abandon_prompt_pass' if s and any(p.get('which')=='ABANDON_QUEST' and 'Beating Them Back!' in p.get('text','') for p in a.get('quest_popups',[])) else
                ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'popups':a.get('quest_popups')}}),'quest_abandon_prompt_pass')
        def abandoned(b,a,s):
            after=quest_state(1);unchanged=inventory()==items
            passed=s and after==baseline and not a.get('quest_probe',{}).get('active') and unchanged
            return {'status':'quest_abandon_pass' if passed else ('controller_failure' if not s else 'client_or_protocol_failure'),
                'oracle':{'native':after,'probe':a.get('quest_probe'),'inventory_money_unchanged':unchanged}}
        require(click_case(t,'quests.confirm_abandon','Confirm abandoning Beating Them Back!.',
            lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Abandon','Yes'],abandoned),'quest_abandon_pass')
    finally:
        t.clean_panels();restore_autoaccepted(t,baseline)
        t.receipt['restoration']={'native':quest_state(1),'inventory_money_restored':inventory()==items};t.persist()
        if not t.receipt['restoration']['inventory_money_restored']:raise RuntimeError('quest fixture changed inventory/money')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output)
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))


if __name__=='__main__':main()
