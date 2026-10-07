"""Check native melee-range feedback on the user's saved primary pose."""
import argparse,copy,json,math,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_retained_class_fixture import closed
from .interaction_primary_combat_reentry import inventory,protected_snapshot
from .interaction_primary_melee_diagnostic import review,NAMES
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_ground_movement import position
from .interaction_bridge_deploy import shot
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import pair
from .world.native_objects import records
from .world.objects import INDEX
from .world.gameobjects import modern_guid
from .world.buffer import Reader
from .interaction_macros import require

# The diagnostic strip obscures the caption prefix. The actual owned native
# query reply and template2830 both establish this full name.
PUBLIC_NAME='Parched Buzzard'


def stock_range_error(value):
    return value.get('code')==265 and value.get('text')=='You are too far away!'


class RangePresence(Presence):
    def __init__(self,*args):super().__init__(*args);self.targets={};self.combat=[]

    def inspect_packet(self,p):
        if p.get('name') in NAMES:
            if len(self.combat)>=256:raise RuntimeError('range repeated packet limit reached')
            self.combat.append(p)
        if p.get('name')!='SMSG_UPDATE_OBJECT' or p.get('direction')!='from_native':return
        for r in records(bytes.fromhex(p['body'])):
            if r.get('kind')==3 and r['guid']>>52==0xf13 and r['guid']>>32&0xfffff==2830:
                self.targets[r['guid']]={**r,'created_at':p['time']}
                self.removed.discard(r['guid'])
            elif r.get('guid') in self.targets:
                self.targets[r['guid']]['fields'].update(r.get('fields',{}))
                if r.get('movement'):self.targets[r['guid']]['movement']=r['movement']

    def target(self):return self.targets.get(pair(self.player,'UNIT_FIELD_TARGET'))


def static_position(target):
    if not target:return None
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.phaseMask,c.MovementType,c.position_x,c.position_y,c.position_z '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'WHERE c.id=2830 AND c.map=0 AND ABS(c.position_x-%s)<.01 AND ABS(c.position_y-%s)<.01 '
            'AND ABS(c.position_z-%s)<.01',target['movement']['position'][:3])
        rows=q.fetchall()
    return list(rows[0]) if len(rows)==1 and rows[0][1:6]==(2830,PUBLIC_NAME,0,1,0) else None


def source(t,path,phase,entry_path=None):
    d=closed(path)
    if (t.fixture['actor'],t.fixture['guid'],t.fixture['character_name'],t.fixture['level'])!=('primary',1,'Harnessone',85):
        raise RuntimeError('requires original owned primary')
    if d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or d.get('phase')!=phase:
        raise RuntimeError('closed primary source or login epoch differs')
    current=actors.session_entry(t.fixture)['session']
    if entry_path:
        e=closed(entry_path);base=d['baseline']
        if (e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or
            e.get('phase')!='owned_primary_combat_preparation' or e.get('session')!=current or e['started_at']<=d['finished_at'] or
            len(e.get('reentry_checks',{}))!=15 or not all(e['reentry_checks'].values()) or
            e['offline_source']['saved']!=base['saved'] or e['offline_source']['inventory']!=base['inventory'] or
            e['offline_source']['pets']!=base['pets'] or e['protected_baseline']!=base['protected'] or
            position(1)!=base['position']):raise RuntimeError('fresh preserved primary reentry differs')
        t.receipt['reentry_source']={'path':str(entry_path.resolve()),'sha256':lab.sha256(entry_path)}
    elif d.get('session')!=current:raise RuntimeError('closed primary login epoch differs')
    t.receipt['source']={'path':str(path.resolve()),'sha256':lab.sha256(path)};t.persist();return d


