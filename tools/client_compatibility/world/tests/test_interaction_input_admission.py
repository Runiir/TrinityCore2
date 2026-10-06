"""A stale or unavailable admission must stop input after passive observation."""
import pytest
from tools.client_compatibility.interaction_trial import Trial


def trial(events):
    t=Trial.__new__(Trial)
    t.receipt={'cases':[]};t.controller='code';t.persist=lambda:None
    def observe(label):
        events.append(('observe',label))
        return {},{'file':label+'.png'}
    t.observe=observe
    t.execute=lambda action:events.append(('execute',action)) or []
    return t


@pytest.mark.parametrize('admission',[None,{}, {'accepted':False},{'accepted':1}])
def test_refused_admission_never_sends_input_or_calls_outcome(admission):
    events=[];t=trial(events)
    def guard():
        events.append(('admission',admission));return admission
    def outcome(*args):
        pytest.fail('An unsubmitted input has no gameplay outcome')
    with pytest.raises(RuntimeError,match='input admission refused'):
        t.step('attack','Attack the reviewed target.',{'attack':{'kind':'click','value':[1,2]}},
            outcome,diagnostic_action='attack',before_input=guard)
    assert [e[0] for e in events]==['observe','admission']
    assert t.receipt['cases'][0]['input_admission']==admission
    assert 'input_transport' not in t.receipt['cases'][0]


def test_admitted_input_executes_once_between_guard_and_outcome_observation():
    events=[];t=trial(events);action={'kind':'click','value':[1,2]}
    def guard():
        events.append(('admission',None));return {'accepted':True,'age_seconds':5}
    row=t.step('attack','Attack the reviewed target.',{'attack':action},
        lambda *args:{'status':'pass'},diagnostic_action='attack',before_input=guard)
    assert [e[0] for e in events]==['observe','admission','execute','observe']
    assert events[2]==('execute',action)
    assert row['input_admission']=={'accepted':True,'age_seconds':5}
    assert row['status']=='pass'
