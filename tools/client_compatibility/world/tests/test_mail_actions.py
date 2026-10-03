"""Mail mutations require catalog ownership and preserve native command failures."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_mail_packets import GUID,GO,catalog,entry,parse_entry


def action(fn,name,body):return {'fn':fn,'name':name,'body':body.hex()}


def setup():
    return [action('mail_request','CMSG_MAIL_GET_LIST',Writer().guid(*modern_guid(GUID,0)).finish()),
            action('mail_response','SMSG_MAIL_LIST_RESULT',catalog([entry(attachments=[])]))]


def run(codec,actions):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
                  gameobjects=[GO],units=[],actions=actions)


def read(id=4):return Writer().guid(*modern_guid(GUID,0)).pack('Q',id).finish()


def delete(id=4,reason=0):return struct.pack('<Qi',id,reason)


def test_read_and_delete_use_native_mailbox_and_owned_32_bit_ids(codec):
    replies=run(codec,setup()+[action('mail_request','CMSG_MAIL_MARK_AS_READ',read()),
                              action('mail_request','CMSG_MAIL_DELETE',delete(reason=-1))])
    assert replies[2]==['CMSG_MAIL_MARK_AS_READ',struct.pack('<QI',GUID,4).hex()]
    assert replies[3]==['CMSG_MAIL_DELETE',struct.pack('<QIi',GUID,4,-1).hex()]


@pytest.mark.parametrize('id',[0,5,2**32,2**64-1])
def test_foreign_and_truncated_mail_ids_are_rejected(codec,id):
    replies=run(codec,setup()+[action('mail_request','CMSG_MAIL_MARK_AS_READ',read(id)),
                              action('mail_request','CMSG_MAIL_DELETE',delete(id))])
    assert all('error' in reply for reply in replies[2:])


def test_catalog_must_follow_mailbox_request_and_survive_full_validation(codec):
    assert 'error' in run(codec,[action('mail_request','CMSG_MAIL_DELETE',delete())])[0]
    rows=run(codec,[setup()[1],action('mail_request','CMSG_MAIL_DELETE',delete())])
    assert 'error' in rows[1]
    malformed=catalog([entry(id=5,attachments=[])])+b'x'
    rows=run(codec,setup()+[action('mail_response','SMSG_MAIL_LIST_RESULT',malformed),
                           action('mail_request','CMSG_MAIL_DELETE',delete(5)),
                           action('mail_request','CMSG_MAIL_DELETE',delete(4))])
    assert 'error' in rows[2] and 'error' in rows[3] and rows[4][0]=='CMSG_MAIL_DELETE'


def test_closing_or_logging_out_revokes_mailbox_mutation_access(codec):
    for closure in [action('bank_close','CMSG_CLOSE_INTERACTION',Writer().guid(*modern_guid(GUID,0)).finish()),
                    action('logout_complete','',b'')]:
        rows=run(codec,setup()+[closure,action('mail_request','CMSG_MAIL_DELETE',delete())])
        assert 'error' in rows[-1]


def test_mail_request_requires_complete_body(codec):
    for name,body in [('CMSG_MAIL_MARK_AS_READ',read()),('CMSG_MAIL_DELETE',delete())]:
        malformed=[body[:i] for i in range(len(body))]+[body+b'x']
        rows=run(codec,setup()+[action('mail_request',name,body) for body in malformed])
        assert all('error' in row for row in rows[2:])


@pytest.mark.parametrize('command,error,tail,expected',[
    (4,0,b'',(4,4,0,0,0,0)),(4,6,b'',(4,4,6,0,0,0)),
    (0,3,b'',(4,0,3,0,0,0)),(2,0,struct.pack('<II',17,5),(4,2,0,0,17,5)),
    (2,1,struct.pack('<I',50),(4,2,1,51,0,0)),(0,19,b'',(4,0,19,0,0,0))])
def test_native_command_result_variants_and_inventory_errors(codec,command,error,tail,expected):
    response=run(codec,[action('mail_response','SMSG_SEND_MAIL_RESULT',struct.pack('<III',4,command,error)+tail)])[0]
    assert response[0]=='SMSG_MAIL_COMMAND_RESULT'
    r=Reader(bytes.fromhex(response[1]));assert r.unpack('QiiiQi')==expected;r.end()


def test_only_successful_deletion_removes_catalog_identity(codec):
    for error in [0,6]:
        rows=run(codec,setup()+[action('mail_response','SMSG_SEND_MAIL_RESULT',struct.pack('<III',4,4,error)),
                               action('mail_request','CMSG_MAIL_DELETE',delete())])
        assert ('error' in rows[-1])==(error==0)


def test_native_mail_result_rejects_unknown_and_malformed_variants(codec):
    valid=struct.pack('<III',4,4,0)
    malformed=[valid[:i] for i in range(len(valid))]+[valid+b'x',struct.pack('<III',4,6,0),
        struct.pack('<III',4,4,7),struct.pack('<IIII',4,4,1,999),
        struct.pack('<IIIII',4,2,0,17,2**31)]
    rows=run(codec,[action('mail_response','SMSG_SEND_MAIL_RESULT',body) for body in malformed])
    assert all('error' in row for row in rows)


def test_console_sender_zero_is_an_empty_modern_guid(codec):
    row=run(codec,[action('mail_response','SMSG_MAIL_LIST_RESULT',catalog([entry(sender=0,attachments=[])]))])[0]
    r=Reader(bytes.fromhex(row[1]));r.unpack('Ii');assert parse_entry(r)['sender']==(0,0);r.end()
