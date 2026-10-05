"""The social oracle rejects mismatched requests, GUIDs and native outcomes."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friends import wire_checks,HIGH
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
