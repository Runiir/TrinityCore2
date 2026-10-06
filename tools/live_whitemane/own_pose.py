"""Decode only authenticated, owned-player 60895 movement, without raw storage.

Layout is WPP 28fc3d1 V4_4_0_54481 ReadMovementStats, already exercised by
the local 4.4.2 rewrite. Unsupported optional layouts produce no height signal.
"""
import math
from tools.client_compatibility.world.buffer import Reader


def parse(payload, player):
    r=Reader(payload)
    mover=r.guid()
    if mover!=player or mover[1]>>58!=2:
        raise ValueError('movement is not the owned player')
    flags,flags2,flags3,tick=r.unpack('4I')
    north,west,height,facing,pitch,elevation=r.unpack('6f')
    forces,_=r.unpack('2I')
    if forces>16:raise ValueError('unsupported movement forces')
    for _ in range(forces):r.guid()
    presence=[r.bits(1) for _ in range(8)]
    # WPP's pinned ReadMovementStats uses the presence byte, not scalar
    # flag values, to select additional fields. Whitemane retains flags3=8
    # after an instant taxi; it does not change this packet's layout.
    # HasSpline (bit 3) is also a value-only bit in this message.
    if any(presence[i] for i in (1,6,7)):
        mask=sum(bit<<i for i,bit in enumerate(presence))
        raise ValueError(f'unsupported movement layout flags={flags:x}/{flags2:x}/{flags3:x} optional={mask:02x}')
    if presence[0]:r.guid()
    if presence[2]:
        fall_time,vertical=r.unpack('If')
        if r.bits(1):r.unpack('3f')
    r.end()
    if not all(math.isfinite(v) for v in (north,west,height,facing,pitch,elevation)) or max(abs(north),abs(west),abs(height))>17067:
        raise ValueError('invalid owned movement position')
    return {'north':north,'west':west,'height_yards':height,
            'movement_flags':flags,'movement_flags2':flags2,'movement_flags3':flags3,
            'facing_radians':facing,'client_uptime_ms':tick,
            'flying':bool(flags&0x1000000),'falling':bool(flags&0x800),
            'ascending':bool(flags&0x200000),'descending':bool(flags&0x400000),
            'pitch_radians':pitch}


def match(row, pose, *, now):
    """Bind the pose to current addon XY and flight state, never to another map."""
    world=row['archaeology']['world']
    if not world or pose.get('runtime')!=row['runtime']:return None
    age=now-pose['observed_at']
    stationary=row['movement']['speed']==0 and not row['archaeology']['falling']
    if not 0<=age<=(30 if stationary else 2):return None
    limit=.75 if stationary else 2+row['movement']['speed']*.6
    if math.hypot(pose['north']-world['north'],pose['west']-world['west'])>limit:return None
    transition=pose['flying']!=row['archaeology']['flying'] or pose['falling']!=row['archaeology']['falling']
    if transition and age>.75:return None
    return {**pose,'instance':world['instance'],'age_seconds':age,
            'movement_mode_transition':transition,
            'source':'authenticated_owned_player_movement_matched_to_public_addon'}
