"""Native ordinary ground splines in the pinned 60895 monster-move layout.

Wire reference: WPP 28fc3d1 V4_4_0_54481 MovementHandler.ReadMovementSpline.
Transport, animation and parabolic variants are deliberately not translated.
"""
import math
from .buffer import Reader, Writer
from .native_objects import guid as native_guid
from .gameobjects import modern_guid


def parse(body):
    r=Reader(body);guid=native_guid(r);exit_voluntary,=r.unpack('B')
    position=list(r.unpack('3f'));sequence,face=r.unpack('IB')
    if face not in range(5):raise ValueError('invalid native creature spline face')
    facing=r.unpack('3f') if face==2 else r.unpack('Q')[0] if face==3 else r.unpack('f')[0] if face==4 else None
    flags,=r.unpack('I')
    if flags & 0xFF018000:return None  # special animation/jump/fade or transport
    duration,count=r.unpack('II')
    if count>10000:raise ValueError('native creature spline exceeds point bound')
    uncompressed=bool(flags&0x400000)
    points=[list(r.unpack('3f')) for _ in range(count if uncompressed else min(count,1))]
    deltas=r.raw(max(0,count-1)*4) if not uncompressed else b''
    r.end()
    if not all(math.isfinite(v) and abs(v)<=17067 for p in [position,*points] for v in p):
        raise ValueError('invalid native creature spline coordinates')
    return {'guid':guid,'position':position,'sequence':sequence,'face':face,'facing':facing,
        'flags':flags | (0x20 if face==1 else 0),'duration':duration,'points':points,
        'deltas':deltas,'exit_voluntary':bool(exit_voluntary)}


def response(owner,name,body):
    if name!='SMSG_ON_MONSTER_MOVE':return None
    spline=parse(body)
    if not spline or spline['guid'] not in getattr(owner,'visible_units',{}):return None
    record=owner.visible_units[spline['guid']];map_id=record['map']
    record['movement']['position']=spline['position']+[record['movement']['position'][3]]
    w=Writer().guid(*modern_guid(spline['guid'],map_id)).pack('3fI',*spline['position'],spline['sequence'])
    w.bits(0,1).bits(0,3).flush()  # no cross-realm teleport, default stop tolerance
    w.pack('IIIIB',spline['flags'],0,spline['duration'],0,0).guid().pack('b',-1)
    modern_face={0:0,1:0,2:1,3:2,4:3}[spline['face']]
    w.bits(modern_face,2).bits(len(spline['points']),16).bits(spline['exit_voluntary'],1).bits(0,1)
    w.bits(len(spline['deltas'])//4,16).bits(0,4).flush()
    if modern_face==1:w.pack('3f',*spline['facing'])
    elif modern_face==2:w.pack('f',0).guid(*modern_guid(spline['facing'],map_id))
    elif modern_face==3:w.pack('f',spline['facing'])
    for point in spline['points']:w.pack('3f',*point)
    w.raw(spline['deltas'])
    return 'SMSG_ON_MONSTER_MOVE',w.finish()
