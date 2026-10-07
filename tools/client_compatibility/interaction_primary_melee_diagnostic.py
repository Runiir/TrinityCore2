"""One reviewed original-primary melee attempt with native/public damage evidence."""
import argparse,copy,json,math,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import saved,pets,character,SCRIPT_BOUNDARY
from .interaction_primary_combat_reentry import inventory,protected_snapshot
from .interaction_ground_movement import position
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed
from .interaction_observation import read_page
from .interaction_operations import command
from .interaction_macros import require
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import pair
from .world.native_objects import records
from .world.objects import INDEX
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .melee_health_fixture import native_target
from .primary_melee_fixture import PrimaryMeleeFixture
from .pet_attack_capture_evidence import target_guid
from .melee_result_evidence import pairs,health_checks,public_events
from .pet_attack_evidence import combat_pairs

NAMES={'CMSG_ATTACK_SWING','CMSG_ATTACK_STOP','SMSG_ATTACK_START','SMSG_ATTACK_STOP',
    'SMSG_ATTACKER_STATE_UPDATE','SMSG_ATTACK_SWING_ERROR','SMSG_ATTACKSWING_NOTINRANGE',
    'SMSG_ATTACKSWING_BADFACING','SMSG_ATTACKSWING_DEADTARGET','SMSG_ATTACKSWING_CANT_ATTACK','CMSG_CAST_SPELL'}


class PrimaryPresence(Presence):
    def __init__(self,*args):super().__init__(*args);self.target=None;self.combat=[]

    def inspect_packet(self,p):
        if p.get('name') in NAMES:
            if len(self.combat)>=256:raise RuntimeError('primary repeated combat packet limit reached')
            self.combat.append(p)
        if p.get('name')!='SMSG_UPDATE_OBJECT' or p.get('direction')!='from_native':return
        for r in records(bytes.fromhex(p['body'])):
            if native_target(r):
                if self.target and r['guid']!=self.target['guid']:raise RuntimeError('ambiguous primary ground target')
                self.target=r
            elif self.target and r.get('guid')==self.target['guid']:self.target['fields'].update(r.get('fields',{}))


def health(o):return o.target['fields'][INDEX['UNIT_FIELD_HEALTH']]


def source(t,path,phase):
    d=closed(path)
    if (t.fixture['actor'],t.fixture['guid'],t.fixture['character_name'],t.fixture['level'])!=('primary',1,'Harnessone',85):
        raise RuntimeError('requires original primary')
    if d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or d.get('phase')!=phase:
        raise RuntimeError('closed primary source identity differs')
    if d.get('session')!=actors.session_entry(t.fixture)['session']:raise RuntimeError('primary login epoch changed')
    t.receipt['source']={'path':str(path.resolve()),'sha256':lab.sha256(path)};t.persist();return d


