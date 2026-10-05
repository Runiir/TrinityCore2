"""The live book oracle rejects mismatched native, public and rendered pages."""
import copy,struct
from tools.client_compatibility.interaction_item_text import wire_checks,page_checks,TITLE
from tools.client_compatibility.world.buffer import Writer

GUID=(0x4000<<48)|50
HIGH=(3<<58)|(1<<42)
SPEC={'pages':[{'id':18,'text':'Dear Sir,\n','next':19},{'id':19,'text':'Warm regards. é','next':0}]}


def packets():
    def row(name,direction,body):return dict(name=name,direction=direction,body=body.hex())
    w=Writer().pack('I',18).bits(1,1).pack('I',2)
    for page in SPEC['pages']:
        text=page['text'].encode()
        w.pack('IIiB',page['id'],page['next'],0,0).bits(len(text),12).raw(text)
    return [row('CMSG_READ_ITEM','to_native',b'\xff\x19'),
        row('SMSG_READ_ITEM_OK','from_native',struct.pack('<Q',GUID)),
        row('SMSG_READ_ITEM_RESULT_OK','to_client',Writer().guid(50,HIGH).finish()),
        row('CMSG_PAGE_TEXT_QUERY','to_native',struct.pack('<IQ',18,GUID)),
        *[row('SMSG_PAGE_TEXT_QUERY_RESPONSE','from_native',struct.pack('<I',p['id'])+
            p['text'].encode()+b'\0'+struct.pack('<I',p['next'])) for p in SPEC['pages']],
        row('SMSG_QUERY_PAGE_TEXT_RESPONSE','to_client',w.finish())]


def check(rows):return wire_checks(rows,{'guid':GUID},{'slot':3},SPEC)


def test_exact_owned_native_read_and_complete_chain_pass():
    assert all(check(packets()).values())
    rows=packets();rows[3]['body']=struct.pack('<IQ',18,0).hex()
    assert all(check(rows).values())


def test_missing_duplicate_wrong_actor_position_text_or_flags_do_not_pass():
    for index in range(7):
        rows=packets();rows.pop(index)
        assert not all(check(rows).values())
    for index in (0,1,2,3,4,6):
        rows=packets();rows.append(rows[index])
        assert not all(check(rows).values())
    variants=[(0,b'\xff\x18'),(1,struct.pack('<Q',GUID+1)),
        (2,Writer().guid(51,HIGH).finish()),(3,struct.pack('<IQ',19,GUID)),
        (4,struct.pack('<I',18)+b'Wrong text\0'+struct.pack('<I',19))]
    for index,body in variants:
        rows=packets();rows[index]['body']=body.hex()
        assert not all(check(rows).values())


def test_public_page_requires_exact_text_and_stock_navigation_state():
    probe={'visible':True,'contents_visible':True,'title':TITLE,'item':TITLE,'page':1,
        'text':SPEC['pages'][0]['text'],'text_length':len(SPEC['pages'][0]['text'].encode()),
        'text_truncated':False,'has_next':True,'next_visible':True,'previous_visible':False}
    assert all(page_checks(probe,SPEC['pages'][0],1).values())
    for key,value in [('visible',False),('contents_visible',False),('title','Wrong letter'),('item','Wrong letter'),
        ('page',2),('text','Wrong text'),('text_length',0),('text_truncated',True),
        ('has_next',False),('next_visible',False),('previous_visible',True)]:
        changed=copy.deepcopy(probe);changed[key]=value
        assert not all(page_checks(changed,SPEC['pages'][0],1).values())
