"""Native inventory oracle independent of the bridge's modern slot mapping."""
import struct
from .journal import Cursor
from ..world.native_objects import records
from ..world.objects import INDEX


class Inventory:
    def __init__(self,root,session,guid):
        self.cursor=Cursor(root/'evidence/world_packets.jsonl')
        self.session,self.guid=session,guid
        self.objects={}

    def poll(self):
        for row in self.cursor.poll():
            if row.get('session')!=self.session or row.get('direction')!='from_native':continue
            if row.get('name')=='SMSG_DESTROY_OBJECT':
                body=bytes.fromhex(row['body'])
                if len(body)!=9:raise ValueError('native destroyed-item record has invalid length')
                self.objects.pop(int.from_bytes(body[:8],'little'),None);continue
            if row.get('name')!='SMSG_UPDATE_OBJECT':continue
            for record in records(bytes.fromhex(row['body'])):
                if record['update_type']==3:
                    for guid in record['removed']:self.objects.pop(guid,None)
                    continue
                guid=record['guid']
                if guid==self.guid or guid>>48==0x4000:
                    self.objects.setdefault(guid,{}).update(record.get('fields',{}))
        return self

    def pair(self,guid,name,offset=0):
        fields=self.objects.get(guid,{})
        start=INDEX[name]+offset
        return fields.get(start,0)|fields.get(start+1,0)<<32

    def equipment(self,slot):
        if not 1<=slot<=19:raise ValueError('equipment slot outside bound')
        return self.item(self.pair(self.guid,'PLAYER_FIELD_INV_SLOT_HEAD',(slot-1)*2))

    def item(self,guid):
        fields=self.objects.get(guid,{})
        return {'guid':guid,'id':fields.get(INDEX['OBJECT_FIELD_ENTRY'],0),
            'count':fields.get(INDEX['ITEM_FIELD_STACK_COUNT'],0)}

    def character_stats(self):
        fields=self.objects.get(self.guid,{})
        def floating(name):return struct.unpack('<f',struct.pack('<I',fields.get(INDEX[name],0)))[0]
        return {'strength':fields.get(INDEX['UNIT_FIELD_STAT0'],0),
            'armor':fields.get(INDEX['UNIT_FIELD_RESISTANCES'],0),
            'damage':[floating('UNIT_FIELD_MINDAMAGE'),floating('UNIT_FIELD_MAXDAMAGE')],
            'health':fields.get(INDEX['UNIT_FIELD_MAXHEALTH'],0)}

    def slot(self,bag,slot):
        if not 0<=bag<=4 or not 1<=slot<=36:raise ValueError('oracle bag position outside bound')
        if bag==0:
            if slot>16:raise ValueError('native backpack contains sixteen slots')
            guid=self.pair(self.guid,'PLAYER_FIELD_INV_SLOT_HEAD',(23+slot-1)*2)
        else:
            container=self.pair(self.guid,'PLAYER_FIELD_INV_SLOT_HEAD',(19+bag-1)*2)
            guid=self.pair(container,'CONTAINER_FIELD_SLOT_1',(slot-1)*2)
        return self.item(guid)
