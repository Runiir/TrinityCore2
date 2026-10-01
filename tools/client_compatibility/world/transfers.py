"""Owned-player teleports, using native writers and the 60895 WPP layout."""
from .buffer import Reader,Writer,player_high

CLIENT_NAMES={'CMSG_MOVE_TELEPORT_ACK','CMSG_SUSPEND_TOKEN_RESPONSE','CMSG_WORLD_PORT_RESPONSE'}


def _near(owner,body):
    r=Reader(body);present=[False]*8
    for i in [6,0,3,2]:present[i]=bool(r.bits(1))
    vehicle=r.bits(1)
    if vehicle:raise ValueError('vehicle teleport is not implemented')
    transport=r.bits(1);present[1]=bool(r.bits(1))
    if transport:raise ValueError('transport teleport is not implemented')
    for i in [4,7,5]:present[i]=bool(r.bits(1))
    seq,=r.unpack('I');octets=[0]*8
    def read(indices):
        for i in indices:
            if present[i]:octets[i]=r.raw(1)[0]^1
    read([1,2,3,5]);x,=r.unpack('f');read([4]);o,=r.unpack('f')
    read([7]);z,=r.unpack('f');read([0,6]);y,=r.unpack('f');r.end()
    guid=int.from_bytes(bytes(octets),'little')
    if guid!=owner.character['guid']:return None
    owner.pending_near={'sequence':seq,'position':(x,y,z,o)}
    return 'SMSG_MOVE_TELEPORT',Writer().guid(guid,player_high()).pack('I4fB',seq,x,y,z,o,0).bits(0,2).finish()


def response(owner,name,body):
    if name=='MSG_MOVE_TELEPORT':return _near(owner,body)
    if name=='SMSG_TRANSFER_PENDING':
        r=Reader(body);spell,ship=r.bits(1),r.bits(1)
        vessel=r.unpack('iI') if ship else None
        spell_id=r.unpack('i')[0] if spell else None
        target,=r.unpack('i');r.end()
        position=getattr(owner,'latest_movement',None) or owner.self_snapshot['movement']['position']
        owner.pending_far={'map':target,'stage':'pending'}
        w=Writer().pack('i3f',target,*position[:3]).bits(ship,1).bits(spell,1)
        if vessel:w.pack('Ii',vessel[1],vessel[0])
        if spell:w.pack('i',spell_id)
        return name,w.finish()
    if name=='SMSG_SUSPEND_TOKEN':
        r=Reader(body);seq,=r.unpack('I');reason=r.bits(1);r.end()
        pending=getattr(owner,'pending_far',None)
        if not pending:raise ValueError('suspend without a native transfer')
        pending.update(sequence=seq,reason=reason,stage='suspended')
        return name,Writer().pack('I',seq).bits(reason,2).finish()
    if name=='SMSG_NEW_WORLD':
        r=Reader(body);x,o,z,target,y=r.unpack('fffif');r.end()
        pending=getattr(owner,'pending_far',None)
        if not pending or pending['map']!=target or pending['stage']!='acknowledged':
            raise ValueError('new world without a matching native transfer')
        pending.update(position=(x,y,z,o),stage='new_world')
        owner.character['map']=target;owner.created=False
        owner.visible_gameobjects={};owner.visible_units={}
        owner.taxi_menu=None;owner.gossip_menu=None;owner.pending_near=None
        owner.latest_movement=(x,y,z,o)
        return name,Writer().pack('i4fI3fi',target,x,y,z,o,16,0,0,0,pending['sequence']).finish()
    return None


def request(owner,name,body):
    r=Reader(body)
    if name=='CMSG_MOVE_TELEPORT_ACK':
        guid,high=r.guid();seq,ticks=r.unpack('II');r.end()
        pending=getattr(owner,'pending_near',None)
        if high!=player_high() or guid!=owner.character['guid'] or not pending or seq!=pending['sequence']:
            raise ValueError('unmatched teleport acknowledgement')
        octets=guid.to_bytes(8,'little');w=Writer().pack('II',seq,ticks)
        for i in [5,0,1,6,3,7,2,4]:w.bits(bool(octets[i]),1)
        for i in [4,2,7,6,5,1,3,0]:
            if octets[i]:w.raw(bytes([octets[i]^1]))
        owner.latest_movement=pending['position'];owner.pending_near=None
        return 'MSG_MOVE_TELEPORT_ACK',w.finish()
    pending=getattr(owner,'pending_far',None)
    if name=='CMSG_SUSPEND_TOKEN_RESPONSE':
        seq,=r.unpack('I');r.end()
        if not pending or seq!=pending['sequence'] or pending['stage']!='suspended':
            raise ValueError('unmatched suspend acknowledgement')
        pending['stage']='acknowledged'
        return name,body
    if name=='CMSG_WORLD_PORT_RESPONSE':
        r.end()
        if not pending or pending['stage']!='new_world':raise ValueError('unmatched world port acknowledgement')
        pending['stage']='entering'
        return 'MSG_MOVE_WORLDPORT_ACK',b''
    raise ValueError('unknown transfer acknowledgement')


def resume(owner):
    pending=getattr(owner,'pending_far',None)
    if pending and pending['stage']=='entering':
        owner.world.send('SMSG_RESUME_TOKEN',Writer().pack('I',pending['sequence']).bits(pending['reason'],2).finish())
        owner.pending_far=None
