"""Recovery must bind to the exact failed layout and restored native fixture."""
import copy
import pytest
from tools.client_compatibility.interaction_quest_selection_recovery import source_matches,NATIVE,LAYOUT


def baseline():
    checks={k:k!='selection' for k in LAYOUT}
    return {'completed':False,'finished_at':100,'failure':'RuntimeError: original quest/header/selection state did not restore',
        'quest_link_layout_calibration':True,'actor':{'guid':1},'runtime':{'world':1},
        'quest_link_restoration':{'checks':checks},'native_restoration':{'checks':{k:True for k in NATIVE}},
        'quest_link_original':{'selection':0}}


def test_exact_selection_failure_with_other_values_restored_is_recoverable():
    old=baseline();assert source_matches(old,old)


@pytest.mark.parametrize('change',['open','completed','different_failure','link_trial','original_nonzero',
    'native_failure','missing_native','other_layout_failure','missing_layout','other_actor','other_runtime'])
def test_unbound_or_partially_restored_failure_is_refused(change):
    old=baseline();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='completed':old['completed']=True
    elif change=='different_failure':old['failure']='another failure'
    elif change=='link_trial':old['quest_link_layout_calibration']=False
    elif change=='original_nonzero':old['quest_link_original']['selection']=1
    elif change=='native_failure':old['native_restoration']['checks']['spells']=False
    elif change=='missing_native':old['native_restoration']['checks'].pop('spells')
    elif change=='other_layout_failure':old['quest_link_restoration']['checks']['rows']=False
    elif change=='missing_layout':old['quest_link_restoration']['checks'].pop('rows')
    elif change=='other_actor':current['actor']={'guid':2}
    else:current['runtime']={'world':2}
    assert not source_matches(old,current)
