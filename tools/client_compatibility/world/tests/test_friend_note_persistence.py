"""Persistence requires source-bound logout and native-reloaded owned contacts."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friend_note_persistence import (
    prepared_matches,contact_checks,NOTE,PHASE,ORIGINAL_FIELDS,LOGOUT_CHECKS,GUID,HIGH,FRIEND)
from tools.client_compatibility.world.buffer import Writer


def preparation():
    d={k:{} for k in ORIGINAL_FIELDS}
    d.update(completed=True,failure=None,finished_at=100,actor={'guid':1},runtime={'client':{'pid':12,'start_ticks':'34'}},
        phase=PHASE,marker_note=NOTE,logout_checks={k:True for k in LOGOUT_CHECKS},
        original_social=[[1,2,1,''],[2,1,1,'']],
        original_public_friends=[{'name':FRIEND,'connected':False,'level':0,'notes':''}],
        original_quest_log={'selection':0},custom_script_permission='blocked_by_user',
        softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False})
    return d


def test_closed_owned_logout_preserves_original_empty_note_and_script_boundary():
    old=preparation();assert prepared_matches(old,old)


@pytest.mark.parametrize('change',['open','failed','failure','actor','runtime','phase','marker','missing_check',
    'failed_check','missing_original','original_note','public_note','quest_selection','scripts','unrestored'])
def test_unbound_or_incomplete_preparation_cannot_authorize_entry(change):
    old=preparation();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='failed':old['completed']=False
    elif change=='failure':old['failure']='another failure'
    elif change=='actor':current['actor']['guid']=2
    elif change=='runtime':current['runtime']['client']['start_ticks']='35'
    elif change=='phase':old['phase']='another screen'
    elif change=='marker':old['marker_note']='another note'
    elif change=='missing_check':old['logout_checks'].pop('native_offline')
    elif change=='failed_check':old['logout_checks']['native_complete']=False
    elif change=='missing_original':old.pop('original_inventory')
    elif change=='original_note':old['original_social'][0][-1]=NOTE
    elif change=='public_note':old['original_public_friends'][0]['notes']=NOTE
    elif change=='quest_selection':old['original_quest_log']['selection']=2
    elif change=='scripts':old['custom_script_permission']='enabled'
    else:old['softTargetInteract']['original_restored']=True
    assert not prepared_matches(old,current)


def trace(note=NOTE,guid=GUID,realm=1,status=0,flags=3):
    native=struct.pack('<IIQI',flags,1,guid,1)+note.encode()+b'\0'+struct.pack('<B',status)
    if status:native+=struct.pack('<III',12,1,1)
    modern=Writer().pack('I',flags).bits(1,8).guid(guid,HIGH).guid().pack('IIIBIII',realm,1,1,status,
        12 if status else 0,1 if status else 0,1 if status else 0).bits(len(note),10).raw(note.encode()).finish()
    return [{'name':'SMSG_CONTACT_LIST','direction':d,'body':b.hex()} for d,b in
        [('from_native',native),('to_client',modern)]]


def test_native_and_modern_owned_offline_marker_lists_are_reloaded_without_rewrite():
    assert all(contact_checks(trace()).values())


@pytest.mark.parametrize('change',['no_native','no_modern','wrong_note','wrong_guid','wrong_realm','online',
    'rewrite','extra_list','mismatched_flags'])
def test_another_or_rewritten_contact_cannot_qualify_persistence(change):
    rows=trace()
    if change=='no_native':rows.pop(0)
    elif change=='no_modern':rows.pop(1)
    elif change=='wrong_note':rows=trace(note='another note')
    elif change=='wrong_guid':rows=trace(guid=3)
    elif change=='wrong_realm':rows=trace(realm=2)
    elif change=='online':rows=trace(status=1)
    elif change=='rewrite':rows.append({'name':'CMSG_SET_CONTACT_NOTES','direction':'from_client','body':''})
    elif change=='extra_list':rows.append(rows[0])
    else:rows[1]=trace(flags=7)[1]
    assert not all(contact_checks(rows).values())


@pytest.mark.parametrize('side',[0,1])
def test_trailing_or_truncated_contact_bytes_are_rejected(side):
    rows=trace();rows[side]['body']+='00'
    with pytest.raises(ValueError):contact_checks(rows)
    rows=trace();rows[side]['body']=rows[side]['body'][:-2]
    with pytest.raises(ValueError):contact_checks(rows)
