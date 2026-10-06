"""Independent pinned60895 reader for attributable owned-pet cast delivery."""
from .buffer import Reader


def decode(name,body):
    if name not in ('SMSG_SPELL_START','SMSG_SPELL_GO'):
        raise ValueError('not a pet start/completion packet')
    r=Reader(body)
    caster,unit,cast,original=[r.guid() for _ in range(4)]
    spell,visual,flags,extra,duration=r.unpack('iIIII')
    trajectory=r.unpack('IfBii');prediction=r.unpack('iB');beacon=r.guid()
    hits,misses,status,powers=[r.bits(n) for n in (16,16,16,9)]
    runes,points,optional=r.bits(1),r.bits(16),r.bits(2);r.align()
    target_flags=r.bits(28);source,dest=r.bits(1),r.bits(1)
    target_extra,name_len=r.bits(2),r.bits(7)
    target,item=r.guid(),r.guid()
    if (original!=(0,0) or trajectory!=(0,0.0,0,0,0) or prediction!=(0,0) or beacon!=(0,0) or
        misses or status or powers not in (0,1) or runes or points or optional or
        source or dest or target_extra or name_len or item!=(0,0) or hits>8):
        raise ValueError('unsupported owned-pet cast extensions')
    hit_targets=[r.guid() for _ in range(hits)]
    remaining=[r.unpack('bi') for _ in range(powers)]
    if name=='SMSG_SPELL_GO' and r.bits(1):raise ValueError('unexpected pet completion log attachment')
    r.end()
    return {'caster':caster,'unit':unit,'cast':cast,'spell':spell,'visual':visual,'flags':flags,
        'extra':extra,'duration':duration,'target_flags':target_flags,'target':target,
        'hits':hit_targets,'remaining':remaining}
