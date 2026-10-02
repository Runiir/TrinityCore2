"""Actual native quest details and independent modern reader checks."""
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

BODY=bytes.fromhex(
    '57040000c50030f100000000000000005e70000042656174696e67205468656d204261636b2100536f20796f75277265'
    '20746865206e657720726563727569742066726f6d2053746f726d77696e642c2065683f2049276d204d61727368616c'
    '204d6342726964652c20636f6d6d616e646572206f662074686973206761727269736f6e2e20476c616420746f206861'
    '766520796f75206f6e20626f6172642e2e2e244224423c4d634272696465206c6f6f6b73207468726f75676820736f6d'
    '65207061706572732e3e24422442244e2e20497420697320244e2c2072696768743f24422442596f7527766520617272'
    '69766564206a75737420696e2074696d652e2054686520426c61636b726f636b206f7263732068617665206d616e6167'
    '656420746f20736e65616b20696e746f204e6f7274687368697265207468726f756768206120627265616b20696e2074'
    '6865206d6f756e7461696e2e204d7920736f6c64696572732061726520646f696e672074686520626573742074686174'
    '20746865792063616e20746f2070757368207468656d206261636b2c206275742049206665617220746865792077696c'
    '6c206265206f7665727768656c6d656420736f6f6e2e2442244248656164206e6f7274687765737420696e746f207468'
    '6520666f7265737420616e64206b696c6c207468652061747461636b696e6720426c61636b726f636b20776f72677321'
    '2048656c70206d7920736f6c646965727321004b696c6c203620426c61636b726f636b20426174746c6520576f726773'
    '2e0054686973206973206120426c61636b726f636b20426174746c6520576f72672e00426c61636b726f636b20426174'
    '746c6520576f726700000000000000000000000100000800000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000a7df00000000000000000000000000000100000000000000000000000000'
    '0000892001000000000000000000000000005e0100003200000000000000000000000000000000000000000000000000'
    '000048000000000000000000000000000000000000000500000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000004000000060000000000000002000000000000000100000000000000050000000000'
    '0000'
)
NPC=int.from_bytes(BODY[:8],'little')
UNIT={'guid':NPC,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):3}}


def call(codec,body=BODY,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},gameobjects=[],
        units=[UNIT] if units is None else units,actions=[{'fn':'quest_response','name':'SMSG_QUEST_GIVER_QUEST_DETAILS','body':body.hex()}])[0]


def decode(body):
    r=Reader(body);npc=r.guid();inform=r.guid();header=r.unpack('18I')
    assert header[10]==0 and header[12]==0 and header[17]==0
    emotes=[r.unpack('2I') for _ in range(header[11])]
    lengths=[r.bits(n) for n in [9,12,12,10,8,10,8]];flags=[r.bits(1) for _ in range(6)];r.align()
    items=[r.unpack('2i') for _ in range(4)];currencies=[r.unpack('3i') for _ in range(4)]
    counts=r.unpack('4iQi3i');factions=[r.unpack('4i') for _ in range(5)];spells=r.unpack('7i')
    choices=[]
    for _ in range(6):
        type_=r.bits(2);r.align();item=r.unpack('i2I');bonus=r.bits(1);r.align();modifiers=r.bits(6);r.align();quantity=r.unpack('i')[0]
        choices.append((type_,item,bonus,modifiers,quantity))
    boost=r.bits(1);r.align();texts=[r.raw(n).decode() for n in lengths];r.end()
    return locals()


def test_actual_warrior_quest_details_preserve_identity_text_and_rewards(codec):
    reply=call(codec);assert reply[0]=='SMSG_QUEST_GIVER_QUEST_DETAILS';d=decode(bytes.fromhex(reply[1]))
    assert d['npc']==modern_guid(NPC,0) and d['inform']==(0,0)
    assert d['header'][0]==28766 and d['header'][16]==197 and d['header'][11]==4
    assert d['texts'][0]=='Beating Them Back!'
    assert 'Blackrock' in d['texts'][1] and d['texts'][2]=='Kill 6 Blackrock Battle Worgs.'
    assert d['counts'][0:4]==(0,0,350,50)
    assert d['items']==[(57255,1),(0,0),(0,0),(0,0)] and d['currencies']==[(0,0,0)]*4
    assert d['factions'][0]==(72,5,0,0)
    assert d['choices']==[(0,(0,0,0),0,0,0)]*6 and d['boost']==0
    assert d['spells']==(0,0,0,0,0,0,0)


def test_quest_details_reject_cuts_trailing_data_and_foreign_giver(codec):
    for n in range(len(BODY)):assert 'error' in call(codec,BODY[:n])
    assert 'error' in call(codec,BODY+b'x')
    assert call(codec,units=[]) is None
    assert call(codec,units=[{**UNIT,'kind':4}]) is None
