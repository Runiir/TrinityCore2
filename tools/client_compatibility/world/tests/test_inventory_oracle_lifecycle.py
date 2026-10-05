import json
from tools.client_compatibility.observation.inventory import Inventory
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX


def packet(guid,fields,creation=False):
    raw=guid.to_bytes(8,'little');mask=sum(bool(x)<<i for i,x in enumerate(raw))
    w=Writer().pack('HI',0,1).pack('BB',1 if creation else 0,mask).raw(bytes(x for x in raw if x))
    if creation:w.pack('B',4 if guid==1 else 1).bits(4,8).bits(0,24).bits(0,6).flush()
    masks=[0]*(max(fields)//32+1)
    for index in fields:masks[index//32]|=1<<(index%32)
    return w.pack('B',len(masks)).pack('I'*len(masks),*masks).pack('I'*len(fields),
        *(fields[index] for index in sorted(fields))).finish().hex()


def append(path,body):
    with path.open('a') as f:f.write(json.dumps({'session':'same-owned-realm','direction':'from_native',
        'name':'SMSG_UPDATE_OBJECT','body':body})+'\n')


def test_self_recreation_clears_omitted_zero_fields_but_sparse_updates_merge(tmp_path):
    path=tmp_path/'evidence/world_packets.jsonl';path.parent.mkdir()
    rank=INDEX['PLAYER_SKILL_RANK_0'];money=INDEX['PLAYER_FIELD_COINAGE']
    append(path,packet(1,{rank:1,money:100},True))
    oracle=Inventory(tmp_path,'same-owned-realm',1).poll()
    append(path,packet(1,{money:200}));oracle.poll()
    assert oracle.money()==200 and oracle.objects[1][rank]==1
    append(path,packet(1,{money:200},True));oracle.poll()
    assert oracle.money()==200 and oracle.objects[1].get(rank,0)==0


def test_recreated_owned_item_replaces_prior_identity_fields(tmp_path):
    path=tmp_path/'evidence/world_packets.jsonl';path.parent.mkdir()
    guid=(0x4000<<48)|10;entry=INDEX['OBJECT_FIELD_ENTRY'];count=INDEX['ITEM_FIELD_STACK_COUNT']
    append(path,packet(guid,{entry:49778,count:5},True))
    oracle=Inventory(tmp_path,'same-owned-realm',1).poll()
    append(path,packet(guid,{count:4}));oracle.poll()
    assert oracle.item(guid)=={'guid':guid,'id':49778,'count':4}
    append(path,packet(guid,{entry:49778},True));oracle.poll()
    assert oracle.item(guid)=={'guid':guid,'id':49778,'count':0}
