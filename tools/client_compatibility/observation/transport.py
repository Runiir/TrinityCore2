"""Fresh owned-session player, taxi and transfer facts from ordinary packets."""
import json
from .. import lab_runtime as lab
from ..world import movement
from ..world.buffer import Reader
from ..world.native_objects import records
from ..world.objects import INDEX
from .journal import Cursor, player_entry


class Observer:
    def __init__(self,*,guid=None,session=None,root=None):
        root=root or lab.ROOT
        entry=player_entry(root,guid,session)
        self.guid=entry['guid']
        self.session=entry['session'];self.started=entry['time'];self.offset=0
        self.position=entry['position'];self.map=entry['map'];self.seen_at=entry['time']
        self.taxi=None;self.transferring=False;self.transfer_events=[];self.taxi_replies=[]
        self.gossip=None;self.selected=None;self.attackers=set();self.player_attack_target=None
        self.units={};self.names={};self.player_level=85;self.player_faction=1
        self.cursor=Cursor(root/'evidence/world_packets.jsonl')

    def poll(self):
        for p in self.cursor.poll():
            if p.get('session')!=self.session or p['time']<self.started:continue
            if p['direction']=='from_native' and p['name']=='SMSG_CREATURE_QUERY_RESPONSE':
                from ..world.gossip import text
                template=Reader(bytes.fromhex(p['body']));entry,=template.unpack('I')
                if not entry&0x80000000:self.names[entry]=text(template).decode()
            name=p['name'];body=bytes.fromhex(p['body']);r=Reader(body)
            if p['direction']=='from_client' and (name in movement.SUPPORTED or name=='CMSG_MOVE_SET_FACING_HEARTBEAT'):
                self.position=list(movement.parse(body,self.guid)['position']);self.seen_at=p['time']
            if p['direction']=='from_client' and name=='CMSG_SET_SELECTION':
                self.selected=r.guid()
            if p['direction']=='to_client':
                if name=='SMSG_MOVE_TELEPORT':
                    guid,_=r.guid();_,x,y,z,o,_=r.unpack('I4fB')
                    if guid==self.guid:self.position=[x,y,z,o];self.seen_at=p['time'];self.taxi=None
                elif name=='SMSG_TRANSFER_PENDING':self.transferring=True
                elif name=='SMSG_NEW_WORLD':
                    self.map,x,y,z,o=r.unpack('i4f');self.position=[x,y,z,o];self.seen_at=p['time'];self.taxi=None
                    self.units={};self.attackers=set()
                elif name=='SMSG_RESUME_TOKEN':self.transferring=False
                if any(s in name for s in ['TRANSFER','NEW_WORLD','SUSPEND_TOKEN','RESUME_TOKEN']):
                    self.transfer_events.append({'name':name,'time':p['time']})
            if p['direction']=='from_native':
                if name=='SMSG_ATTACK_START':
                    attacker,victim=r.unpack('QQ')
                    if victim==self.guid:self.attackers.add(attacker)
                    if attacker==self.guid:self.player_attack_target=victim
                elif name=='SMSG_ATTACK_STOP':
                    from ..world.native_objects import guid as native_guid
                    attacker=native_guid(r);native_guid(r);r.unpack('I')
                    self.attackers.discard(attacker)
                    if attacker==self.guid:self.player_attack_target=None
                elif name=='SMSG_ON_MONSTER_MOVE':
                    from ..world.native_objects import guid as native_guid
                    guid=native_guid(r);r.unpack('B');position=list(r.unpack('3f'))
                    if guid in self.units:
                        self.units[guid]['movement']['position']=position+[self.units[guid]['movement']['position'][3]]
                elif name=='SMSG_SHOWTAXINODES':
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
                        if record.get('guid')==self.guid and 'movement' in record:
                            self.map=record['map'];self.position=list(record['movement']['position']);self.seen_at=p['time']
                            self.player_level=record['fields'].get(INDEX['UNIT_FIELD_LEVEL'],85)
                            self.player_faction=record['fields'].get(INDEX['UNIT_FIELD_FACTIONTEMPLATE'],1)
                elif name=='SMSG_DESTROY_OBJECT':self.units.pop(r.unpack('Q')[0],None)
        from ..hostile_avoidance import visible_hostiles
        from ..world.gameobjects import modern_guid
        selected=next(({'guid':g,'position':list(u['movement']['position']),
            'health':u['fields'].get(INDEX['UNIT_FIELD_HEALTH'],0),
            'max_health':u['fields'].get(INDEX['UNIT_FIELD_MAXHEALTH'],0)}
            for g,u in self.units.items() if modern_guid(g,u['map'])==self.selected),None)
        return {'session':self.session,'map':self.map,'position':self.position,'seen_at':self.seen_at,
            'taxi_menu':self.taxi,'transferring':self.transferring,'taxi_replies':self.taxi_replies,
            'gossip_menu':self.gossip,'selected_unit':selected,'attacking_units':sorted(self.attackers),
            'player_attack_target':self.player_attack_target,
            'visible_unit_names':{g:self.names[g>>32&0xFFFFF] for g in self.units if g>>32&0xFFFFF in self.names},
            'visible_hostiles':visible_hostiles(self.units,self.map,self.player_faction,self.player_level),
            'transfer_events':self.transfer_events,'source':'owned_session_normal_travel_packets'}
