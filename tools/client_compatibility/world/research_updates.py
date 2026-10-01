"""Refresh addon-visible digsites and projects when native archaeology changes."""
from .buffer import Writer,player_high
from .native_objects import records
from .objects import INDEX,field_values
from .gameobjects import packet


def complete_mask(writer,size):
    if size>32:raise ValueError('research array exceeds native bound')
    writer.bits(size,32)
    if size:writer.bits((1<<size)-1,size)


def block(guid,sites=None,projects=None):
    mask=0
    if sites is not None:mask|=(1<<23)|(1<<24)
    if projects is not None:mask|=(1<<27)|(1<<28)
    fields=Writer().pack('BBBI',1,0,3,1<<7)
    fields.pack('I',1).bits(0,14).bits(mask,32)
    if sites is not None:complete_mask(fields,len(sites))
    if projects is not None:complete_mask(fields,len(projects))
    if sites is not None:fields.pack('H'*len(sites),*sites)
    if projects is not None:fields.pack('h'*len(projects),*projects)
    fields.flush();data=fields.finish()
    return Writer().pack('B',0).guid(guid,player_high()).pack('I',len(data)).raw(data).finish()


def updates(owner,body):
    if not hasattr(owner,'self_snapshot'):return None
    blocks=[]
    for record in records(body):
        if record['update_type']!=0 or record['guid']!=owner.character['guid']:continue
        changed=record['fields'];owner.self_snapshot['fields'].update(changed)
        active=field_values(owner.self_snapshot,owner.character)['ActivePlayerData']
        sites=active['ResearchSites'][0] if any(INDEX['PLAYER_FIELD_RESEARCH_SITE_1']+i in changed for i in range(8)) else None
        projects=[r['ResearchProjectID'] for r in active['Research'][0]] if any(INDEX['PLAYER_FIELD_RESEARCH_PROJECT_1']+i in changed for i in range(8)) else None
        if sites is not None or projects is not None:blocks.append(block(owner.character['guid'],sites,projects))
    return packet(owner.character['map'],blocks) if blocks else None