def restore(t,o,base):
    with t.bounded_combat_observation(60):
        t.execute({'kind':'chat','value':'/stopattack'});t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels();state,frame=t.observe('range_restored');o.poll()
    checks={'saved_user_pose':position(1)==base['position'],'saved_rows':saved(1)==base['saved'],
        'inventory':inventory(1)==base['inventory'],'pets':pets(1)==base['pets'],
        'money':character(1,t.fixture['account_id'])['money']==base['money'],
        'protected':protected_snapshot()==base['protected'],'native_clear':pair(o.player,'UNIT_FIELD_TARGET')==0,
        'public_clear':not state['target'].get('exists'),'melee_stopped':not state['owner_melee']['active'],
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('range diagnostic restoration differs')


def capture(t,path):
    d=source(t,path,'primary_melee_damage_verified');base=d['baseline']
    state,frame=t.observe('range_selection_scene')
    if position(1)!=base['position'] or protected_snapshot()!=base['protected'] or state['target'].get('exists') or state['owner_melee']['active']:
        raise RuntimeError('primary range selection preflight differs')
    t.receipt.update(baseline=base,session=d['session'],frame=frame,completed=True,
        phase='await_primary_range_selection',input_sent=False,qualification_added=False)


def stage(t,path,selection_review,name_authority=None,entry_path=None):
    d=source(t,path,'primary_melee_damage_verified',entry_path)
    if len(d.get('combat_checks',{}))!=13 or not all(d['combat_checks'].values()) or len(d.get('restoration_checks',{}))!=10 or not all(d['restoration_checks'].values()):
        raise RuntimeError('primary melee whole result is incomplete')
    base=d['baseline'];entry=closed(entry_path or Path(d['source']['path']))
    session=actors.session_entry(t.fixture)['session'];started=entry['started_at'] if entry_path else entry['entry_started_at']
    if protected_snapshot()!=base['protected'] or position(1)!=base['position']:raise RuntimeError('primary source pose changed')
    o=RangePresence(session,1,started).poll()
    t.receipt.update(baseline=base,session=session,entry_started_at=started,qualification_added=False);t.persist()
    try:
        if name_authority:
            if name_authority.is_symlink() or not name_authority.resolve().is_relative_to(lab.ROOT/'evidence'):
                raise RuntimeError('name authority is outside the owned evidence')
            a=json.loads(name_authority.read_text())
            native=[p for p in a.get('packets',[]) if p.get('session')==session and p.get('direction')=='from_native' and
                p.get('name')=='SMSG_CREATURE_QUERY_RESPONSE' and bytes.fromhex(p['body']).startswith(struct.pack('<I',2830)+PUBLIC_NAME.encode()+b'\0')]
            with lab.connection() as con,con.cursor() as q:
                q.execute('SELECT entry,name,unit_flags,unit_flags2,flags_extra,scale,modelid1 '
                    'FROM client442_world.creature_template WHERE entry=2830');template=list(q.fetchone() or ())
            if not native and (a.get('native_template')!=template or template!=[2830,PUBLIC_NAME,0,2048,0,1.0,1105] or a.get('session')!=session):
                raise RuntimeError('exact current native Buzzard name authority is absent')
            t.receipt['name_authority']={'path':str(name_authority),'sha256':lab.sha256(name_authority)};t.persist()
            t.execute({'kind':'chat','value':'/targetexact '+PUBLIC_NAME})
        else:
            r=json.loads(selection_review.read_text());capture_path=Path(r['source']['path']);c=closed(capture_path)
            if c.get('phase')!='await_primary_range_selection' or c.get('actor')!=t.fixture or c.get('runtime')!=t.receipt['runtime'] or c.get('baseline')!=base or c.get('source',{}).get('sha256')!=lab.sha256(path):
                raise RuntimeError('range selection capture is not bound to this primary result')
            review(t,selection_review,c,capture_path,'primary_range_target_selection')
            point=r.get('point',[])
            if len(point)!=2 or any(type(v) is not int for v in point) or not (200<=point[0]<1000 and 100<=point[1]<500):
                raise RuntimeError('reviewed ordinary target point is outside the world viewport')
            t.io.click(*point,button=1,hold=1.2);time.sleep(1.5)
        state,_=t.observe('range_selected_buzzard');o.poll();target=o.target()
        distance=math.dist(base['position'][:3],target['movement']['position'][:3]) if target else 0
        fixed=static_position(target)
        # Use the same pinned public native-GUID conversion as the melee oracle.
        from .pet_attack_capture_evidence import target_guid
        checks={'selected_native':bool(target and target['guid'] not in o.removed),'selected_public':bool(target and state['target'].get('guid')==target_guid(target)),
            'public_name':state['target'].get('name')==PUBLIC_NAME,'native_alive':bool(target and target['fields'][INDEX['UNIT_FIELD_HEALTH']]>0),
            'public_health':bool(target and state['target'].get('health')==target['fields'][INDEX['UNIT_FIELD_HEALTH']]),
            'outside_melee_reach':12<distance<40,'static_native_position':bool(fixed),
            'unchanged_user_pose':position(1)==base['position'],'protected':protected_snapshot()==base['protected'],
            'saved':saved(1)==base['saved'],'inventory':inventory(1)==base['inventory'],'idle':not state['owner_melee']['active'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(checks=checks,target=copy.deepcopy(target),static_position_authority=fixed,
            distance_metres=distance,frame=shot(t.out/'review_ready.png'),
            phase='await_primary_range_review');t.persist()
        if not all(checks.values()):raise RuntimeError('current selected out-of-range Buzzard differs')
        t.receipt['completed']=True
    except Exception:restore(t,o,base);raise


def run(t,path,review_path):
    d=source(t,path,'await_primary_range_review')
    if len(d.get('checks',{}))!=13 or not all(d['checks'].values()):raise RuntimeError('range staging guards incomplete')
    o=RangePresence(d['session'],1,d['entry_started_at']).poll();base=d['baseline'];target=d['target']
    t.receipt.update(baseline=base,session=d['session'],qualification_added=False);t.persist()
    try:
        image=review(t,review_path,d,path,'primary_range_error')
        if position(1)!=base['position'] or not o.target() or o.target()['guid']!=target['guid'] or protected_snapshot()!=base['protected'] or static_position(o.target())!=d['static_position_authority']:
            raise RuntimeError('reviewed range target or primary pose changed')
        before,_=t.observe('range_fresh_error_baseline')
        if any(stock_range_error(v) for v in before.get('errors',[])):
            raise RuntimeError('requires an ordinary reload to clear prior passive range history')
        since=None
        def admit():
            nonlocal since
            accepted=0<=time.time()-image.stat().st_mtime<110 and lab.sha256(image)==d['frame']['sha256']
            if accepted:since=time.time()
            return {'accepted':accepted,'frame':d['frame'],'checked_at':time.time()}
        with t.bounded_combat_observation(60):
            def outcome(b,a,s):
                o.poll();native=[p for p in o.combat if p['time']>=since and p['name']=='SMSG_ATTACKSWING_NOTINRANGE' and p['direction']=='from_native']
                client=[p for p in o.combat if p['time']>=since and p['name']=='SMSG_ATTACK_SWING_ERROR' and p['direction']=='to_client' and p['body']=='00']
                delivered=[{'native':n,'client':next((c for c in client if 0<=c['time']-n['time']<2),None)} for n in native]
                stock=[v for v in a.get('errors',[]) if stock_range_error(v) and v not in b.get('errors',[])]
                t.receipt.update(error_pairs=delivered,public_errors=stock,range_outcome_frame=t.receipt['cases'][-1].get('after_frame'));t.persist()
                passed=bool(delivered and all(p['client'] for p in delivered) and stock)
                return {'status':'primary_range_feedback_pass' if passed else 'client_or_protocol_failure','oracle':{'native_client_stock_range_feedback':passed}}
            require(t.step('diagnostic.primary.range','Attempt melee once on the reviewed distant Buzzard to inspect range feedback.',
                {'attack':{'kind':'chat','value':'/startattack'}},outcome,diagnostic_action='attack',before_input=admit,
                await_state=lambda a:any(stock_range_error(v) for v in a.get('errors',[]))),'primary_range_feedback_pass')
            t.execute({'kind':'chat','value':'/stopattack'});state,frame=t.observe('range_stopped');o.poll()
        packets=[p for p in o.combat if p['time']>=since];requests=[p for p in packets if p['name']=='CMSG_ATTACK_SWING']
        modern=[p for p in requests if p['direction']=='from_client'];native=[p for p in requests if p['direction']=='to_native'];identity=None
        if len(modern)==1:r=Reader(bytes.fromhex(modern[0]['body']));identity=r.guid();r.end()
        checks={'one_exact_attack':len(modern)==len(native)==1 and identity==modern_guid(target['guid'],0) and native[0]['body']==struct.pack('<Q',target['guid']).hex(),
            'native_range_rejection':bool(t.receipt['error_pairs']),'delivered_range_error':all(p['client'] for p in t.receipt['error_pairs']),
            'stock_range_feedback':bool(t.receipt['public_errors']),
            'no_melee_damage':not any(p['name']=='SMSG_ATTACKER_STATE_UPDATE' for p in packets),
            'unchanged_target_health':o.targets[target['guid']]['fields'][INDEX['UNIT_FIELD_HEALTH']]==target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])],
            'no_native_spell':not any(p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native' for p in packets),
            'user_pose':position(1)==base['position'],'public_melee_stopped':not state['owner_melee']['active'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(range_checks=checks,packets=packets,frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('range feedback whole result differs')
        t.receipt.update(completed=True,phase='primary_range_feedback_verified')
    finally:restore(t,o,base)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['capture','stage','run'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path);p.add_argument('--name-authority',type=Path);p.add_argument('--entry',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.action=='run' and not a.review:p.error('run requires separately reviewed target')
    if a.action=='stage' and not (a.review or a.name_authority):p.error('stage requires reviewed selection or exact native name authority')
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='capture':capture(t,a.source)
            elif a.action=='stage':stage(t,a.source,a.review,a.name_authority,a.entry)
            else:run(t,a.source,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','checks','range_checks','restoration_checks')}),flush=True)
