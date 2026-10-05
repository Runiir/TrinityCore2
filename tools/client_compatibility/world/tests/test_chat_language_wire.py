import pytest
from tools.client_compatibility.interaction_chat_language import request,response
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,stateful,action


@pytest.mark.parametrize('language',[6,7])
def test_stock_language_survives_native_request_and_self_echo(codec,language):
    text=b'TC442UI:language_wire'
    modern=Writer().pack('i',language).bits(len(text),11).bits(1,1).raw(text).finish()
    name,body=stateful(codec,{'guid':1,'map':0},[
        action('chat_request','CMSG_CHAT_MESSAGE_SAY',modern)])[0]
    assert name=='CMSG_MESSAGECHAT_SAY'
    assert request(modern.hex(),True)==request(body,False)==(language,text.decode())
    native=Writer().pack('BiQIQI',1,language,1,0,0,len(text)+1).raw(text+b'\0').pack('B',0).finish()
    name,body=stateful(codec,{'guid':1,'map':0},[
        action('chat_response','SMSG_MESSAGECHAT',native)])[0]
    assert name=='SMSG_CHAT'
    assert response(native.hex(),False)==response(body,True)==(1,language,1,text.decode())
    with pytest.raises(ValueError):request(modern.hex()+'00',True)
    with pytest.raises(ValueError):response(body+'00',True)
