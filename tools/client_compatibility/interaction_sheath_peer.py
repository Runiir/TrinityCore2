"""Observe weapon cycles immediately and after settling, on owner and peer clients."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import binding_key
from .interaction_bridge_deploy import shot
from .interaction_ground_movement import suite
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sheath import cycle
from .interaction_sit_stand import pose
from .observation.journal import entries
from .world.native_objects import records
from .world.objects import INDEX


def toggle(t,peer,oracle,session,peer_session,wanted,key,label,baseline):
    before,frame=t.observe(label+'_before')
    row={'id':label,'goal':'Observe the installed sheath binding on owner and peer.',
        'time':time.time(),'status':'started','before':before,'before_frame':frame,
        'selected':'sheath','selection_source':'code','request':None,'response':None,
        'input':{'kind':'key','value':key,'hold':.4,'description':'Press the observed sheath binding once.'},
        'visual_qualification_pending':True}
    t.receipt['cases'].append(row);t.persist();since=time.time()
    try:
        # Capture the first rendered result before diagnostic-page readiness
        # waits. The owned adapter verifies HDMI-1 and releases the held key.
        t.io.key(key,hold=.4);row['input_transport']=[];row['released_at']=time.time();t.persist()
        row['scene_frames']=[]
        for stage,delay in [('early',0),('settled',8)]:
            time.sleep(delay)
            for client in [t,peer]:
                with actor(client.fixture['actor']):
                    path=client.out/(t.fixture['actor']+'_'+label+'_'+stage+'.png')
                    row['scene_frames'].append({'actor':client.fixture['actor'],
                        'stage':stage,'seconds_since_release':time.time()-row['released_at'],
                        **shot(path),'file':str(path)})
            t.persist()
        public=detail(t,label+'_value',lambda p:pose(oracle)['sheath']==wanted and
            p['pose'].get('sheath')==wanted+1)
        after,after_frame=t.observe(label+'_after')
        with actor(peer.fixture['actor']):other,peer_frame=peer.observe('peer_'+t.fixture['actor']+'_'+label)
        requests=[];updates=[]
        for packet in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if packet.get('time',0)<since or packet.get('session') not in [session,peer_session]:continue
            if packet.get('name')=='CMSG_SET_SHEATHED' and packet.get('session')==session:
                requests.append({k:packet[k] for k in ['time','direction','name','body']})
            if packet.get('name')!='SMSG_UPDATE_OBJECT' or packet.get('direction')!='from_native':continue
            for obj in records(bytes.fromhex(packet['body'])):
                value=obj.get('fields',{}).get(INDEX['UNIT_FIELD_BYTES_2'])
                if obj.get('guid')==t.fixture['guid'] and value is not None:
                    updates.append({'time':packet['time'],'session':packet['session'],
                        'native_sheath':value&255,'native_bytes2':value})
        native=pose(oracle)
        checks={'modern_request':any(p['direction']=='from_client' and p['body'] in
            [(wanted.to_bytes(4,'little')+bytes([a])).hex() for a in [0,128]] for p in requests),
            'native_request':any(p['direction']=='to_native' and
                p['body']==wanted.to_bytes(4,'little').hex() for p in requests),
            'native_owner_state':native['sheath']==wanted,
            'native_peer_update':any(p['session']==peer_session and p['native_sheath']==wanted for p in updates),
            'public_owner_state':public['pose'].get('sheath')==wanted+1,
            'stand_unchanged':native['stand']==baseline['stand'],
            'idle':public['pose'].get('speed')==0,
            'main_bar':signature(public)==signature(t.ground_bar),
            'position':before['world_position']==after['world_position'],
            'peer_target':other.get('target',{}).get('guid')==t.guid,
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions') and
                not other.get('lua_errors') and not other.get('blocked_actions')}
        row.update(after=after,after_frame=after_frame,peer_frame=peer_frame,
            oracle={'checks':checks,'native_pose':native,'public':public,
                'requests':requests,'native_updates':updates},
            status='native_sheath_peer_probe_pass' if all(checks.values()) else 'client_or_protocol_failure')
        if not all(checks.values()):raise RuntimeError('sheath peer probe checks differ')
    except Exception as error:
        row.update(status='infrastructure_failure' if row['status']=='started' else row['status'],
            error=f'{type(error).__name__}: {error}');raise
    finally:row['finished_at']=time.time();t.persist()


def phase(t,peer,oracle,session,peer_session):
    baseline=pose(oracle);bar=detail(t,'sheath_peer_phase');keys=bar['keys'].get('TOGGLESHEATH')
    if not keys:raise RuntimeError('owned sheath binding is absent')
    key=binding_key(keys[0]);ranged=bool(oracle.equipment(18)['id'])
    t.receipt.update(observed_weapon_cycle=cycle(baseline['sheath'],ranged),
        sheath_phase_baseline=baseline,observed_sheath_binding=keys,
        qualified_scope='Native sheath cycles with early and settled owner/peer screenshots. Native/public values and peer updates are probes; exact rendered weapons require separate visual review. Temporary staging and party are fixture-only.');t.persist()
    try:
        for wanted in cycle(baseline['sheath'],ranged):
            toggle(t,peer,oracle,session,peer_session,wanted,key,'movement.sheath_state_'+str(wanted),baseline)
    finally:
        if pose(oracle)['sheath']!=baseline['sheath']:
            for wanted in cycle(pose(oracle)['sheath'],ranged):
                toggle(t,peer,oracle,session,peer_session,wanted,key,'fixture.sheath_cleanup_'+str(wanted),baseline)
                if wanted==baseline['sheath']:break


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
