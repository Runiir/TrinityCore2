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


def test_laya_can_choose_travel_instead_of_the_previous_fixed_dig_stage(monkeypatch):
    r=row();r['archaeology'].update(can_survey=True,falling=False)
    r['farm_ui']['actionbars']=[{'label':'Teleport','enabled':True}]
    r['pending_find']={'attempts':1};r['minimap_finds']={'clear':False}
    def choose(state,instructions,options):
        assert state['pending_pickup'] and 'dig' in options and 'teleport' in options
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
