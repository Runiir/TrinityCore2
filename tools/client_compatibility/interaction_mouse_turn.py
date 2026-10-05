"""Bounded ordinary right-button turning with native and owned peer agreement."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_ground_movement import suite,packets,position,angle
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_macros import require
from .observation.journal import entries
from .world.movement import parse
from .world.buffer import Reader


def settled_checks(before,after,public,facing,seen,pairs,broadcast,speed):
    change=angle(before[3],after[3])
    attributed=[p for p in pairs if p.get('native') and
        abs(angle(p['movement']['position'][3],after[3]))<.05]
    return {'bounded_facing_change':.15<abs(change)<2,
        'position_preserved':math.dist(before[:3],after[:3])<.2 and before[4]==after[4]==0,
        'native_facing_request':bool(attributed),
        'public_position':len(public)>=2 and math.dist(after[:2],public[:2])<.2,
        'public_facing':abs(angle(after[3],facing))<.05,
        # UnitPosition's fourth value is a map field, never an orientation.
        'peer_position':len(seen)>=4 and math.dist(after[:2],seen[:2])<.2,
        'peer_broadcast_facing':bool(broadcast) and
            abs(angle(after[3],broadcast[-1]['movement']['position'][3]))<.05,
        'released_idle':speed==0}


def turn(t,peer,session,peer_session,direction):
    before=position(t.fixture['guid']);since=time.time()
    start,end=([900,420],[980,420]) if direction=='right' else ([980,420],[900,420])
    def outcome(b,a,selected):
        after=position(t.fixture['guid']);deadline=time.monotonic()+12;samples=[]
        while True:
            public,frame=t.observe('mouse_turn_'+direction+'_settled')
            agrees=abs(angle(after[3],frame['movement']['facing_radians']))<.05
            samples.append({'frame':frame,'native_public_facing':agrees,'input_replayed':False})
            if agrees or time.monotonic()>deadline:break
            time.sleep(.2)
        bar=detail(t,'mouse_turn_'+direction+'_bar')
        with actor(peer.fixture['actor']):other,peer_frame=peer.observe('peer_'+t.fixture['actor']+'_mouse_'+direction)
        pair=packets(since,session,t.fixture['guid'],'SET_FACING','HEARTBEAT');broadcast=[]
        for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if (row.get('time',0)<since or row.get('session')!=peer_session or
                row.get('name')!='SMSG_MOVE_UPDATE' or row.get('direction')!='to_client'):continue
            body=bytes.fromhex(row['body'])
            if Reader(body).guid()[0]==t.fixture['guid']:
                broadcast.append({'time':row['time'],'movement':parse(body,t.fixture['guid'])})
        seen=other.get('target',{}).get('position',[])
        checks=settled_checks(before,after,public.get('world_position',[]),frame['movement']['facing_radians'],
            seen,pair,broadcast,bar['pose'].get('speed'))
        checks.update(ordinary_right_drag=selected=='turn',main_bar=signature(bar)==signature(t.ground_bar),
            ui_clean=not public.get('lua_errors') and not public.get('blocked_actions'))
        return {'status':'native_mouse_turn_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_before':before,'native_after':after,
                'facing_change':angle(before[3],after[3]),'public_position':public.get('world_position'),
                'public_frame':frame,'peer_position':seen,'peer_frame':peer_frame,
                'request_pairs':pair,'peer_packets':broadcast,'settling':samples}}
    require(t.step('movement.mouse_turn.'+direction,'Turn through an ordinary right-button world drag, then release.',
        {'turn':{'kind':'drag','start':start,'end':end,'button':3,'duration':1.0}},outcome,
        diagnostic_action='turn'),'native_mouse_turn_pass')
    return t.receipt['cases'][-1]['oracle']['facing_change']


def phase(t,peer,oracle,session,peer_session):
    t.receipt['qualified_scope']='Owned primary and scout each turn through one right-button world drag in each horizontal direction. '
    t.receipt['qualified_scope']+='Native accepted orientation, rendered player facing and owned peer movement-broadcast orientation must agree; peer public coordinates must match, '
    t.receipt['qualified_scope']+='with bounded position change and released idle input. Original native positions/headings, resources, '
    t.receipt['qualified_scope']+='stats, saved spells/actions, pose/AFK, target and solo group restore. Camera-only orbit, pitch, movement while turning and sensitivity remain open.'
    t.receipt['custom_script_permission']='blocked_by_user';t.persist()
    right=turn(t,peer,session,peer_session,'right');left=turn(t,peer,session,peer_session,'left')
    t.receipt['mouse_turn_opposite_directions']={'right':right,'left':left,'opposite':right*left<0};t.persist()
    if right*left>=0:raise RuntimeError('opposite mouse drags do not produce opposite native heading changes')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    suite(a.output,work=phase,separated=True)
