"""Attribute the owned near-teleport acknowledgement before freezing dummy pose."""
from types import SimpleNamespace
from .world.buffer import Reader,player_high
from .world import transfers


def acknowledgement(packets,session,since,until,owner,position):
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until]
    sent=[p for p in rows if p.get('direction')=='to_client' and p.get('name')=='SMSG_MOVE_TELEPORT']
    proofs=[]
    for p in sent:
        r=Reader(bytes.fromhex(p['body']));identity=r.guid();seq,x,y,z,facing,extra=r.unpack('I4fB')
        options=r.bits(2);r.end()
        if identity!=(owner,player_high()) or extra or options:continue
        if any(abs(a-b)>.01 for a,b in zip((x,y,z,facing),position[:4])):continue
        matches=[]
        for c in rows:
            if c.get('direction')!='from_client' or c.get('name')!='CMSG_MOVE_TELEPORT_ACK' or c['time']<p['time']:continue
            try:
                state=SimpleNamespace(character={'guid':owner},pending_near={'sequence':seq,'position':(x,y,z,facing)})
                name,body=transfers.request(state,c['name'],bytes.fromhex(c['body']))
            except ValueError:continue
            native=[n for n in rows if n.get('direction')=='to_native' and n.get('name')==name and
                n['body']==body.hex() and 0<=n['time']-c['time']<2]
            if len(native)==1:matches.append({'modern_teleport':p,'client_ack':c,'native_ack':native[0]})
        if len(matches)==1:proofs.extend(matches)
    if len(proofs)!=1:raise RuntimeError('dummy landing lacks one exact owned teleport and native acknowledgement')
    return proofs[0]


def landing_checks(initial,accepted):
    return {'xy_facing':all(abs(accepted[i]-initial[i])<.01 for i in (0,1,3)),
        'map':accepted[4]==initial[4]==0,'near_spawn_floor':abs(accepted[2]-initial[2])<.2}
