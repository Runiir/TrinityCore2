"""A preparatory entry cannot borrow a failed or partially restored baseline."""
import copy
import pytest
from tools.client_compatibility.interaction_primary_reentry import baseline_matches,NATIVE,LAYOUT


def baseline():
    return {'completed':True,'failure':None,'finished_at':100,'actor':{'guid':1},'runtime':{'world':2},
        'quest_trial_kind':'link','quest_no_message_request':True,'quest_link_original':{'selection':0},
        'native_restoration':{'checks':{k:True for k in NATIVE}},
        'quest_link_restoration':{'checks':{k:True for k in LAYOUT}}}


def test_fully_restored_same_actor_baseline_matches():
    old=baseline();assert baseline_matches(old,old)


@pytest.mark.parametrize('change',['failed','open','failure','actor','runtime','kind','message','selection',
    'native_false','native_missing','layout_false','layout_missing'])
def test_incomplete_or_different_baselines_are_refused(change):
    old=baseline();current=copy.deepcopy(old)
    if change=='failed':old['completed']=False
    elif change=='open':old['finished_at']=None
    elif change=='failure':old['failure']='failed'
    elif change=='actor':current['actor']={'guid':2}
    elif change=='runtime':current['runtime']={'world':3}
    elif change=='kind':old['quest_trial_kind']='layout'
    elif change=='message':old['quest_no_message_request']=False
    elif change=='selection':old['quest_link_original']['selection']=2
    elif change=='native_false':old['native_restoration']['checks']['spells']=False
    elif change=='native_missing':old['native_restoration']['checks'].pop('spells')
    elif change=='layout_false':old['quest_link_restoration']['checks']['rows']=False
    else:old['quest_link_restoration']['checks'].pop('rows')
    assert not baseline_matches(old,current)
