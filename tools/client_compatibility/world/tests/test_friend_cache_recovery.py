"""Cache reset admits only one source-bound presentation difference."""
import copy
import pytest
from tools.client_compatibility.interaction_friend_cache_recovery import source_matches,NATIVE,FRIENDS


def fixture(prepared=False):
    return {'completed':prepared,'failure':None if prepared else
        'RuntimeError: fresh target control was not observed: fixture.friend_whisper.row',
        'finished_at':100,'friend_cache_restore_required':prepared,'actor':{'guid':1},'runtime':{'client':12},
        'bridge_native_restoration':{'checks':{k:True for k in NATIVE}},
        'friend_restoration':{'checks':{k:k!='public_friends' for k in FRIENDS}},
        'original_social':[[1,2,1,''],[2,1,1,'']],
        'original_public_friends':[{'name':'Harnesstwo','connected':False,'level':0,'notes':''}],
        'original_quest_log':{'selection':0},'custom_script_permission':'blocked_by_user',
        'softTargetInteract':{'original':'0','current_stock_disabled':'1','original_restored':False}}


@pytest.mark.parametrize('prepared',[False,True])
def test_exact_closed_cache_only_difference_can_be_cleaned_without_qualification(prepared):
    old=fixture(prepared);assert source_matches(old,old)


def unsent_fixture():
    old=fixture();old['failure']='RuntimeError: exact owned friend whisper text or target differs'
    old['friend_whisper_guard']={'exact':False,'submitted':False,'input_replayed':False,
        'target':'Harnesstwo','token':'TC442UI:friend_1487b663'}
    return old


def test_closed_unsent_whisper_with_only_cache_difference_can_be_restored():
    old=unsent_fixture();assert source_matches(old,old)


@pytest.mark.parametrize('change',[{'submitted':True},{'input_replayed':True},{'exact':True},
    {'target':'Anotherplayer'},{'token':'unrelated'}])
def test_submitted_changed_or_unattributable_whisper_cannot_authorize_cache_cleanup(change):
    old=unsent_fixture();old['friend_whisper_guard'].update(change)
    assert not source_matches(old,old)


@pytest.mark.parametrize('change',['open','another_failure','actor','runtime','native_failure','missing_native',
    'other_friend_failure','missing_friend','already_restored','different_original_level','different_note',
    'different_social','quest_selection','script_permission','original_cvar_restored','unmarked_prepared'])
def test_other_or_unrestored_sources_cannot_authorize_cache_cleanup(change):
    old=fixture();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='another_failure':old['failure']='another failure'
    elif change=='actor':current['actor']['guid']=2
    elif change=='runtime':current['runtime']['client']=13
    elif change=='native_failure':old['bridge_native_restoration']['checks']['pose']=False
    elif change=='missing_native':old['bridge_native_restoration']['checks'].pop('pose')
    elif change=='other_friend_failure':old['friend_restoration']['checks']['quest_layout']=False
    elif change=='missing_friend':old['friend_restoration']['checks'].pop('quest_layout')
    elif change=='already_restored':old['friend_restoration']['checks']['public_friends']=True
    elif change=='different_original_level':old['original_public_friends'][0]['level']=1
    elif change=='different_note':old['original_public_friends'][0]['notes']='changed note'
    elif change=='different_social':old['original_social'][0][-1]='changed note'
    elif change=='quest_selection':old['original_quest_log']['selection']=2
    elif change=='script_permission':old['custom_script_permission']='enabled'
    elif change=='original_cvar_restored':old['softTargetInteract']['original_restored']=True
    else:old['completed']=True;old['failure']=None
    assert not source_matches(old,current)
