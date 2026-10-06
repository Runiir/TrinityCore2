"""Offline recovery requires the exact owned Follow and its instance rejection."""
import copy
import pytest
from tools.client_compatibility.interaction_pet_follow_disconnect import proof


def sample():
    failed={'native_session':'c03d6414','follow_started_at':1791284098.274447,
        'finished_at':1791284162.7473273,
        'native_pet_before':{'guid':17383896348356509717,'map':0}}
    entry={'started_at':1791283780.3951285,'finished_at':1791283815.5885274}
    rows=[dict(session='c03d6414',time=1791284104.6527338,direction='from_client',
        name='CMSG_PET_ACTION',body='01a215680428010080030000000000000000000000000000')]
    events=[dict(session='20083d6a',time=1791283795.8099694,event='instance_authenticated',account_id=2),
        dict(session='20083d6a',time=1791284104.652795,event='world_connection_closed',error='unsupported pet action shape'),
        dict(session='c03d6414',time=1791284104.65289,event='world_connection_closed',error='Operation canceled [system:125 at source]'),
        dict(session='c03d6414',time=1791284104.6529527,event='native_stream_closed',error='Operation canceled [system:125 at source]')]
    return failed,entry,rows,events


def test_actual_ui123_follow_body_attributes_instance_rejection_without_native_command():
    result=proof(*sample())
    assert result['decoded']['action_value']==1
    assert result['native_command_sent'] is False


def test_journal_iterators_retain_authentication_after_scanning_the_closure():
    failed,entry,rows,events=sample()
    assert proof(failed,entry,iter(rows),iter(events))==proof(failed,entry,rows,events)


@pytest.mark.parametrize('change',['foreign_session','duplicate','native_command','abandon',
    'wrong_pet','wrong_map','dismiss','target','position','trailing','foreign_instance',
    'wrong_account','late_rejection','wrong_error','missing_cancel'])
def test_recovery_refuses_unattributable_request_or_disconnect(change):
    failed,entry,rows,events=copy.deepcopy(sample())
    if change=='foreign_session':rows[0]['session']='foreign'
    elif change=='duplicate':rows.append(dict(rows[0]))
    elif change=='native_command':rows.append(dict(rows[0],direction='to_native'))
    elif change=='abandon':rows.append(dict(rows[0],name='CMSG_PET_ABANDON'))
    elif change=='wrong_pet':failed['native_pet_before']['guid']+=1
    elif change=='wrong_map':failed['native_pet_before']['map']=1
    elif change=='dismiss':rows[0]['body']=rows[0]['body'].replace('01008003','03008003')
    elif change=='target':rows[0]['body']=rows[0]['body'][:22]+'010001'+rows[0]['body'][24:]
    elif change=='position':rows[0]['body']=rows[0]['body'][:-8]+'0000803f'
    elif change=='trailing':rows[0]['body']+='00'
    elif change=='foreign_instance':events[0]['session']='foreign'
    elif change=='wrong_account':events[0]['account_id']=1
    elif change=='late_rejection':events[1]['time']+=2
    elif change=='wrong_error':events[1]['error']='unrelated failure'
    elif change=='missing_cancel':events.pop()
    with pytest.raises((RuntimeError,ValueError)):proof(failed,entry,rows,events)
