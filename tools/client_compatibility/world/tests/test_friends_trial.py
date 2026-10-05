"""The social oracle rejects mismatched requests, GUIDs and native outcomes."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friends import (wire_checks,HIGH,recovery_source_matches,
    menu_recovery_source_matches,FRIEND,REMOVE_NAME)
from tools.client_compatibility.world.buffer import Writer


def trace(result=7,guid=3,name='Harnessdwarf',remove=False):
    op='CMSG_DEL_FRIEND' if remove else 'CMSG_ADD_FRIEND'
    request=(Writer().pack('I',1).guid(guid,HIGH).finish() if remove else
        Writer().bits(len(name),9).bits(0,9).raw(name.encode()).finish())
    native=struct.pack('<Q',guid) if remove else name.encode()+b'\0\0'
    status=struct.pack('<BQ',result,guid)+(b'\0' if result==7 else b'')
    modern=Writer().pack('B',result).guid(guid,HIGH if guid else 0).guid().pack('IBIII',1,0,0,0,0).bits(0,10).finish()
    return [{'name':n,'direction':d,'body':b.hex()} for n,d,b in [(op,'from_client',request),(op,'to_native',native),
        ('SMSG_FRIEND_STATUS','from_native',status),('SMSG_FRIEND_STATUS','to_client',modern)]]


@pytest.mark.parametrize('result,guid,name,remove',[(7,3,'Harnessdwarf',False),(8,3,'Harnessdwarf',False),
    (9,1,'Harnessone',False),(4,0,'Zzqvxfixture',False),(5,3,'Harnessdwarf',True)])
def test_exact_offline_lifecycle_and_error_responses(result,guid,name,remove):
    assert all(wire_checks(trace(result,guid,name,remove),name,guid,result,remove).values())


@pytest.mark.parametrize('index',[0,1,2,3])
def test_each_missing_or_repeated_packet_breaks_attribution(index):
    rows=trace();missing=copy.deepcopy(rows);missing.pop(index)
    assert not all(wire_checks(missing,'Harnessdwarf',3,7).values())
    assert not all(wire_checks(rows+[rows[index]],'Harnessdwarf',3,7).values())


def test_success_and_another_guid_cannot_masquerade_as_duplicate_error():
    assert not all(wire_checks(trace(),'Harnessdwarf',3,8).values())
    assert not all(wire_checks(trace(8,2),'Harnessdwarf',3,8).values())


def test_trailing_modern_bytes_are_rejected():
    rows=trace();rows[-1]['body']+='00'
    with pytest.raises(ValueError):wire_checks(rows,'Harnessdwarf',3,7)


def recovery_fixture():
    current={'actor':{'guid':1},'runtime':{'client':{'pid':12,'start_ticks':'34'}}}
    old={**copy.deepcopy(current),'completed':False,'finished_at':99,
        'failure':'RuntimeError: panel cleanup did not change state; refusing to replay Escape',
        'cases':[{'id':k,'status':'friend_status_pass','oracle':{'checks':{'native':True}}} for k in
            ['friends.add_friend','friends.duplicate_friend_error','friends.self_friend_error','friends.nonexistent_friend_error']]+
            [{'id':'friends.remove_friend','status':'infrastructure_failure',
              'error':'RuntimeError: chat edit differs from the selected command; refusing submission'}],
        'chat_submission_checks':[{'submitted':False,'selected_text':'/removefriend '+FRIEND,
            'observed_text':'/removefriend '+REMOVE_NAME,'observed_focused':True}]}
    return old,current


def test_only_exact_failed_autocomplete_source_is_recoverable():
    old,current=recovery_fixture();assert recovery_source_matches(old,current)


@pytest.mark.parametrize('field,value',[('completed',True),('finished_at',None),('failure','another failure'),
    ('actor',{'guid':2}),('runtime',{'client':{'pid':12,'start_ticks':'35'}})])
def test_recovery_rejects_another_verdict_actor_or_lifetime(field,value):
    old,current=recovery_fixture();old[field]=value;assert not recovery_source_matches(old,current)


@pytest.mark.parametrize('field,value',[('submitted',True),('selected_text','/removefriend Harnesstwo'),
    ('observed_text','/removefriend Harnessdwarf-AnotherRealm'),('observed_focused',False)])
def test_recovery_cannot_cancel_another_or_submitted_edit(field,value):
    old,current=recovery_fixture();old['chat_submission_checks'][0][field]=value
    assert not recovery_source_matches(old,current)


def test_recovery_requires_every_prior_friend_outcome_to_pass():
    old,current=recovery_fixture();old['cases'][0]['oracle']['checks']['native']=False
    assert not recovery_source_matches(old,current)


def menu_failure():
    _,current=recovery_fixture()
    checks={k:False for k in ['exact_modern_request','exact_native_request','exact_native_status',
        'exact_modern_status','native_social','public_friends']}
    checks.update({k:True for k in ['ordinary_input','friends_ready','stock_window','dialog_closed','chat_closed','clean']})
    old={**copy.deepcopy(current),'completed':False,'finished_at':101,
        'failure':'RuntimeError: operation did not advance: fixture.friends.recovery_remove client_or_protocol_failure',
        'source_preflight':{'source':True},'cases':[{'id':'fixture.friends.close','status':'friend_window_closed'},
            {'id':'fixture.friends.recovery_open','status':'friend_window_open'},
            {'id':'fixture.friends.recovery_remove','status':'client_or_protocol_failure',
             'input':{'kind':'chat','value':'/removefriend '+REMOVE_NAME},'oracle':{'checks':checks,'packets':[]}}]}
    return old,current


def test_closed_no_packet_owned_removal_failure_can_use_another_cleanup_path():
    old,current=menu_failure();assert menu_recovery_source_matches(old,current)


@pytest.mark.parametrize('change',['packet','another_input','changed_social','unclosed_chat','failed_preflight'])
def test_another_removal_or_partial_native_mutation_is_not_the_same_recovery_source(change):
    old,current=menu_failure();case=old['cases'][-1]
    if change=='packet':case['oracle']['packets']=[{'name':'CMSG_DEL_FRIEND'}]
    elif change=='another_input':case['input']['value']='/removefriend Harnesstwo'
    elif change=='changed_social':case['oracle']['checks']['native_social']=True
    elif change=='unclosed_chat':case['oracle']['checks']['chat_closed']=False
    else:old['source_preflight']['source']=False
    assert not menu_recovery_source_matches(old,current)
