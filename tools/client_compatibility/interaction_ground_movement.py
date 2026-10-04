"""Observed ground bindings, native accepted positions and a second client's view."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sit_stand import pose,afk
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_macros import require
from .interaction_operations import click_case,controls
from .interaction_groups import native_group
from .interaction_group_menu import open_menu
from .nearby_fixture import NearbyFixture
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.movement import parse,encode
from .world.buffer import Reader

OPERATIONS=[('forward','MOVEFORWARD','START_FORWARD','STOP',1),
    ('backward','MOVEBACKWARD','START_BACKWARD','STOP',-1),
    ('strafe_left','STRAFELEFT','START_STRAFE_LEFT','STOP_STRAFE',1),
    ('strafe_right','STRAFERIGHT','START_STRAFE_RIGHT','STOP_STRAFE',-1),
    ('turn_left','TURNLEFT','START_TURN_LEFT','STOP_TURN',1),
    ('turn_right','TURNRIGHT','START_TURN_RIGHT','STOP_TURN',-1)]


def position(guid):
    lab.server_command('saveall');time.sleep(.5)
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT position_x,position_y,position_z,orientation,map '
            'FROM client442_characters.characters WHERE guid=%s',(guid,))
        return list(cur.fetchone())


def angle(a,b):return (b-a+math.pi)%(2*math.pi)-math.pi


def restore_party(t):
    group=native_group()
    if group is None:
        state,frame=t.observe('party_already_absent')
        if state['group']['members']:raise RuntimeError('native and visible group disagree during cleanup')
        return {'native_absent':True,'visible_solo':True,'frame':frame,'qualification':False}
    if group['members']!=[1,2] or group['leader']!=1 or group['type']!=0:
        raise RuntimeError('temporary party identity changed; refusing cleanup')
    t.clean_panels();player=next(c for c in controls(t) if c['name']=='PlayerFrame')
    open_menu(t,player,'movement_fixture_cleanup')
    require(click_case(t,'fixture.party_leave','Restore the original solo movement fixture.',
        lambda c:c['text'].lower()=='leave party',
        lambda b,a,s:{'status':'fixture_party_cleanup_pass' if s and a['group']['members']==0 and
            native_group() is None else 'client_or_protocol_failure'},
        await_state=lambda s:s['group']['members']==0),'fixture_party_cleanup_pass')
    state,frame=t.observe('party_removed')
    return {'native_absent':native_group() is None,'visible_solo':state['group']['members']==0,
        'frame':frame,'qualification':False}


def packets(since,session,guid,start,stop):
    rows=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl')
        if r.get('time',0)>=since and r.get('session')==session and
        r.get('name') in ['CMSG_MOVE_'+start,'CMSG_MOVE_'+stop,'MSG_MOVE_'+start,'MSG_MOVE_'+stop]]
    pairs=[]
    for row in rows:
        if row['direction']!='from_client':continue
        state=parse(bytes.fromhex(row['body']),guid)
        name,body=encode(row['name'],guid,state)
        matches=[r for r in rows if r['direction']=='to_native' and r['name']==name and
            r['body']==body.hex() and 0<=r['time']-row['time']<2]
        pairs.append({'modern':row,'native':matches[0] if matches else None,'movement':state})
    return pairs


def move(t,peer,session,peer_session,op,command,start,stop,sign):
    before=position(t.fixture['guid']);since=time.time();key=binding_key(t.ground_bar['keys'][command][0])
    def outcome(b,a,selected):
        time.sleep(3);after=position(t.fixture['guid'])
        deadline=time.monotonic()+12;samples=[]
        while True:
            public,frame=t.observe('ground_'+op+'_settled')
            agrees=(math.dist(after[:2],public['world_position'][:2])<.2 and
                abs(angle(after[3],frame['movement']['facing_radians']))<.05)
            samples.append({'frame':frame,'position':public['world_position'],
                'agrees':agrees,'input_replayed':False})
            if agrees or time.monotonic()>deadline:break
            time.sleep(.2)
        bar=detail(t,'ground_'+op+'_bar')
        with actor(peer.fixture['actor']):
            other,other_frame=peer.observe('peer_'+t.fixture['actor']+'_'+op)
        seen=other.get('target',{}).get('position',[])
        pair=packets(since,session,t.fixture['guid'],start,stop)
        broadcast=[]
        for r in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if (r.get('time',0)<since or r.get('session')!=peer_session or
                r.get('name')!='SMSG_MOVE_UPDATE'):continue
            if r['direction']=='to_client' and Reader(bytes.fromhex(r['body'])).guid()[0]==t.fixture['guid']:
                broadcast.append({'packet':r,'movement':parse(bytes.fromhex(r['body']),t.fixture['guid'])})
        dx,dy=after[0]-before[0],after[1]-before[1]
        projection=(dx*math.cos(before[3])+dy*math.sin(before[3])) if op in ['forward','backward'] else (
            -dx*math.sin(before[3])+dy*math.cos(before[3]))
        change=angle(before[3],after[3]);turn=op.startswith('turn_')
        checks={'observed_binding':selected=='move','native_start_stop':all(any(
            p['modern']['name']=='CMSG_MOVE_'+suffix and p['native'] for p in pair) for suffix in [start,stop]),
            'native_direction':sign*change>.2 if turn else sign*projection>1,
            'bounded_displacement':math.hypot(dx,dy)<20,
            'turn_position_preserved':math.hypot(dx,dy)<.2 if turn else True,
            'map_preserved':after[4]==before[4]==0,
            'native_public_position':math.dist(after[:2],public['world_position'][:2])<.2,
            'native_public_facing':abs(angle(after[3],frame['movement']['facing_radians']))<.05,
            'peer_position':len(seen)>=4 and math.dist(after[:2],seen[:2])<.2,
            'peer_movement_packet':bool(broadcast),
            'released_idle':bar['pose'].get('speed')==0,
            'main_bar_preserved':signature(bar)==signature(t.ground_bar),
            'ui_clean':not public.get('lua_errors') and not public.get('blocked_actions')}
        return {'status':'ground_movement_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_before':before,'native_after':after,'projection':projection,
                'facing_change':change,'public_frame':frame,'public_position':public['world_position'],
                'public_position_basis':'UnitPosition x/y, height/map fields retained without reinterpretation',
                'public_settling':samples,
                'peer_frame':other_frame,'peer_position':seen,'request_pairs':pair,'peer_packets':broadcast}}
    require(t.step('movement.'+op,'Exercise the installed ground movement binding with native and peer agreement.',
        {'move':{'kind':'key','value':key,'hold':1.2 if not op.startswith('turn_') else .6,
            'description':'Hold and release the observed '+command+' binding.'}},outcome,
        diagnostic_action='move'),'ground_movement_pass')


def suite(out,work=None,separated=False):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'schema':'client442_ground_movement_v1','started_at':time.time(),'completed':False,'failure':None}
    trials={};oracles={};baselines={};sessions={};fixture=None
    flag=lab.ROOT/'run/capture_public_movement';owns_flag=False;party_attempted=False
    try:
        if flag.exists():raise RuntimeError('another public movement capture is active')
        lab.private_write(flag,str(out)+'\n');owns_flag=True
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name,controller='code');t.clean_panels()
                state,_=t.observe('ground_fixture');t.ground_bar=detail(t,'ground_layout')
                if (state['observer_version']<75 or state.get('framerate',0)<10 or state['target'].get('exists') or
                    state['follow'].get('active') or state['group']['members'] or native_group()):
                    raise RuntimeError('requires observer75 or newer, at least10 rendered FPS, no target/follow and two solo fixtures')
                if any(not t.ground_bar['keys'].get(c) for _,c,*_ in OPERATIONS):
                    raise RuntimeError('required installed ground binding missing')
                session=sessions[name]=actors.session_entry(t.fixture)['session']
                oracle=oracles[name]=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
                baselines[name]={'resources':resources(oracle),'stats':native_state(oracle),
                    'spells':known(t.fixture['guid']),'actions':saved_actions(t.fixture['guid']),
                    'pose':pose(oracle),'afk':afk(oracle)}
                t.receipt['ground_baseline']=baselines[name];t.persist()
        # UnitPosition returned no coordinates for the visible solo target in
        # ground01. Use an ordinary temporary owned party for the peer oracle.
        report['temporary_party']={'source':'ordinary_fixture_inputs','qualification':False}
        with actor('primary'):
            # The stock autocomplete appends this observed same-realm suffix
            # after a fresh reconnect. Submit the explicit owned identity so
            # the exact pending-text guard continues to reject other changes.
            party_attempted=True;trials['primary'].execute({'kind':'chat','value':'/invite Harnesstwo-Client442Lab'})
        with actor('scout'):
            require(click_case(trials['scout'],'fixture.party_accept','Accept the owned temporary movement fixture party.',
                lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Accept',
                lambda b,a,s:{'status':'fixture_party_pass' if s and a['group']['members']==2 and
                    native_group() and native_group()['members']==[1,2] else 'client_or_protocol_failure'},
                await_state=lambda s:s['group']['members']==2),
                'fixture_party_pass')
        fixture=NearbyFixture(out,trials['primary'].fixture,trials['scout'].fixture,
            open_ground=True,separated=separated);fixture.prepare()
        for name,peer_name in [('primary','scout'),('scout','primary')]:
            with actor(peer_name):
                trials[peer_name].execute({'kind':'chat','value':'/targetexact '+trials[name].fixture['character_name']})
                state,_=trials[peer_name].observe('peer_target_'+name)
                if state['target'].get('guid')!=trials[name].guid:raise RuntimeError('owned peer target missing')
            with actor(name):
                t=trials[name]
                # Setup-only wake-up; these inputs receive no movement qualification.
                if afk(oracles[name]):t.execute({'kind':'chat','value':'/afk'})
                if pose(oracles[name])['stand']==1:
                    t.execute({'kind':'key','value':binding_key(t.ground_bar['keys']['SITORSTAND'][0]),'hold':.4})
                time.sleep(3)
                if work:work(t,trials[peer_name],oracles[name],sessions[name],sessions[peer_name])
                else:
                    for op,command,start,stop,sign in OPERATIONS:
                        move(t,trials[peer_name],sessions[name],sessions[peer_name],op,command,start,stop,sign)
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        if fixture:
            try:fixture.restore()
            except Exception as error:report.update(completed=False);report.setdefault('cleanup_failures',{})['positions']=str(error)
        if party_attempted:
            try:
                with actor('primary'):
                    report['temporary_party']['restoration']=restore_party(trials['primary'])
            except Exception as error:
                report['completed']=False;report.setdefault('cleanup_failures',{})['party']=str(error)
        for name,t in trials.items():
            with actor(name):
                if name not in baselines:
                    t.receipt['ground_restoration']={'skipped':True,'qualification':False,
                        'reason':'Preflight failed before native baseline capture or fixture staging.'}
                    t.receipt.update(completed=False,failure=report['failure'],finished_at=time.time());t.persist()
                    continue
                try:
                    t.clean_panels();state,_=t.observe('ground_cleanup_target')
                    if state['target'].get('exists'):t.execute({'kind':'key','value':'Escape','hold':.4})
                    baseline=baselines[name];oracle=oracles[name]
                    if afk(oracle)!=baseline['afk']:t.execute({'kind':'chat','value':'/afk'})
                    if pose(oracle)['stand']!=baseline['pose']['stand']:
                        t.execute({'kind':'key','value':binding_key(t.ground_bar['keys']['SITORSTAND'][0]),'hold':.4})
                    time.sleep(12);state,frame=t.observe('ground_restored');bar=detail(t,'ground_bar_restored')
                    checks={'resources':resources(oracle)==baseline['resources'],
                        'stats':restored_native_state(baseline['stats'],native_state(oracle)),
                        'spells':known(t.fixture['guid'])==baseline['spells'],
                        'actions':saved_actions(t.fixture['guid'])==baseline['actions'],
                        'pose':pose(oracle)==baseline['pose'],'afk':afk(oracle)==baseline['afk'],
                        'main_bar':signature(bar)==signature(t.ground_bar),
                        'target_cleared':not state['target'].get('exists'),
                        'solo_group_restored':state['group']['members']==0,
                        'idle':bar['pose'].get('speed')==0}
                    t.receipt['ground_restoration']={'checks':checks,'frame':frame}
                    if not all(checks.values()):raise RuntimeError('native/public ground fixture restoration differs')
                except Exception as error:
                    report['completed']=False;report.setdefault('cleanup_failures',{})[name]=str(error)
                t.receipt.update(completed=report['completed'],failure=report['failure'],finished_at=time.time());t.persist()
        # A later actor's cleanup failure invalidates the shared cohort too.
        for t in trials.values():t.receipt['completed']=report['completed'];t.persist()
        if owns_flag and flag.exists() and flag.read_text()==str(out)+'\n':flag.unlink()
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output)
