"""Visible-creature templates translated from the owned native query reply."""
from .buffer import Reader,Writer
from .gossip import text


def request(owner,body):
    r=Reader(body);entry,=r.unpack('I');r.end()
    record=next((v for k,v in getattr(owner,'visible_units',{}).items() if k>>32&0xFFFFF==entry),None)
    if not record:raise ValueError('creature template is not visible to the native session')
    if not hasattr(owner,'creature_queries'):owner.creature_queries=set()
    owner.creature_queries.add(entry)
    return Writer().pack('IQ',entry,record['guid']).finish()


def response(owner,body):
    r=Reader(body);marker,=r.unpack('I');entry=marker&0x7FFFFFFF;allow=not(marker&0x80000000)
    pending=getattr(owner,'creature_queries',set())
    if entry not in pending:return None
    pending.remove(entry);w=Writer().pack('I',entry).bits(allow,1).flush()
    if not allow:r.end();return w.finish()
    names=[text(r) for _ in range(4)];alternate=[text(r) for _ in range(4)]
    title,cursor=text(r),text(r)
    flags=r.unpack('2I');kind,family,rank=r.unpack('3i');credits=r.unpack('2I')
    displays=[v for v in r.unpack('4I') if v];hp,mana,leader=r.unpack('ffB')
    quest_items=[v for v in r.unpack('6I') if v];move,expansion=r.unpack('II');r.end()
    w.bits(len(title)+1,11).bits(1,11).bits(len(cursor)+1,6).bits(0,1).bits(bool(leader),1)
    for name,alt in zip(names,alternate):w.bits(len(name)+1,11).bits(len(alt)+1,11)
    w.flush()
    for name,alt in zip(names,alternate):
        if name:w.raw(name+b'\0')
        if alt:w.raw(alt+b'\0')
    w.pack('2I3iI2II f'.replace(' ',''),*flags,kind,family,rank,0,*credits,len(displays),float(len(displays)))
    for display in displays:w.pack('Iff',display,1,1)
    w.pack('ff2I8i',hp,mana,len(quest_items),0,move,expansion,expansion,0,0,0,0,0)
    if title:w.raw(title+b'\0')
    if cursor:w.raw(cursor+b'\0')
    w.pack('I'*len(quest_items),*quest_items)
    return w.finish()
