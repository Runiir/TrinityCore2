from . import intent_queue,farm_policy
from .dig_policy import SolveBatches
from .test_farm_loop import row


def ready():
    r=row();r['archaeology'].update(can_survey=True,site_id=493,loot_open=False,falling=False)
    r['farm_ui']['route']={'kind':'dig'}
    return r


def test_laya_dig_selection_is_retained_without_another_root_model_call(monkeypatch):
    r=ready();session={'steps':[],'via_tolbarad':False,'stop_on':'recipe'}
    calls=[]
    def choose(*args):calls.append(args);return 'dig',{'selected':True},{'answers':{}}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    first=farm_policy.choose(r,SolveBatches(),session)
    second=farm_policy.choose(r,SolveBatches(),session)
    assert first[0]==second[0]=='dig' and len(calls)==1
    assert second[2]['model_decision_reused'] and second[2]['request']==first[2]['request']


def test_combat_and_solve_facts_interrupt_a_retained_dig_task():
    r=ready();q=intent_queue.IntentQueue({})
    q.offer('dig',None,{'choice':'dig'},r)
    options={'dig':('',None),'combat':('',None)}
    r['movement']['in_combat']=True
    assert q.retained(r,options) is None
    q.offer('combat',None,{'choice':'combat'},r)
    assert q.jobs[0]['action']=='combat'
    q.finish('combat');r['movement']['in_combat']=False
    assert q.retained(r,options)[0]=='dig'
    options['solve_7']=('',{'race':7})
    assert q.retained(r,options) is None
    r['pending_find']={'out_of_range':False}
    assert q.retained(r,options)[2]['current_priority']==80


def test_repeated_acceptance_coalesces_and_a_failed_task_is_removed():
    r=ready();q=intent_queue.IntentQueue({})
    for _ in range(20):q.offer('dig',None,{'choice':'dig'},r)
    assert len(q.jobs)==1
    q.finish('dig',retain=True)
    assert q.retained(r,{'dig':('',None)})
    q.finish('dig')
    assert q.retained(r,{'dig':('',None)}) is None
    q.offer('dig',None,{'choice':'dig'},r)
    r['archaeology']['site_id']=321
    assert q.retained(r,{'dig':('',None)}) is None
