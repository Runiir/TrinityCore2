"""Legacy guild events need authoritative IDs absent from their name-only body."""
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action


def call(codec,event,names,identities=None):
    if identities is None:
        identities=[{'guid':1,'name':'Harnessone'},{'guid':258,'name':'Harnesstwo'},
                    {'rank_id':3,'rank_name':'Member'}]
    body=Writer().pack('BB',event,len(names))
    for text in names:body.raw(text.encode()+b'\0')
    return result(codec,op='stateful',character={'guid':1},snapshot=None,last_logout_guid=0,
        gameobjects=[],units=[],identities=identities,
        actions=[action('guild_response','SMSG_GUILD_EVENT',body.pack('Q',0).finish())])[0]


def test_promotion_and_demotion_keep_officer_target_rank_and_direction(codec):
    for event in [1,2]:
        name,body=call(codec,event,['Harnessone','Harnesstwo','Member'])
        r=Reader(bytes.fromhex(body))
        assert name=='SMSG_GUILD_SEND_RANK_CHANGE'
        assert r.guid()==(1,player_high()) and r.guid()==(258,player_high())
        assert r.unpack('I')==(3,) and r.bits(1)==(event==1);r.align();r.end()


def test_removal_keeps_both_identities_names_and_removed_flag(codec):
    name,body=call(codec,6,['Harnesstwo','Harnessone']);r=Reader(bytes.fromhex(body))
    assert name=='SMSG_GUILD_EVENT_PLAYER_LEFT' and r.bits(1)==1
    leaver,remover=r.bits(6),r.bits(6);r.align()
    assert r.guid()==(1,player_high()) and r.unpack('I')==(1,) and r.raw(remover)==b'Harnessone'
    assert r.guid()==(258,player_high()) and r.unpack('I')==(1,) and r.raw(leaver)==b'Harnesstwo';r.end()


def test_rank_event_rejects_missing_or_ambiguous_native_identities(codec):
    names=['Harnessone','Harnesstwo','Member']
    assert 'error' in call(codec,1,names,[])
    duplicate=[{'guid':1,'name':'Harnessone'},{'guid':258,'name':'Harnesstwo'},
               {'rank_id':3,'rank_name':'Member'},{'rank_id':2,'rank_name':'Member'}]
    assert 'error' in call(codec,1,names,duplicate)
    assert 'error' in call(codec,1,names[:2])
    assert 'error' in call(codec,6,['Harnesstwo'])
