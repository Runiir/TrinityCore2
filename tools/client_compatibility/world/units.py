"""Render native-visible ordinary creatures, including flight masters."""
from .buffer import Writer,Reader
from .fields import serialize
from .objects import field_values
from .native_objects import records
from .gameobjects import modern_guid,packet


def block(snapshot,character):
    move=snapshot['movement'];identity=modern_guid(snapshot['guid'],snapshot['map'])
    w=Writer().pack('B',1).guid(*identity).pack('B',5)
    for i in range(19):w.bits(i in (0,4),1)
    from .movement import modern_flags2
    # Creation renders the native start position; ongoing ordinary ground
    # splines are translated separately by creature_movement.
    w.guid(*identity).pack('IIII4fffII',move['flags'],modern_flags2(move['flags2']),0,
        move['time'],*move['position'],move['pitch'],0,0,0).bits(0,8)
    w.pack('9fIf17f',*move['speeds'],0,1,2,65,1,3,10,100,90,140,180,360,90,270,30,80,2.75,7,.4).bits(0,1).pack('I',0)
    # PauseTimesCount is present for every create, even without a spline.
    fields=Writer().pack('B',0).raw(bytes([0,5,255,1]))
    values=field_values(snapshot,character)
    for kind in ['ObjectData','UnitData']:serialize(fields,kind,values[kind],visibility=0)
    data=fields.finish();return w.pack('I',len(data)).raw(data).finish()


def updates(owner,body):
    if not hasattr(owner,'visible_units'):owner.visible_units={}
    blocks=[];removed=[];map_id=owner.character['map']
    for r in records(body):
        map_id=r['map']
        if r['update_type']==3:
            for guid in r['removed']:
                if guid in owner.visible_units:removed.append(guid);del owner.visible_units[guid]
        elif r.get('kind')==3 and r['guid']>>52==0xF13:
            blocks.append(block(r,owner.character));owner.visible_units[r['guid']]=r
        elif r['update_type']==0 and r['guid'] in owner.visible_units:
            from .player_updates import scalar_block
            snapshot = owner.visible_units[r['guid']]
            snapshot['fields'].update(r['fields'])
            changed = scalar_block(snapshot, owner.character, r['fields'])
            if changed: blocks.append(changed)
    return packet(map_id,blocks,removed) if blocks or removed else None


def owned_native(owner,reader):
    identity=reader.guid()
    for guid,record in getattr(owner,'visible_units',{}).items():
        if identity==modern_guid(guid,record['map']):return guid
    raise ValueError('creature is not visible to the owned native session')
