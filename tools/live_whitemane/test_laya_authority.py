import json
from types import SimpleNamespace
from . import decisions,farm_policy,recovery,pending_find,farm_graph,runtime
from .dig_policy import SolveBatches
from .test_farm_loop import row


def test_retained_head_choice_is_accepted_without_an_expert_action_veto(monkeypatch):
    def reply(request,**_):
        value=({'heads':{'archaeology':{'model':'laya','revision':'pinned'}}}
            if isinstance(request,str) else {'revision':'pinned','answers':{'action':{'choice':'observe'}},'token_budget':{}})
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self):return json.dumps(value).encode()
        return Response()
    monkeypatch.setattr(decisions.urllib.request,'urlopen',reply)
    state={'available':True,'casting':False,'artifact_visible':False,'instrument_current':False,'telescope':None}
    assert decisions.archaeology_policy.label(state)=='survey'
    assert decisions.choose(state)[0]=='observe'


def test_laya_can_choose_travel_when_the_pickup_requirement_is_complete(monkeypatch):
    r=row();r['archaeology'].update(can_survey=True,falling=False)
    r['farm_ui']['actionbars']=[{'label':'Teleport','enabled':True}]
    r['pending_find']=None;r['minimap_finds']={'clear':True}
    def choose(state,instructions,options):
        assert not state['pending_pickup'] and not state['pickup']['uncollected']
        assert 'dig' in options and 'teleport' in options
        return 'teleport',{},{}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    assert farm_policy.choose(r,SolveBatches(),{'via_tolbarad':False})[0]=='teleport'


def test_recovery_keeps_unconfirmed_pickup_and_does_not_renew_inactivity(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    r=row();r['archaeology'].update(site_id=187,falling=False,loot_open=False)
    pending_find.latch(r)
    graph=tmp_path/'graph.json';farm_graph.transition(graph,'gather',r,pending=pending_find.load(r))
    session={'last_progress_at':123,'dig_output':None}
    monkeypatch.setattr(recovery.laya_ui,'choose',lambda state,instructions,options:('retry',{},{}))
    monkeypatch.setattr(recovery,'observe',lambda _:r)
    monkeypatch.setattr(recovery.time,'sleep',lambda _:None)
    step={'phase':'dig','local_failure':'artifact interaction did not confirm fragment pickup'}
    assert recovery.run(tmp_path/'recovery',r,step,session,graph)['completed']
    assert pending_find.load(r) and session['last_progress_at']==123
    assert not recovery.retryable('pending find belongs to another owned client')


def test_farm_waits_with_no_progress_use_layas_complete_action_distribution(monkeypatch):
    r=row();r['archaeology'].update(falling=False)
    r['farm_ui']['actionbars']=[{'label':'Teleport','enabled':True}]
    r['minimap_finds']={'clear':True,'status':'no_visible_candidates'}
    session={'via_tolbarad':True,'last_progress_at':10,
        'steps':[{'phase':'wait','completed':True,'started_at':n} for n in (11,12,13)]}
    def choose(state,_,options):
        assert state['combat'] is False and state['mounted'] is False
        assert state['consecutive_actions_without_progress']==3
        assert state['recent_actions'][-1]=={'action':'wait','completed':True,'failure':None}
        assert set(options)=={'wait','teleport'}
        return 'wait',{}, {'answers':{'action':{'choice':'wait','probabilities':{'wait':.6,'teleport':.4}}}}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    def sample(options,weights,k):
        assert options==['wait','teleport'] and weights==[.6,.4]
        return ['teleport']
    monkeypatch.setattr(farm_policy.dig_decisions.random,'choices',sample)
    action,_,receipt=farm_policy.choose(r,SolveBatches(),session)
    assert action=='teleport'
    assert receipt['response']['policy_selection']['probabilities_modified'] is False
    session['last_progress_at']=14
    monkeypatch.setattr(farm_policy.laya_ui,'choose',lambda *_:('wait',{},{}))
    assert farm_policy.choose(r,SolveBatches(),session)[0]=='wait'
