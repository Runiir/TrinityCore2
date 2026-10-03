"""Pinned five-byte currency requests and installed active Honor identity."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,stateful,action


@pytest.mark.parametrize('modern,native',[(395,395),(390,390),(1901,392),(384,384)])
@pytest.mark.parametrize('flags',[0,4,8,12])
def test_currency_flags_have_native_order_width_and_active_id(codec,modern,native,flags):
    # MiscPackets.cpp at 6426c2bd reads modern ID/u8 flags; native reads flags/ID u32.
    assert stateful(codec,dict(guid=1),[action('currency_request','CMSG_SET_CURRENCY_FLAGS',
        struct.pack('<IB',modern,flags))])==[['CMSG_SET_CURRENCY_FLAGS',struct.pack('<II',flags,native).hex()]]


@pytest.mark.parametrize('body',[b'',b'\0'*4,b'\0'*6,struct.pack('<IB',0,4),
    struct.pack('<IB',392,4),struct.pack('<IB',65536,4),struct.pack('<IB',1901,16)])
def test_currency_requests_reject_truncation_deprecated_ids_and_new_flags(codec,body):
    result=stateful(codec,dict(guid=1),[action('currency_request','CMSG_SET_CURRENCY_FLAGS',body)])
    assert 'error' in result[0]


def test_currency_setup_and_gain_preserve_amount_but_use_active_honor(codec):
    # Source-pinned installed CurrencyTypes A0DA38E0: Honor is 1901, not 392.
    setup=Writer().bits(1,23).bits(0,1).bits(12,4).bits(0,1).bits(0,1).pack('II',137,392).finish()
    gain=Writer().bits(0,1).bits(0,1).bits(0,1).pack('ii',138,392).finish()
    assert stateful(codec,dict(guid=1),[action('currency','SMSG_SETUP_CURRENCY',setup),
        action('currency','SMSG_SET_CURRENCY',gain)])==[
        ['SMSG_SETUP_CURRENCY',(struct.pack('<Iii',1,1901,137)+b'\x00\xc0').hex()],
        ['SMSG_SET_CURRENCY',(struct.pack('<iiII',1901,138,0,0)+b'\x00\x00').hex()]]
