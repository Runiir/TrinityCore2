"""Fresh owned-session player, taxi and transfer facts from ordinary packets."""
import json
from .. import lab_runtime as lab
from ..world import movement
from ..world.buffer import Reader
from ..world.native_objects import records
from ..world.objects import INDEX


class Observer:
    def __init__(self):
        events=[json.loads(s) for s in (lab.ROOT/'logs/modern_world.jsonl').read_text().splitlines()]
        entry=next(r for r in reversed(events) if r['event']=='native_player_created' and r['guid']==1)
        self.session=entry['session'];self.started=entry['time'];self.offset=0
        self.position=entry['position'];self.map=entry['map'];self.seen_at=entry['time']
        self.taxi=None;self.transferring=False;self.transfer_events=[];self.taxi_replies=[]
        self.gossip=None
        self.units={};self.player_level=85;self.player_faction=1

    def poll(self):
        with (lab.ROOT/'evidence/world_packets.jsonl').open() as handle:
            if handle.seek(0,2)<self.offset:raise RuntimeError('owned packet trace was rotated during travel')
            handle.seek(self.offset)
            while line:=handle.readline():
                if not line.endswith('\n'):break
                self.offset=handle.tell();p=json.loads(line)
                if p.get('session')!=self.session or p['time']<self.started:continue
                name=p['name'];body=bytes.fromhex(p['body']);r=Reader(body)
                if p['direction']=='from_client' and (name in movement.SUPPORTED or name=='CMSG_MOVE_SET_FACING_HEARTBEAT'):
                    self.position=list(movement.parse(body,1)['position']);self.seen_at=p['time']
                if p['direction']=='to_client':
                    if name=='SMSG_MOVE_TELEPORT':
                        guid,_=r.guid();_,x,y,z,o,_=r.unpack('I4fB')
                        if guid==1:self.position=[x,y,z,o];self.seen_at=p['time'];self.taxi=None
                    elif name=='SMSG_TRANSFER_PENDING':self.transferring=True
                    elif name=='SMSG_NEW_WORLD':
                        self.map,x,y,z,o=r.unpack('i4f');self.position=[x,y,z,o];self.seen_at=p['time'];self.taxi=None
                        self.units={}
                    elif name=='SMSG_RESUME_TOKEN':self.transferring=False
                    if any(s in name for s in ['TRANSFER','NEW_WORLD','SUSPEND_TOKEN','RESUME_TOKEN']):
                        self.transfer_events.append({'name':name,'time':p['time']})
                if p['direction']=='from_native':
                    if name=='SMSG_SHOWTAXINODES':
                        _,vendor,source,count=r.unpack('IQII');mask=r.raw(count);r.end()
                        self.taxi={'source':source,'vendor':vendor,'seen_at':p['time'],
                            'known':[i*8+b+1 for i,v in enumerate(mask) for b in range(8) if v&(1<<b)]}
                    elif name=='SMSG_GOSSIP_MESSAGE':
                        from ..world.gossip import text
                        guid,menu,text_id,count=r.unpack('QIII');options=[]
                        if count>64:raise ValueError('excessive gossip menu')
                        for _ in range(count):
                            index,icon,flags,cost=r.unpack('iBBI');title=text(r).decode();text(r)
                            options.append({'id':index,'icon':icon,'title':title})
                        self.gossip={'guid':guid,'menu':menu,'options':options,'seen_at':p['time']}
                    elif name=='SMSG_GOSSIP_COMPLETE':self.gossip=None
                    elif name=='SMSG_ACTIVATETAXIREPLY':self.taxi_replies.append({'status':r.unpack('I')[0],'time':p['time']})
                    elif name=='SMSG_UPDATE_OBJECT':
                        for record in records(body):
                            if record['update_type']==3:
                                for guid in record['removed']:self.units.pop(guid,None)
                            elif record.get('kind')==3 and record['guid']>>52==0xF13:
                                self.units[record['guid']]=record
                            elif record['update_type']==0 and record['guid'] in self.units:
                                self.units[record['guid']]['fields'].update(record['fields'])
                            if record.get('guid')==1 and 'movement' in record:
                                self.map=record['map'];self.position=list(record['movement']['position']);self.seen_at=p['time']
                                self.player_level=record['fields'].get(INDEX['UNIT_FIELD_LEVEL'],85)
                                self.player_faction=record['fields'].get(INDEX['UNIT_FIELD_FACTIONTEMPLATE'],1)
                    elif name=='SMSG_DESTROY_OBJECT':self.units.pop(r.unpack('Q')[0],None)
        from ..hostile_avoidance import visible_hostiles
        return {'session':self.session,'map':self.map,'position':self.position,'seen_at':self.seen_at,
            'taxi_menu':self.taxi,'transferring':self.transferring,'taxi_replies':self.taxi_replies,
            'gossip_menu':self.gossip,
            'visible_hostiles':visible_hostiles(self.units,self.map,self.player_faction,self.player_level),
            'transfer_events':self.transfer_events,'source':'owned_session_normal_travel_packets'}
