"""Ignore attribution rejects wrong contacts, outcomes and partial packet traces."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_ignore import wire_checks,source_matches,CONTEXT,GUID,HIGH,FRIEND
from tools.client_compatibility.world.buffer import Writer


def trace(remove=False,guid=GUID,name=FRIEND,result=None):
    op='CMSG_DEL_IGNORE' if remove else 'CMSG_ADD_IGNORE';result=result if result is not None else (16 if remove else 15)
    modern=(Writer().pack('I',1).guid(guid,HIGH).finish() if remove else
        Writer().bits(len(name),9).guid().raw(name.encode()).finish())
    native=struct.pack('<Q',guid) if remove else name.encode()+b'\0'
    status=struct.pack('<BQ',result,guid)
    reply=Writer().pack('B',result).guid(guid,HIGH).guid().pack('IBIII',1,0,0,0,0).bits(0,10).finish()
    return [{'name':n,'direction':d,'body':b.hex()} for n,d,b in [(op,'from_client',modern),(op,'to_native',native),
        ('SMSG_FRIEND_STATUS','from_native',status),('SMSG_FRIEND_STATUS','to_client',reply)]]


@pytest.mark.parametrize('remove',[False,True])
def test_exact_owned_ignore_add_and_remove(remove):
    assert all(wire_checks(trace(remove),remove).values())


@pytest.mark.parametrize('index',[0,1,2,3])
def test_each_missing_or_duplicate_packet_breaks_attribution(index):
    rows=trace();missing=copy.deepcopy(rows);missing.pop(index)
    assert not all(wire_checks(missing).values())
    assert not all(wire_checks(rows+[rows[index]]).values())


@pytest.mark.parametrize('kwargs',[{'guid':2},{'name':'Harnesstwo'},{'result':14}])
def test_another_contact_or_duplicate_result_cannot_qualify(kwargs):
    assert not all(wire_checks(trace(**kwargs)).values())


def test_trailing_modern_bytes_are_rejected():
    rows=trace();rows[-1]['body']+='00'
    with pytest.raises(ValueError):wire_checks(rows)


def probe_fixture():
    current={'actor':{'guid':1},'runtime':{'client':{'pid':12,'start_ticks':'34'}}}
    old={**copy.deepcopy(current),'completed':True,'failure':None,'finished_at':9,
        'original_social':[[1,2,1,''],[2,1,1,'']],
        'bridge_native_restoration':{'checks':{'native':True}},'friend_restoration':{'checks':{'social':True}},
        'ignore_tabs':[{'controls':[]}],
        'ignore_dialogs':[{'controls':[{'name':name,'kind':kind,'text':text,'context':CONTEXT,'enabled':True}
            for name,kind,text in [('StaticPopup1Button1','Button','Accept'),
                ('StaticPopup1Button2','Button','Cancel'),('StaticPopup1EditBox','EditBox','')]]}]}
    return old,current


def test_completed_owned_empty_ignore_probe_is_admissible():
    old,current=probe_fixture();assert source_matches(old,current)


@pytest.mark.parametrize('change',['failed','open','actor','lifetime','social','prompt','restoration','nonempty'])
def test_another_or_unrestored_probe_cannot_authorize_ignore_input(change):
    old,current=probe_fixture()
    if change=='failed':old['completed']=False;old['failure']='failed'
    elif change=='open':old['finished_at']=None
    elif change=='actor':old['actor']={'guid':2}
    elif change=='lifetime':old['runtime']['client']['start_ticks']='35'
    elif change=='social':old['original_social'][0][2]=3
    elif change=='prompt':old['ignore_dialogs'][0]['controls'][0]['context']='another prompt'
    elif change=='restoration':old['friend_restoration']['checks']['social']=False
    elif change=='nonempty':old['ignore_tabs'][0]['controls']=[{
        'name':'FriendsFrameIgnoreButton2','text':'Other','kind':'Button'}]
    assert not source_matches(old,current)