def stage(t,path):
    e=source(t,path,'owned_primary_combat_preparation')
    if len(e.get('reentry_checks',{}))!=15 or not all(e['reentry_checks'].values()):raise RuntimeError('primary entry guards incomplete')
    state,frame=t.observe('primary_before_staging');t.clean_panels()
    if state['target'].get('exists') or state['owner_melee']['active']:raise RuntimeError('primary must have idle empty selection')
    base={'saved':saved(1),'pets':pets(1),'inventory':inventory(1),'money':character(1,t.fixture['account_id'])['money'],
        'position':position(1),'protected':protected_snapshot()}
    if base['saved']!=e['offline_source']['saved'] or base['protected']!=e['protected_baseline']:
        raise RuntimeError('primary saved or protected source changed')
    fixture=PrimaryMeleeFixture(t.out);o=PrimaryPresence(e['session'],1,e['started_at']).poll()
    t.receipt.update(baseline=base,session=e['session'],entry_started_at=e['started_at'],qualification_added=False);t.persist()
    try:
        landing=fixture.prepare();t.execute({'kind':'chat','value':'/targetexact Sheep'})
        state,_=t.observe('primary_selected_ground_target');o.poll();pose=position(1);time.sleep(.5)
        checks={'exact_native_target':native_target(o.target),'selected_native':bool(o.target and pair(o.player,'UNIT_FIELD_TARGET')==o.target['guid']),
            'selected_public':bool(o.target and state['target'].get('guid')==target_guid(o.target)),
            'undamaged_target':bool(o.target and health(o)==o.target['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]>0),
            'public_health':bool(o.target and state['target'].get('health')==health(o)),
            'melee_range':bool(o.target and math.dist(pose[:3],o.target['movement']['position'][:3])<4),
            'facing':abs(pose[3])<.01,'pose_stable':pose==landing==position(1),
            'saved':saved(1)==base['saved'],'inventory':inventory(1)==base['inventory'],'pets':pets(1)==base['pets'],
            'protected':protected_snapshot()==base['protected'],'idle':not state['owner_melee']['active'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(checks=checks,target=copy.deepcopy(o.target),staged_position=pose,
            fixture={'path':str(t.out/'primary_melee_fixture.json'),'sha256':lab.sha256(t.out/'primary_melee_fixture.json')},
            frame=shot(t.out/'review_ready.png'),phase='await_primary_melee_review')
        t.persist()
        if not all(checks.values()):raise RuntimeError('primary ground staging differs')
        t.receipt['completed']=True
    except Exception:
        cleanup(t,o,fixture,base);raise


def review(t,path,d,stage_path):
    if path.is_symlink() or not path.resolve().is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned primary review')
    r=json.loads(path.read_text());f=r.get('frame',{});image=path.parent/f.get('file','');m=f.get('monitor',{})
    focus=owned_input.focus()
    if (r.get('reviewed') is not True or r.get('source',{}).get('sha256')!=lab.sha256(stage_path) or
        r['source'].get('path')!=str(stage_path.resolve()) or f!=d['frame'] or r.get('control')!='primary_ground_melee' or
        r.get('target_visible') is not True or not image.resolve().is_relative_to(lab.ROOT/'evidence') or
        not image.is_file() or lab.sha256(image)!=f.get('sha256') or not 0<=time.time()-image.stat().st_mtime<110 or
        not m.get('second_monitor_verified') or m.get('pid')!=t.receipt['runtime']['client']['pid'] or
        m.get('input_isolation',{}).get('actor')!='primary' or
        m.get('input_isolation',{}).get('game_pid')!=focus['input_isolation']['game_pid']):
        raise RuntimeError('fresh reviewed primary target differs')
    t.receipt['review']={'path':str(path),'sha256':lab.sha256(path),'frame':f};t.persist()
    return image


def cleanup(t,o,fixture,base):
    with t.bounded_combat_observation(60):
        t.execute({'kind':'chat','value':'/stopattack'});t.execute({'kind':'chat','value':'/cleartarget'})
        restored=fixture.restore();t.clean_panels();state,frame=t.observe('primary_pose_restored');o.poll()
    checks={'saved_user_pose':position(1)==base['position'],'saved_rows':saved(1)==base['saved'],
        'inventory':inventory(1)==base['inventory'],'retained_pets':pets(1)==base['pets'],
        'money':character(1,t.fixture['account_id'])['money']==base['money'],
        'protected_actors':protected_snapshot()==base['protected'],'native_selection_clear':pair(o.player,'UNIT_FIELD_TARGET')==0,
        'public_selection_clear':not state['target'].get('exists'),'melee_stopped':not state['owner_melee']['active'],
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(restoration_checks=checks,restored_frame=frame,pose_restoration=restored);t.persist()
    if not all(checks.values()):raise RuntimeError('primary combat restoration differs')


def run(t,path,review_path):
    d=source(t,path,'await_primary_melee_review')
    if len(d.get('checks',{}))!=14 or not all(d['checks'].values()):raise RuntimeError('primary staging guards incomplete')
    fixture=PrimaryMeleeFixture.resume(t.out,Path(d['fixture']['path']))
    o=PrimaryPresence(d['session'],1,d['entry_started_at']).poll();base=d['baseline'];target=d['target']
    t.receipt.update(baseline=base,session=d['session'],qualification_added=False);t.persist()
    try:
        image=review(t,review_path,d,path)
        if (lab.sha256(Path(d['fixture']['path']))!=d['fixture']['sha256'] or position(1)!=d['staged_position'] or
            protected_snapshot()!=base['protected'] or not o.target or o.target['guid']!=target['guid'] or
            health(o)!=target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])] or pair(o.player,'UNIT_FIELD_TARGET')!=target['guid']):
            raise RuntimeError('primary target changed before attempt')
        public,_=read_page(t,'primary_before_swings','combat_log','/tcui combat_log')
        sequence=public.get('sequence',0);command(t,'/tcui state');since=None
        def admit():
            nonlocal since
            accepted=0<=time.time()-image.stat().st_mtime<110 and lab.sha256(image)==d['frame']['sha256']
            if accepted:since=time.time()
            return {'accepted':accepted,'frame':d['frame'],'checked_at':time.time()}
        with t.bounded_combat_observation(60):
            def outcome(b,a,s):
                o.poll();passed=health(o)<target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]
                t.receipt['first_health']={'time':time.time(),'native':copy.deepcopy(o.target),'public':a['target']};t.persist()
                return {'status':'primary_damage_pass' if passed else 'client_or_protocol_failure','oracle':{'native_health_loss':passed}}
            require(t.step('diagnostic.primary.melee','Apply one ordinary melee attempt to the reviewed in-range ground target.',
                {'attack':{'kind':'chat','value':'/startattack'}},outcome,diagnostic_action='attack',before_input=admit),'primary_damage_pass')
            t.execute({'kind':'chat','value':'/stopattack'})
            public,frame=read_page(t,'primary_after_swings','combat_log','/tcui combat_log')
            command(t,'/tcui state');state,_=t.observe('primary_damage_outcome');o.poll()
        packets=[p for p in o.combat if p['time']>=since];hits,foreign=pairs(packets,1,target['guid'],0)
        events=public_events(public,sequence,hits,t.guid,target_guid(target))
        checks=health_checks(target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])],health(o),hits,state['target'].get('health'),foreign,
            allow_death=True,public_death=state['target'].get('exists') is False)
        starts=combat_pairs(packets,d['session'],since,time.time(),{'guid':1,'map':0},target,'SMSG_ATTACK_START')
        requests=[p for p in packets if p['name']=='CMSG_ATTACK_SWING']
        modern=[p for p in requests if p['direction']=='from_client'];native=[p for p in requests if p['direction']=='to_native']
        submitted=None
        if len(modern)==1:
            r=Reader(bytes.fromhex(modern[0]['body']));submitted=r.guid();r.end()
        checks.update(one_exact_attack=bool(len(modern)==len(native)==1 and submitted==modern_guid(target['guid'],0) and
            native[0]['body']==struct.pack('<Q',target['guid']).hex()),
            native_public_start=bool(starts and all(p['client'] for p in starts)),public_swing_event=bool(events),
            no_range_facing_error=not any(p['name'] in NAMES and ('ATTACKSWING_' in p['name'] or p['name']=='SMSG_ATTACK_SWING_ERROR') for p in packets),
            no_native_spell_cast=not any(p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native' for p in packets),
            melee_stopped=not state['owner_melee']['active'])
        t.receipt.update(combat_checks=checks,packets=packets,hits=hits,events=events,public=public,frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('primary native/public damage proof differs')
        t.receipt.update(completed=True,phase='primary_melee_damage_verified')
    finally:cleanup(t,o,fixture,base)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','run','cleanup'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action=='run' and not a.review:p.error('run requires a separately reviewed fresh target')
    with actor('primary'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='stage':stage(t,a.source)
            elif a.action=='run':run(t,a.source,a.review)
            else:
                d=source(t,a.source,'await_primary_melee_review');o=PrimaryPresence(d['session'],1,d['entry_started_at']).poll()
                cleanup(t,o,PrimaryMeleeFixture.resume(t.out,Path(d['fixture']['path'])),d['baseline']);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}';t.receipt['completed']=False
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','checks','combat_checks','restoration_checks')}),flush=True)
