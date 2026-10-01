"""Ordinary visible-NPC gossip; native menu indices remain authoritative."""
from .buffer import Reader,Writer
from . import units,gameobjects

CLIENT_NAMES={'CMSG_TALK_TO_GOSSIP','CMSG_GOSSIP_SELECT_OPTION'}


def text(reader):
    end=reader.data.find(b'\0',reader.pos)
    if end<0 or end-reader.pos>4096:raise ValueError('invalid native gossip string')
    return reader.raw(end-reader.pos+1)[:-1]


def request(owner,name,body):
    r=Reader(body);guid=units.owned_native(owner,r)
    if name=='CMSG_TALK_TO_GOSSIP':
        r.end();return 'CMSG_GOSSIP_HELLO',Writer().pack('Q',guid).finish()
    menu,index=r.unpack('Ii');size=r.bits(8);promo=r.raw(size);r.end()
    state=getattr(owner,'gossip_menu',None)
    if not state or (guid,menu)!=(state['guid'],state['menu']) or index not in state['options']:
        raise ValueError('gossip choice does not belong to native menu')
    return 'CMSG_GOSSIP_SELECT_OPTION',Writer().pack('QII',guid,menu,index).raw(promo+b'\0').finish()


def response(owner,name,body):
    if name=='SMSG_GOSSIP_COMPLETE':
        Reader(body).end();owner.gossip_menu=None
        return name,Writer().bits(0,1).finish()
    if name!='SMSG_GOSSIP_MESSAGE':return None
    r=Reader(body);guid,menu,text_id,count=r.unpack('QIII')
    record=getattr(owner,'visible_units',{}).get(guid)
    if not record:return None
    if count>64:raise ValueError('native gossip option count exceeds bound')
    options=[]
    for _ in range(count):
        index,icon,flags,cost=r.unpack('iBBI')
        options.append((index,icon,flags,cost,text(r),text(r)))
    quests_count,=r.unpack('I')
    if quests_count>64:raise ValueError('native gossip quest count exceeds bound')
    quests=[]
    for _ in range(quests_count):quests.append((*r.unpack('iiiiB'),text(r)))
    r.end()
    owner.gossip_menu={'guid':guid,'menu':menu,'options':{row[0] for row in options}}
    w=Writer().guid(*gameobjects.modern_guid(guid,record['map'])).pack('5i',menu,0,0,count,quests_count).bits(bool(text_id),1).bits(0,1)
    for index,icon,flags,cost,title,confirm in options:
        w.pack('iBB4i',index,icon,flags,cost,0,0,index)
        w.bits(len(title),12).bits(len(confirm),12).bits(0,2).bits(0,2).bits(1,8).pack('I',0).raw(title).raw(confirm)
    if text_id:w.pack('I',text_id)
    for quest,kind,level,flags,repeat,title in quests:
        w.pack('9i',quest,0,kind,level,level,0,flags,0,0)
        w.bits(bool(repeat),1).bits(0,3).bits(len(title),9).raw(title)
    return name,w.finish()
