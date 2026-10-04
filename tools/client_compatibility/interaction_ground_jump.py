"""One flat-ground jump with early scene capture and native jump/landing proof."""
import argparse,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import binding_key
from .interaction_bridge_deploy import shot
from .interaction_ground_movement import suite,packets,position
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sit_stand import pose
from .observation.journal import entries
from .world.movement import parse
from .world.buffer import Reader


def phase(t,peer,oracle,session,peer_session):
    before,frame=t.observe('jump_before');native_before=position(t.fixture['guid']);baseline=pose(oracle)
    keys=t.ground_bar['keys'].get('JUMP')
    if not keys or before.get('framerate',0)<10 or baseline['stand']!=0:
        raise RuntimeError('flat jump requires an observed binding, standing pose and at least10 rendered FPS')
    key=binding_key(keys[0]);since=time.time()
    row={'id':'movement.jump','goal':'Jump once on the owned flat-ground fixture.',
        'time':since,'status':'started','before':before,'before_frame':frame,'selected':'jump',
        'selection_source':'code','request':None,'response':None,
        'input':{'kind':'key','value':key,'hold':.25},'visual_qualification_pending':True}
    t.receipt['cases'].append(row);t.persist()
    try:
        t.io.key(key,hold=.25);row['input_transport']=[];row['scene_frames']=[];t.persist()
        for client in [t,peer]:
            with actor(client.fixture['actor']):
                path=client.out/(t.fixture['actor']+'_jump_early.png')
                row['scene_frames'].append({'actor':client.fixture['actor'],'requested_at':time.time(),
                    **shot(path),'file':str(path)})
        time.sleep(2);after,after_frame=t.observe('jump_landed');bar=detail(t,'jump_value')
        native_after=position(t.fixture['guid']);pair=packets(since,session,t.fixture['guid'],'JUMP','FALL_LAND')
        with actor(peer.fixture['actor']):other,peer_frame=peer.observe('peer_'+t.fixture['actor']+'_jump_landed')
        broadcasts=[]
        for packet in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if packet.get('time',0)<since or packet.get('session')!=peer_session or packet.get('name')!='SMSG_MOVE_UPDATE' or packet.get('direction')!='to_client':continue
            body=bytes.fromhex(packet['body'])
            if Reader(body).guid()[0]==t.fixture['guid']:
                broadcasts.append({'time':packet['time'],'movement':parse(body,t.fixture['guid'])})
        jumps=[p for p in pair if p['modern']['name']=='CMSG_MOVE_JUMP']
        lands=[p for p in pair if p['modern']['name']=='CMSG_MOVE_FALL_LAND']
        checks={'observed_binding':key==binding_key(keys[0]),
            'native_jump_land':bool(jumps) and bool(lands) and all(p['native'] for p in pair),
            'jump_fall_state':bool(jumps) and all(p['movement']['fall'] and p['movement']['zspeed']>0 for p in jumps),
            'landing_idle':bool(lands) and lands[-1]['movement']['flags']==0,
            'peer_fall':any(p['movement']['fall'] for p in broadcasts),
            'peer_landing':bool(broadcasts) and broadcasts[-1]['movement']['flags']==0,
            'flat_position':all(abs(a-b)<.3 for a,b in zip(native_before,native_after)),
            'public_position':before['world_position']==after['world_position'],
            'pose_unchanged':pose(oracle)==baseline,'idle':bar['pose'].get('speed')==0,
            'main_bar':signature(bar)==signature(t.ground_bar),
            'peer_target':other.get('target',{}).get('guid')==t.guid,
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
        row.update(after=after,after_frame=after_frame,peer_frame=peer_frame,
            oracle={'checks':checks,'native_before':native_before,'native_after':native_after,
                'request_pairs':pair,'peer_packets':broadcasts,'public':bar},
            status='native_jump_probe_pass' if all(checks.values()) else 'client_or_protocol_failure')
        if not all(checks.values()):raise RuntimeError('flat-ground jump checks differ')
    except Exception as error:
        row.update(status='infrastructure_failure' if row['status']=='started' else row['status'],
            error=f'{type(error).__name__}: {error}');raise
    finally:row['finished_at']=time.time();t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
