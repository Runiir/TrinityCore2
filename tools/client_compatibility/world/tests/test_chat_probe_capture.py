import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,stateful,action

LINK=b'|cffffffff|Hitem:49778::::::::85:::::::::|h[Worn Greatsword]|h|r'


def request(text=LINK,language=7):
    return Writer().pack('i',language).bits(len(text),11).bits(1,1).raw(text).finish()


def response(text=LINK,sender=1,kind=1,language=7):
    return Writer().pack('BiQIQI',kind,language,sender,0,0,len(text)+1).raw(text+b'\0').pack('B',0).finish()


def captured(codec,name,body):
    return result(codec,op='public_chat_probe',name=name,body=body.hex())


def translated(codec,fn,name,body):
    return stateful(codec,{'guid':1,'map':1418},[action(fn,name,body)])[0]


def test_exact_stock_owned_say_link_is_captured_in_all_four_wire_directions(codec):
    modern=request();native=response()
    assert captured(codec,'CMSG_CHAT_MESSAGE_SAY',modern)
    assert captured(codec,'SMSG_MESSAGECHAT',native)
    name,body=translated(codec,'chat_request','CMSG_CHAT_MESSAGE_SAY',modern)
    assert captured(codec,name,bytes.fromhex(body))
    name,body=translated(codec,'chat_response','SMSG_MESSAGECHAT',native)
    assert captured(codec,name,bytes.fromhex(body))


@pytest.mark.parametrize('text',[b'private '+LINK,LINK+b' private',LINK.replace(b'49778',b'78478'),
    LINK.replace(b'Worn Greatsword',b'private name'),LINK.replace(b'item:',b'spell:'),LINK[:-1]])
def test_arbitrary_or_foreign_link_text_is_never_captured(codec,text):
    for name,body,fn in [('CMSG_CHAT_MESSAGE_SAY',request(text),'chat_request'),
                         ('SMSG_MESSAGECHAT',response(text),'chat_response')]:
        assert not captured(codec,name,body)
        translated_name,encoded=translated(codec,fn,name,body)
        assert not captured(codec,translated_name,bytes.fromhex(encoded))


def test_foreign_sender_other_chat_type_language_or_trailing_data_is_excluded(codec):
    assert not captured(codec,'CMSG_CHAT_MESSAGE_WHISPER',request())
    assert not captured(codec,'CMSG_CHAT_MESSAGE_SAY',request(language=0))
    for change in [{'sender':2},{'kind':3},{'language':0}]:
        assert not captured(codec,'SMSG_MESSAGECHAT',response(**change))
    for name,body in [('CMSG_CHAT_MESSAGE_SAY',request()),('SMSG_MESSAGECHAT',response())]:
        assert not captured(codec,name,body+b'private')
        assert not captured(codec,name,body[:-1])


def test_existing_public_markers_keep_their_exact_message_boundary(codec):
    marker=b'TC442UI:capture_01'
    assert captured(codec,'CMSG_CHAT_MESSAGE_SAY',request(marker))
    assert captured(codec,'SMSG_MESSAGECHAT',response(marker))
    assert not captured(codec,'CMSG_CHAT_MESSAGE_SAY',request(marker+b' private'))
    assert not captured(codec,'SMSG_MESSAGECHAT',response(marker+b' private'))
