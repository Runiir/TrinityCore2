"""Independent reader checks for the static cache and legacy objective identities."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def native(currencies=None,required_currencies=None):
    w=Writer().pack('7i',28766,2,1,1,9,0,1).pack('4i',0,0,0,0)
    w.pack('iIiI3if',0,1,350,0,0,0,0,0)
    w.pack('12I',0,0x80000,0,0,0,0,0,0,0,0,0,0)
    w.pack('8I',*([0]*8)).pack('12I',*([0]*12))
    w.pack('5I',72,0,0,0,0).pack('5i',5,0,0,0,0).pack('5I',*([0]*5))
    w.pack('IffI',0,.1,.2,0)
    for text in ['Beating Them Back!','Kill 6 Blackrock Battle Worgs.','Help my soldiers!','','Report back.']:
        w.raw(text.encode()+b'\0')
    w.pack('16I',49871,6,0,0,*([0]*12)).pack('12I',*([0]*12)).pack('I',0)
    for text in ['Blackrock Battle Worg','','','']:w.raw(text.encode()+b'\0')
    w.pack('8I',*(currencies or [0]*8)).pack('8I',*(required_currencies or [0]*8))
    for _ in range(4):w.raw(b'\0')
    return w.pack('2I',0,0).finish()


def call(codec,body):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},gameobjects=[],units=[],
        actions=[{'fn':'quest_response','name':'SMSG_QUEST_QUERY_RESPONSE','body':body.hex()}])[0]


def decode(body):
    r=Reader(body);id,=r.unpack('I');allow=r.bits(1);r.align()
    if not allow:r.end();return {'id':id,'allow':allow}
    header=r.unpack('12if');money=r.unpack('iif');display=r.unpack('i3i');spells=r.unpack('iif');artifact=r.unpack('ifi');flags=r.unpack('i3I')
    items=[r.unpack('4i') for _ in range(4)];choices=[r.unpack('3i') for _ in range(6)]
    poi=r.unpack('iffi');reward=r.unpack('8i');factions=[r.unpack('4i') for _ in range(5)]
    faction_flags,=r.unpack('I');currency=r.unpack('8i');tail=r.unpack('3iqIQ6i')
    lengths=[r.bits(n) for n in [9,12,12,9,10,8,10,8,11]];translated=r.bits(1);r.align()
    objectives=[]
    for _ in range(tail[4]):
        obj=r.unpack('IibiiIIfi');length=r.bits(8);r.align();text=r.raw(length).decode();objectives.append((obj,text))
    texts=[r.raw(n).decode() for n in lengths];r.end();return locals()


def test_native_kill_objective_static_cache_preserves_numbers_text_and_flags(codec):
    name,body=call(codec,native());assert name=='SMSG_QUERY_QUEST_INFO_RESPONSE';d=decode(bytes.fromhex(body))
    assert d['id']==28766 and d['allow']==1
    assert d['header']==(28766,2,1,0,0,0,1,9,0,1,0,1,1.)
    assert d['money']==(350,0,1.) and d['flags']==(0,0x80000,0,0)
    assert d['factions'][0]==(72,5,0,0)
    assert d['tail'][4:]==(1,2**64-1,0,0,0,0,0,0)
    assert d['objectives']==[((28766*32+1,0,0,49871,6,0,0,0.,0),'Blackrock Battle Worg')]
    assert d['texts'][:3]==['Beating Them Back!','Kill 6 Blackrock Battle Worgs.','Help my soldiers!']


def test_native_missing_quest_reply_is_explicitly_disallowed(codec):
    name,body=call(codec,struct.pack('<I',0x80000000|28766))
    assert name=='SMSG_QUERY_QUEST_INFO_RESPONSE' and decode(bytes.fromhex(body))=={'id':28766,'allow':0}


def test_quest_currency_rewards_and_objectives_use_active_ids_without_changing_amounts(codec):
    # Every ID occupies an even slot; quantities can equal old IDs and must
    # remain quantities. Ordinary Justice and Conquest retain their identities.
    name,body=call(codec,native([392,392,395,27,390,11,0,0],[392,137,395,392,0,0,0,0]))
    assert name=='SMSG_QUERY_QUEST_INFO_RESPONSE'
    decoded=decode(bytes.fromhex(body))
    assert decoded['currency']==(1901,392,395,27,390,11,0,0)
    assert decoded['objectives'][1:]==[
        ((28766*32+11,4,-1,1901,137,0,0,0.,0),''),
        ((28766*32+12,4,-1,395,392,0,0,0.,0),'')]


def test_query_rejects_every_cut_and_trailing_bytes(codec):
    body=native()
    for n in range(len(body)):assert 'error' in call(codec,body[:n])
    assert 'error' in call(codec,body+b'x')
