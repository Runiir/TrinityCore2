"""Ignore delivery must prove suppression between attributable positive controls."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_ignored_chat import feedback_checks,general_count,negative_checks
from tools.client_compatibility.interaction_ignore import wire_checks
from tools.client_compatibility.interaction_ignore_friend import current_matches,ORIGINAL,IGNORED,selected_ignore_contract
from tools.client_compatibility.interaction_friend_cache_recovery import source_matches
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_ignore_trial import trace,HIGH
from tools.client_compatibility.world.tests.test_friend_cache_recovery import fixture


def feedback(guid=2,reason=0):
    return [{'name':'CMSG_CHAT_REPORT_IGNORED','direction':'from_client',
        'body':Writer().guid(guid,HIGH).pack('B',reason).finish().hex()},
        {'name':'CMSG_CHAT_IGNORED','direction':'to_native','body':bytes([0,4,3]).hex()}]


def general(count=4):
    return {'selected':1,'message_types_available':True,'message_types':['WHISPER'],
        'windows':[{'id':1,'name':'General','frame_visible':True,'message_count':count}]}


def observations():
    token='TC442UI:reply_seed_01234567';primary=feedback()
    body=struct.pack('<BiQ',7,0,2)+token.encode()+b'\0'
    primary.extend([{'name':'SMSG_MESSAGECHAT','direction':'from_native','body':body.hex()},
        {'name':'SMSG_CHAT','direction':'to_client','body':(b'\x07'+token.encode()).hex()}])
    notice=struct.pack('<BiQ',25,0,1)+b'Harnessone\0'
    peer=[{'name':'SMSG_MESSAGECHAT','direction':'from_native','body':notice.hex()},
        {'name':'SMSG_CHAT','direction':'to_client','body':b'\x19'.hex()}]
    return primary,peer,token,[{'chat_probes':[]} for _ in range(3)],general(),general()


def test_owned_friend_add_remove_preserves_separate_ignore_bit_contract():
    for remove in [False,True]:assert all(wire_checks(trace(remove,guid=2,name='Harnesstwo'),
        remove,guid=2,name='Harnesstwo').values())
    assert current_matches(ORIGINAL,False) and current_matches(IGNORED,True)
    for other in [[[1,2,2,''],[2,1,1,'']],[[1,2,3,'changed'],[2,1,1,'']],[[1,3,3,''],[2,1,1,'']]]:
        assert not current_matches(other,True)


def test_complete_owned_suppression_and_feedback_is_admissible():
    assert all(negative_checks(*observations()).values())


@pytest.mark.parametrize('change',['no_modern_feedback','no_native_feedback','wrong_sender','wrong_reason',
    'no_native_delivery','no_modern_delivery','public_delivery','too_few_samples','visible_line_added',
    'hidden_general','disabled_whispers','no_notice','wrong_notice_sender','duplicate_notice','lua_error'])
def test_missing_wrong_or_unsuppressed_outcomes_fail(change):
    primary,peer,token,states,before,after=observations()
    if change=='no_modern_feedback':primary.pop(0)
    elif change=='no_native_feedback':primary.pop(1)
    elif change=='wrong_sender':primary[:2]=feedback(guid=3)
    elif change=='wrong_reason':primary[:2]=feedback(reason=1)
    elif change=='no_native_delivery':primary.pop(2)
    elif change=='no_modern_delivery':primary.pop(3)
    elif change=='public_delivery':states[1]['chat_probes']=[{'text':token,'event':'CHAT_MSG_WHISPER'}]
    elif change=='too_few_samples':states.pop()
    elif change=='visible_line_added':after=general(5)
    elif change=='hidden_general':before['windows'][0]['frame_visible']=False
    elif change=='disabled_whispers':before['message_types']=[]
    elif change=='no_notice':peer=[]
    elif change=='wrong_notice_sender':peer[0]['body']=(struct.pack('<BiQ',25,0,3)+b'Harnessone\0').hex()
    elif change=='duplicate_notice':peer.append(copy.deepcopy(peer[0]))
    else:states[0]['lua_errors']=['failed']
    assert not all(negative_checks(primary,peer,token,states,before,after).values())


def test_feedback_rejects_trailing_modern_bytes():
    rows=feedback();rows[0]['body']+='00'
    with pytest.raises(ValueError):feedback_checks(rows)


def test_general_count_refuses_missing_or_boolean_counter():
    assert general_count(general())==4
    assert general_count(general(True)) is None
    assert general_count({}) is None


def test_closed_failed_ignore_trial_can_restore_only_its_isolated_cache_difference():
    old=fixture(True);old.update(completed=False,failure='RuntimeError: owned ignored-chat outcomes differ',
        ignored_chat_restoration={'checks':{k:True for k in ['native_social','public_friends_preserved','stock_ignore_empty']}})
    assert source_matches(old,old)
    for key in old['ignored_chat_restoration']['checks']:
        bad=copy.deepcopy(old);bad['ignored_chat_restoration']['checks'][key]=False
        assert not source_matches(bad,bad)
    bad=copy.deepcopy(old);bad['failure']='RuntimeError: another failure';assert not source_matches(bad,bad)


def test_disabled_selected_tab_requires_both_visible_ignore_controls():
    rows=[{'name':'FriendsTabHeaderTab2','text':'Ignore','enabled':False},
        {'name':'FriendsFrameIgnorePlayerButton','enabled':True},{'name':'FriendsFrameUnsquelchButton'}]
    assert selected_ignore_contract(rows)
    for index in range(3):
        other=copy.deepcopy(rows);other.pop(index);assert not selected_ignore_contract(other)
    other=copy.deepcopy(rows);other[0]['enabled']=True;assert not selected_ignore_contract(other)


def test_only_exact_closed_unrestored_ignore_bit_failure_can_be_cleaned():
    from tools.client_compatibility.interaction_ignore_recovery import source_matches as recoverable
    old=fixture();old['failure']='RuntimeError: target is not an enabled ordinary button'
    old['friend_restoration']['checks']['native_social']=False;old['ignored_chat_source']={'sha256':'a'*64}
    peer={'finished_at':100,'actor':{'guid':2},'parked_restoration':{'checks':{str(i):True for i in range(19)}}}
    assert recoverable(old,old,peer)
    for field in ['resources','stats','spells','actions','pose','afk','position']:
        bad=copy.deepcopy(old);bad['bridge_native_restoration']['checks'][field]=False
        assert not recoverable(bad,bad,peer)
    for field in ['inventory_money','offline_owned_dwarf','quest_layout','native_quests','same_session','group']:
        bad=copy.deepcopy(old);bad['friend_restoration']['checks'][field]=False
        assert not recoverable(bad,bad,peer)
    bad=copy.deepcopy(old);bad['failure']='another failure';assert not recoverable(bad,bad,peer)
    bad=copy.deepcopy(old);bad['original_social'][0][3]='changed';assert not recoverable(bad,bad,peer)
    bad=copy.deepcopy(old);bad['custom_script_permission']='enabled';assert not recoverable(bad,bad,peer)
    bad=copy.deepcopy(peer);bad['parked_restoration']['checks']['0']=False;assert not recoverable(old,old,bad)
