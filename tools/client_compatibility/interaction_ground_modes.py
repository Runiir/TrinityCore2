"""Bounded observed walk/run and autorun inputs with native and peer outcomes."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import binding_key
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_ground_movement import suite,move,packets,position,angle
from .interaction_macros import require
from .observation.journal import entries
from .world.movement import parse
from .world.buffer import Reader

WALK=0x100


def mode(t,oracle,session,walking,label):
    before=position(t.fixture['guid']);since=time.time();suffix='SET_WALK_MODE' if walking else 'SET_RUN_MODE'
    def outcome(b,a,selected):
        pair=packets(since,session,t.fixture['guid'],suffix,suffix)
        bar=detail(t,label+'_value');after=position(t.fixture['guid'])
        checks={'observed_binding':selected=='toggle',
            'native_mode_request':bool(pair) and all(p['native'] for p in pair),
            'walking_flag':bool(pair) and all(bool(p['movement']['flags']&WALK)==walking for p in pair),
            'position':math.dist(before[:3],after[:3])<.05 and abs(angle(before[3],after[3]))<.05,
            'idle':bar['pose'].get('speed')==0,'main_bar':signature(bar)==signature(t.ground_bar),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'native_ground_mode_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'request_pairs':pair,'native_before':before,'native_after':after,'public':bar}}
    require(t.step(label,'Toggle the installed walk/run binding and verify its native mode.',
        {'toggle':{'kind':'key','value':binding_key(t.ground_bar['keys']['TOGGLERUN'][0]),
            'hold':.4,'description':'Press the observed walk/run binding once.'}},outcome,
        diagnostic_action='toggle'),'native_ground_mode_pass')


def cadence(case,walking):
    pairs=case['oracle']['request_pairs'];starts=[p for p in pairs if p['modern']['name']=='CMSG_MOVE_START_FORWARD']
    stops=[p for p in pairs if p['modern']['name']=='CMSG_MOVE_STOP']
    if not starts or not stops:raise RuntimeError('movement cadence lacks native start/stop attribution')
    a,b=starts[0]['movement'],stops[-1]['movement'];seconds=((b['time']-a['time'])&0xffffffff)/1000
    distance=math.dist(a['position'][:2],b['position'][:2]);speed=distance/seconds if seconds else 0
    expected=2.5 if walking else 7.0
    checks={'walking_flag':all(bool(p['movement']['flags']&WALK)==walking for p in pairs),
        'duration':.5<seconds<2.5,'speed':abs(speed-expected)<.6,
        'native_final_position':math.dist(b['position'][:2],case['oracle']['native_after'][:2])<.2}
    return {'walking':walking,'seconds':seconds,'yards':distance,'yards_per_second':speed,
        'expected_yards_per_second':expected,'checks':checks}


def autorun_inputs(t,key,row):
    started=False
    try:
        t.io.key(key,hold=.4);started=True
        row['input_transport']=[{'toggle':'start','time':time.time()}];t.persist()
        time.sleep(1.2)
    finally:
        # Stop before reading journals or waiting for a screenshot. A normal
        # start must never extend its movement duration with diagnostics.
        if started:
            t.io.key(key,hold=.4)
            row.setdefault('input_transport',[]).append({'toggle':'stop','time':time.time()});t.persist()
        else:
            # A sender error may occur after a partial start. Holding and
            # releasing the observed forward binding also cancels autorun.
            forward=binding_key(t.ground_bar['keys']['MOVEFORWARD'][0])
            t.io.key(forward,hold=.2)
            row.setdefault('input_transport',[]).append({'cleanup':'forward override and release',
                'time':time.time(),'qualification':False});t.persist()


def autorun(t,peer,session,peer_session):
    before,frame=t.observe('autorun_before');native_before=position(t.fixture['guid'])
    key=binding_key(t.ground_bar['keys']['TOGGLEAUTORUN'][0]);since=time.time()
    lock_mask=16 # X11 Mod2Mask on this private XKB map; verify the Num_Lock binding below.
    numlock_key=t.io.raw.display.keysym_to_keycode(t.io.raw.XK.string_to_keysym('Num_Lock'))
    modifiers=t.io.raw.display.get_modifier_mapping()
    if numlock_key not in modifiers[4]:raise RuntimeError('private Num_Lock is not the observed Mod2 binding')
    lock_before=bool(t.io.raw.display.screen().root.query_pointer().mask&lock_mask)
    row={'id':'movement.autorun','goal':'Start and stop autorun through its observed toggle.',
        'time':since,'before':before,'before_frame':frame,'status':'started','selected':'autorun',
        'selection_source':'code','request':None,'response':None,
        'input':{'kind':'key','value':key,'hold':.4,'toggle_count':2,'between_seconds':1.2},
        'numlock_before':lock_before};t.receipt['cases'].append(row);t.persist()
    autorun_inputs(t,key,row)
    native_after=position(t.fixture['guid']);deadline=time.monotonic()+12;samples=[]
    while True:
        after,after_frame=t.observe('autorun_after')
        agrees=math.dist(native_after[:2],after['world_position'][:2])<.2
        samples.append({'frame':after_frame,'agrees':agrees,'input_replayed':False})
        if agrees or time.monotonic()>deadline:break
        time.sleep(.2)
    bar=detail(t,'autorun_value');pair=packets(since,session,t.fixture['guid'],'START_FORWARD','STOP')
    with actor(peer.fixture['actor']):other,peer_frame=peer.observe('peer_'+t.fixture['actor']+'_autorun')
    broadcast=[]
    for packet in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if packet.get('time',0)<since or packet.get('session')!=peer_session or packet.get('name')!='SMSG_MOVE_UPDATE' or packet.get('direction')!='to_client':continue
        body=bytes.fromhex(packet['body'])
        if Reader(body).guid()[0]==t.fixture['guid']:
            broadcast.append({'time':packet['time'],'movement':parse(body,t.fixture['guid'])})
    seen=other.get('target',{}).get('position',[]);dx,dy=[native_after[i]-native_before[i] for i in [0,1]]
    projection=dx*math.cos(native_before[3])+dy*math.sin(native_before[3]);stops=[p for p in pair if p['modern']['name']=='CMSG_MOVE_STOP']
    lock_after=bool(t.io.raw.display.screen().root.query_pointer().mask&lock_mask)
    checks={'native_start_stop':all(any(p['modern']['name']=='CMSG_MOVE_'+suffix and p['native'] for p in pair) for suffix in ['START_FORWARD','STOP']),
        'native_stop_idle':bool(stops) and stops[-1]['movement']['flags']==0,
        'bounded_forward':1<projection<25,'public_position':math.dist(native_after[:2],after['world_position'][:2])<.2,
        'peer_position':len(seen)>=4 and math.dist(native_after[:2],seen[:2])<.2,
        'peer_stop':bool(broadcast) and broadcast[-1]['movement']['flags']==0,
        'idle':bar['pose'].get('speed')==0,'numlock_restored':lock_after==lock_before,
        'main_bar':signature(bar)==signature(t.ground_bar),
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
    row.update(after=after,after_frame=after_frame,peer_frame=peer_frame,numlock_after=lock_after,
        oracle={'checks':checks,'native_before':native_before,'native_after':native_after,
            'projection':projection,'request_pairs':pair,'peer_packets':broadcast,'public':bar,'public_settling':samples},
        status='native_autorun_pass' if all(checks.values()) else 'client_or_protocol_failure',finished_at=time.time());t.persist()
    if not all(checks.values()):raise RuntimeError('autorun native/public/peer checks differ')


def phase(t,peer,oracle,session,peer_session):
    if any(not t.ground_bar['keys'].get(k) for k in ['TOGGLERUN','TOGGLEAUTORUN']):raise RuntimeError('owned ground-mode binding absent')
    since=time.time()
    try:
        mode(t,oracle,session,True,'movement.walk_on')
        move(t,peer,session,peer_session,'forward','MOVEFORWARD','START_FORWARD','STOP',1)
        slow=cadence(t.receipt['cases'][-1],True)
        mode(t,oracle,session,False,'movement.walk_off')
        move(t,peer,session,peer_session,'forward','MOVEFORWARD','START_FORWARD','STOP',1)
        fast=cadence(t.receipt['cases'][-1],False)
        t.receipt['ground_speed_comparison']={'walk':slow,'run':fast,
            'checks':{'both_native_cadences':all(slow['checks'].values()) and all(fast['checks'].values()),
                'slower_walk':slow['yards_per_second']<fast['yards_per_second']/2}};t.persist()
        if not all(t.receipt['ground_speed_comparison']['checks'].values()):raise RuntimeError('native walk/run speed comparison failed')
        autorun(t,peer,session,peer_session)
    finally:
        modes=[p['name'] for p in entries(lab.ROOT/'evidence/world_packets.jsonl')
            if p.get('time',0)>=since and p.get('session')==session and p.get('direction')=='from_client'
            and p.get('name') in ['CMSG_MOVE_SET_WALK_MODE','CMSG_MOVE_SET_RUN_MODE']]
        walking=bool(modes) and modes[-1]=='CMSG_MOVE_SET_WALK_MODE'
        if walking:mode(t,oracle,session,False,'fixture.walk_mode_cleanup')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
