"""Collect requests preserve 64-bit money and native attachment/gameplay checks."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_mail_actions import action,setup,run,read
from tools.client_compatibility.world.tests.test_mail_packets import GUID


@pytest.mark.parametrize('money',[0,12345,2**32,2**64-1])
def test_money_amount_is_not_truncated_and_native_can_validate_it(codec,money):
    row=run(codec,setup()+[action('mail_request','CMSG_MAIL_TAKE_MONEY',read()+struct.pack('<Q',money))])[-1]
    assert row==['CMSG_MAIL_TAKE_MONEY',struct.pack('<QIQ',GUID,4,money).hex()]


def test_native_verifies_attachment_membership_after_owned_mail_validation(codec):
    row=run(codec,setup()+[action('mail_request','CMSG_MAIL_TAKE_ITEM',read()+struct.pack('<Q',17))])[-1]
    assert row==['CMSG_MAIL_TAKE_ITEM',struct.pack('<QII',GUID,4,17).hex()]


@pytest.mark.parametrize('id',[0,2**32,2**64-1])
def test_attachment_guid_is_never_narrowed_to_another_native_item(codec,id):
    row=run(codec,setup()+[action('mail_request','CMSG_MAIL_TAKE_ITEM',read()+struct.pack('<Q',id))])[-1]
    assert 'error' in row


@pytest.mark.parametrize('name',['CMSG_MAIL_TAKE_ITEM','CMSG_MAIL_TAKE_MONEY'])
def test_collect_rejects_missing_fields_foreign_mail_and_closed_mailbox(codec,name):
    body=read()+struct.pack('<Q',17)
    malformed=[body[:i] for i in range(len(body))]+[body+b'x',read(5)+struct.pack('<Q',17)]
    rows=run(codec,setup()+[action('mail_request',name,b) for b in malformed])
    assert all('error' in row for row in rows[2:])
    close=action('bank_close','CMSG_CLOSE_INTERACTION',Writer().guid(*modern_guid(GUID,0)).finish())
    assert 'error' in run(codec,setup()+[close,action('mail_request',name,body)])[-1]
