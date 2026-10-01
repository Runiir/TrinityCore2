"""Native-authoritative flight menus and public-table multi-hop route encoding."""
import heapq
from functools import lru_cache
from .buffer import Reader,Writer
from . import units,gameobjects

CLIENT_NAMES={'CMSG_TAXI_NODE_STATUS_QUERY','CMSG_TAXI_QUERY_AVAILABLE_NODES',
              'CMSG_ENABLE_TAXI_NODE','CMSG_ACTIVATE_TAXI'}
NATIVE_NAMES={'CMSG_TAXI_NODE_STATUS_QUERY':'CMSG_TAXINODE_STATUS_QUERY',
              'CMSG_TAXI_QUERY_AVAILABLE_NODES':'CMSG_TAXIQUERYAVAILABLENODES',
              'CMSG_ENABLE_TAXI_NODE':'CMSG_ENABLETAXI'}


@lru_cache(maxsize=1)
def paths():
    from ..observation.map_data import catalog
    return catalog()['taxi_paths']


def route(source,destination,known,edges=None):
    graph={}
    for edge in edges if edges is not None else paths():
        if edge['source'] in known and edge['destination'] in known:
            graph.setdefault(edge['source'],[]).append((edge['destination'],edge['cost']))
    queue=[(0,source,[source])];best={}
    while queue:
        cost,node,journey=heapq.heappop(queue)
        if node in best:continue
        best[node]=cost
        if node==destination:return journey
        for next_node,fare in graph.get(node,[]):
            heapq.heappush(queue,(cost+fare,next_node,journey+[next_node]))
    raise ValueError('destination has no known native taxi route')


def request(owner,name,body):
    r=Reader(body);native=units.owned_native(owner,r)
    if name!='CMSG_ACTIVATE_TAXI':
        r.end();return NATIVE_NAMES[name],Writer().pack('Q',native).finish()
    destination,_,_=r.unpack('III');r.end()
    menu=getattr(owner,'taxi_menu',None)
    if not menu or menu['vendor']!=native or destination not in menu['known']:
        raise ValueError('taxi selection does not belong to an owned native menu')
    journey=route(menu['source'],destination,menu['known'])
    if len(journey)<2:raise ValueError('taxi destination is the current node')
    return 'CMSG_ACTIVATETAXIEXPRESS',Writer().pack('QI',native,len(journey)).pack('I'*len(journey),*journey).finish()


def response(owner,name,body):
    if name=='SMSG_SHOWTAXINODES':
        r=Reader(body);window,native,source,count=r.unpack('IQII')
        if window!=1 or count>256:raise ValueError('unexpected native taxi menu')
        record=getattr(owner,'visible_units',{}).get(native)
        if not record:return None
        mask=r.raw(count);r.end()
        known={i*8+b+1 for i,value in enumerate(mask) for b in range(8) if value&(1<<b)}
        owner.taxi_menu={'vendor':native,'source':source,'known':known}
        mask+=bytes((-len(mask))%8);chunks=len(mask)//8
        w=Writer().bits(1,1).pack('II',chunks,chunks).guid(*gameobjects.modern_guid(native,record['map'])).pack('I',source)
        return 'SMSG_SHOW_TAXI_NODES',w.raw(mask).raw(mask).finish()
    if name=='SMSG_TAXINODE_STATUS':
        r=Reader(body);native,status=r.unpack('QB');r.end()
        record=getattr(owner,'visible_units',{}).get(native)
        if not record:return None
        return 'SMSG_TAXI_NODE_STATUS',Writer().guid(*gameobjects.modern_guid(native,record['map'])).bits(status,2).finish()
    if name=='SMSG_ACTIVATETAXIREPLY':
        r=Reader(body);status,=r.unpack('I');r.end()
        return 'SMSG_ACTIVATE_TAXI_REPLY',Writer().bits(status,4).finish()
    if name=='SMSG_NEW_TAXI_PATH':
        Reader(body).end();return name,b''
    return None
