import struct
from types import SimpleNamespace
from tools.client_compatibility.world.buffer import Writer
from . import survey_find,guide


class Cursor:
    def __init__(self,data):self.data=data;self.offset=0
    def take(self,n):
        if n<0 or self.offset+n>len(self.data):raise ValueError('truncated')
        value=self.data[self.offset:self.offset+n];self.offset+=n;return value
    def byte(self):return self.take(1)[0]
    def u16(self):return struct.unpack('<H',self.take(2))[0]
    def u32(self):return struct.unpack('<I',self.take(4))[0]
    def guid(self):
        masks=self.byte(),self.byte()
        return tuple(sum(self.byte()<<(i*8) for i in range(8) if mask&(1<<i)) for mask in masks)


def packet(owner=(1,2)):
    entry=206836
    fields=(Writer().raw(b'\x00\x00\x07\xff\x01').pack('I',entry).raw(bytes(28))
        .pack('I',0).guid(*owner).finish())
    body=(Writer().pack('B',1).guid(77,(11<<58)|(entry<<6)).pack('B',8)
        .raw(b'\x82\x10\x00').pack('Iffff',0,10.,20.,30.,0.).raw(bytes(8))
        .pack('I',len(fields)).raw(fields).finish())
    return struct.pack('<HIBI',1,1,0x80,len(body))+body


def test_only_own_find_spawn_in_own_survey_window_is_accepted():
    reader=SimpleNamespace(Reader=Cursor);window=SimpleNamespace(active=True,player=(1,2),requested=100)
    record=survey_find.owned(reader,window,'server_to_client',0x4B0000,packet(),101)
    assert record['name']=='Fossil Archaeology Find' and record['north']==10 and 'owner' not in record
    assert survey_find.owned(reader,window,'server_to_client',0x4B0000,packet((9,10)),101) is None
    assert survey_find.owned(reader,window,'server_to_client',0x4B0000,packet(),109) is None
    assert survey_find.owned(reader,window,'client_to_server',0x4B0000,packet(),101) is None
    for i in range(len(packet())):
        assert survey_find.owned(reader,window,'server_to_client',0x4B0000,packet()[:i],101) is None


def test_out_of_range_context_uses_visible_find_bearing_then_allows_loot():
    from tools.client_compatibility.archaeology_policy import label
    row={'movement':{'facing_radians':0,'in_world':True,'health_percent':100,
        'dead':False,'in_combat':False,'on_taxi':False},
        'archaeology':{'world':{'instance':1,'north':0,'west':0},'casting':False},
        'visible_find':{'world':{'instance':1,'north':8,'west':0},'distance_yards':8}}
    waypoint,error=guide.select(row,{'reapproach_find':True},None)
    assert error==0 and label(guide.model_state(row,waypoint,survey_find.in_range(row)))=='forward_short'
    row['visible_find']['distance_yards']=2
    assert not survey_find.in_range(row)
    row['visible_find']['distance_yards']=.4
    assert label(guide.model_state(row,waypoint,survey_find.in_range(row)))=='loot'
