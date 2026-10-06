"""Only own visible archaeology finds created during an own Survey window."""
import math
import struct
from . import runtime

FINDS={203071:'Night Elf Archaeology Find',203078:'Nerubian Archaeology Find',
    204282:'Dwarf Archaeology Find',206836:'Fossil Archaeology Find',202655:'Troll Archaeology Find',
    207187:'Orc Archaeology Find',207188:'Draenei Archaeology Find',207189:'Vrykul Archaeology Find',
    207190:"Tol'vir Archaeology Find"}


def collected(find):
    import json
    path=runtime.ROOT/'run/collected_find.json'
    if not path.exists():return False
    receipt=json.loads(path.read_text())
    return receipt['runtime']==find.get('runtime') and find['observed_at']<=receipt['observed_at']


def created(reader,payload,diagnostics=None):
    # Same supported 60895 stationary CreateObject layout as the telescope
    # reader. Values updates and every other object type are ignored.
    r=reader.Reader(payload);instance,count,flags=r.u16(),r.u32(),r.byte()
    def note(reason):
        if diagnostics is not None:
            if reason in diagnostics or len(diagnostics)<16:diagnostics[reason]=diagnostics.get(reason,0)+1
    if count!=1 or flags!=0x80:
        note(f'update_header_count_{count}_flags_{flags}');return None
    if r.u32()!=len(payload)-r.offset:raise ValueError('visible find update size mismatch')
    kind,guid=r.byte(),r.guid()
    if kind not in (1,2) or r.byte()!=8:return None
    entry=(guid[1]>>6)&0x7fffff
    if entry not in FINDS:return None
    note(f'known_find_entry_{entry}')
    movement=r.take(3)
    if movement not in (b'\x82\x10\x00',b'\xc2\x10\x00'):
        note('known_find_movement_flags_'+movement.hex());return None
    pauses=r.u32()
    if pauses>32:raise ValueError('visible find pause bound')
    north,west,height,angle=struct.unpack('<ffff',r.take(16))
    if not all(map(math.isfinite,(north,west,height,angle))) or max(abs(north),abs(west))>100000:
        raise ValueError('invalid visible find position')
    r.take(8+pauses*4);fields=reader.Reader(r.take(r.u32()))
    if r.offset!=len(payload):raise ValueError('trailing visible find data')
    prefix=fields.take(5)
    if prefix!=b'\x00\x00\x07\xff\x01':
        note('known_find_fields_prefix_'+prefix.hex());return None
    if fields.u32()!=entry:raise ValueError('visible find entry mismatch')
    fields.take(28);effects=fields.u32()
    if effects>32:raise ValueError('visible find effect bound')
    fields.take(effects*4);owner=fields.guid()
    return {'entry':entry,'name':FINDS[entry],'instance':instance,'north':north,'west':west,'owner':owner}


def owned(reader,window,direction,opcode,payload,stamp,diagnostics=None):
    if (direction!='server_to_client' or opcode!=0x4B0000 or not window.active
        or window.player is None or not 0<=stamp-window.requested<=8):return None
    try:record=created(reader,payload,diagnostics)
    except (ValueError,struct.error,IndexError) as error:
        if diagnostics is not None:
            reason='parse_rejected_'+str(error)[:80]
            if reason in diagnostics or len(diagnostics)<16:diagnostics[reason]=diagnostics.get(reason,0)+1
        return None
    if not record or record.pop('owner')!=window.player:return None
    return {**record,'observed_at':stamp,'source':'owned_authenticated_visible_find_create_after_own_survey'}


def attach(row,now):
    import json
    path=runtime.ROOT/'run/visible_find.json'
    row['visible_find']=None
    if not path.exists():return row
    try:
        find=json.loads(path.read_text());feed=json.loads((runtime.ROOT/'run/bearing_reader.json').read_text())
        world=row['archaeology']['world']
        if (find['runtime']!=row['runtime'] or collected(find) or feed['status']!='ready'
            or find['reader_pid']!=feed['pid'] or find['reader_start_ticks']!=feed['start_ticks']
            or runtime.proc_start(feed['pid'])!=feed['start_ticks'] or not 0<=now-find['observed_at']<=20
            or not world or world['instance']!=find['instance']):return row
        distance=math.hypot(world['north']-find['north'],world['west']-find['west'])
        if distance>40:return row
        row['visible_find']={**find,'distance_yards':distance,
            'estimated_position':False,
            'world':{'instance':find['instance'],'north':find['north'],'west':find['west']}}
    except (ValueError,KeyError,OSError):pass
    return row


def in_range(row):
    find=row.get('visible_find')
    return bool(find and find['distance_yards']<=.5)
