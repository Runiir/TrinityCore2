"""Owned gossip text queries: native probabilities and public broadcast IDs."""
from functools import lru_cache
from .buffer import Reader,Writer
from . import units
from .gossip import text


@lru_cache(maxsize=128)
def broadcasts(entry):
    from .. import lab_runtime as lab
    columns=','.join(f'BroadcastTextID{i}' for i in range(8))
    with lab.connection() as db,db.cursor() as cur:
        cur.execute(f'SELECT {columns} FROM client442_world.npc_text WHERE ID=%s',(entry,))
        return cur.fetchone()


def request(owner,body):
    r=Reader(body);entry,=r.unpack('I');guid=units.owned_native(owner,r);r.end()
    menu=getattr(owner,'gossip_menu',None)
    if not menu or (guid,entry)!=(menu['guid'],menu['text_id']):
        raise ValueError('NPC text query does not belong to the visible gossip menu')
    if not hasattr(owner,'npc_text_queries'):owner.npc_text_queries=set()
    owner.npc_text_queries.add(entry)
    return Writer().pack('IQ',entry,guid).finish()


def response(owner,body):
    r=Reader(body);entry,=r.unpack('I')
    if entry not in getattr(owner,'npc_text_queries',set()):return None
    owner.npc_text_queries.remove(entry);probabilities=[]
    for _ in range(8):
        probabilities.append(r.unpack('f')[0]);text(r);text(r);r.unpack('7I')
    r.end();ids=broadcasts(entry)
    if not ids:return Writer().pack('I',entry).bits(0,1).pack('I',0).finish()
    data=Writer().pack('8f8I',*probabilities,*ids).finish()
    return Writer().pack('I',entry).bits(1,1).pack('I',len(data)).raw(data).finish()
