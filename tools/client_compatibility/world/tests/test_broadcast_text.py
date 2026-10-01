from unittest.mock import patch
from tools.client_compatibility.world import bootstrap,broadcast_text
from tools.client_compatibility.world.buffer import Reader,Writer


def test_public_broadcast_hotfix_reply_and_missing_record():
    class Session:
        def __init__(self):self.sent=[]
        def send(self,name,body):self.sent.append((name,body))
    session=Session()
    query=Writer().pack('I',broadcast_text.TABLE_HASH).bits(2,13).pack('2I',10753,999999).finish()
    with patch.object(broadcast_text,'record',side_effect=[b'Greeting\0',None]):
        bootstrap.query(session,query)
    for (_,body),entry,status,data in zip(session.sent,[10753,999999],[1,3],[b'Greeting\0',b'']):
        reader=Reader(body)
        table,ident,timestamp=reader.unpack('III')
        assert (table,ident)==(broadcast_text.TABLE_HASH,entry)
        assert timestamp>0 and reader.bits(3)==status
        assert reader.raw(reader.unpack('I')[0])==data
        reader.end()
