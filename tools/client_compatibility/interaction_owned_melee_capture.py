"""Capture the owned scout's ordinary in-range auto attacks on the passive dummy."""
import argparse,copy,json,math,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_retained_class_fixture import closed
from . import interaction_pet_attack_capture as capture
from .pet_attack_fixture import PetAttackFixture
from .pet_attack_capture_evidence import target_checks
from .pet_attack_evidence import combat_pairs
from .interaction_ground_movement import position
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.native_objects import guid
from .world.gameobjects import modern_guid
from .interaction_macros import require
from .melee_result_evidence import pairs as hit_pairs
from .interaction_observation import read_page
from .interaction_operations import command


def run(t,preparation,entry,stage_path,review_path,require_feedback=False):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);d=closed(stage_path)
    if (d.get('phase')!='await_owned_pet_attack_review' or d.get('actor')!=t.fixture or
        d.get('runtime')!=t.receipt['runtime'] or d.get('native_session')!=session or
        [s['sha256'] for s in d.get('sources',[])]!=[lab.sha256(p) for p in (preparation,entry)] or
        len(d.get('checks',{}))!=10 or not all(d['checks'].values()) or
        len(d.get('position_freeze',{}).get('checks',{}))!=4 or not all(d['position_freeze']['checks'].values()) or
        d['position_freeze']['accepted']!=d['staged_position'] or d.get('qualification_added') is not False or
        d['fixture_file']['sha256']!=lab.sha256(Path(d['fixture_file']['path']))):
        raise RuntimeError('closed owned in-range dummy staging differs')
    fixture=PetAttackFixture.resume(t.out,t.fixture,Path(d['fixture_file']['path']))
    o=capture.AttackPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),native_session=session,qualification_added=False,
        stage_source={'path':str(stage_path),'sha256':lab.sha256(stage_path)});t.persist();since=None
    owner={'guid':5,'map':0};target=copy.deepcopy(d['native_target'])
    try:
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT entry,flags_extra,unit_flags FROM client442_world.creature_template WHERE entry=44548')
            flags=q.fetchone()
        if not flags or not flags[1]&0x40000:
            raise RuntimeError('the passive dummy must retain native NO_SKILLGAIN')
        t.receipt['dummy_skillgain_guard']={'row':flags,'native_no_skillgain':True};t.persist()
        checked=reviewed(t,review_path,'owned_melee_dummy')
        if (checked.get('stage_source_sha256')!=lab.sha256(stage_path) or checked.get('dummy_visible') is not True or
            checked['frame']['sha256']!=d['frame']['sha256'] or position(5)!=d['staged_position'] or
            math.dist(d['staged_position'][:3],target['movement']['position'][:3])>4):
            raise RuntimeError('fresh reviewed in-range owner and passive dummy differ')
        image=review_path.parent/checked['frame']['file']
        if require_feedback:
            ready,frame=t.observe('owned_melee_feedback_ready')
            t.receipt['melee_feedback_preflight']={'observer_version':ready.get('observer_version'),
                'public':ready.get('owner_melee'),'frame':frame};t.persist()
            if ready.get('observer_version')!=138 or ready.get('owner_melee',{}).get('active') is not False:
                raise RuntimeError('requires loaded passive melee observer138 with autoattack stopped')
        def admitted():
            nonlocal since
            age=time.time()-image.stat().st_mtime
            accepted=0<=age<110 and lab.sha256(image)==checked['frame']['sha256']
            if accepted:since=time.time();t.receipt['melee_started_at']=since;t.persist()
            return {'accepted':accepted,'checked_at':time.time(),'age_seconds':age,'maximum_seconds':110,
                'frame':checked['frame'],'source':str(review_path),'source_sha256':lab.sha256(review_path)}
        def outcome(before,after,selected):
            public=None
            if require_feedback:
                if before.get('observer_version')!=138 or 'owner_melee' not in before:
                    raise RuntimeError('requires the loaded passive melee observer138')
                state,frame=read_page(t,'owned_melee_public_outcome','combat_log','/tcui combat_log')
                public={'probe':state['melee_probe'],'frame':frame,'before_sequence':before['owner_melee']['event_sequence']}
                t.receipt['melee_public_capture']=public;t.persist()
                command(t,'/tcui state')
            o.poll();until=time.time()
            packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if
                p.get('session')==session and since<=p.get('time',0)<=until]
            modern=[p for p in packets if p.get('direction')=='from_client' and p.get('name')=='CMSG_ATTACK_SWING']
            native=[p for p in packets if p.get('direction')=='to_native' and p.get('name')=='CMSG_ATTACK_SWING']
            identity=None
            if len(modern)==1:
                r=Reader(bytes.fromhex(modern[0]['body']));identity=r.guid();r.end()
            hits=[]
            for p in packets:
                if p.get('direction')!='from_native' or p.get('name')!='SMSG_ATTACKER_STATE_UPDATE':continue
                r=Reader(bytes.fromhex(p['body']));flags,=r.unpack('I');attacker,victim=guid(r),guid(r)
                damage,overkill=r.unpack('ii')
                if (attacker,victim)==(5,target['guid']):
                    hits.append({'packet':p,'hit_info':flags,'attacker':attacker,'victim':victim,
                        'damage':damage,'overkill':overkill,'remaining_native_body':r.raw(len(r.data)-r.pos).hex()})
            starts=combat_pairs(packets,session,since,until,owner,target,'SMSG_ATTACK_START')
            checks={'one_owned_modern_attack':len(modern)==1 and identity==modern_guid(target['guid'],0),
                'one_exact_native_attack':len(native)==1 and native[0]['body']==struct.pack('<Q',target['guid']).hex(),
                'native_attack_start_delivered':bool(starts) and all(p['client'] for p in starts),
                'owned_native_positive_hit':any(h['damage']>0 for h in hits),
                'owner_position':position(5)==d['staged_position'],**target_checks(o.target,after,o.player)}
            delivered=[p for p in packets if p.get('direction')=='to_client' and p.get('name')=='SMSG_ATTACKER_STATE_UPDATE']
            matched,orphaned=(hit_pairs(packets,5,target['guid'],0) if require_feedback else ([],[]))
            if require_feedback:
                events=public['probe']['events'];destination=after['target']['guid']
                matching=[v for v in events if v.get('sequence',0)>public['before_sequence'] and
                    v.get('event')=='SWING_DAMAGE' and v.get('source_guid')==t.guid and
                    v.get('destination_guid')==destination and any(p['client'] and
                        v.get('amount')==p['expected']['damage']>0 and
                        v.get('school')==1 and v.get('overkill')==p['expected']['overkill'] and
                        isinstance(v.get('timestamp'),(int,float)) and
                        abs(v['timestamp']-p['native']['time'])<2 and
                        bool(v.get('critical'))==bool(p['expected']['hit_info']&0x200) and
                        bool(v.get('offhand'))==bool(p['expected']['hit_info']&4) and
                        bool(v.get('glancing'))==bool(p['expected']['hit_info']&0x10000) and
                        bool(v.get('crushing'))==bool(p['expected']['hit_info']&0x20000) for p in matched)]
                public['matching_owned_events']=matching
                checks.update(all_native_hit_results_delivered=bool(matched) and all(p['client'] for p in matched),
                    no_orphan_or_duplicate_hits=not orphaned,public_owned_swing_result=bool(matching),
                    public_autoattack_active=after['owner_melee']['active'] is True)
            t.receipt['melee_capture']={'checks':checks,'modern_requests':modern,'native_requests':native,
                'attack_start':starts,'native_hits':hits,'delivered_hit_packets':delivered,
                'hit_pairs':matched,'orphan_hits':orphaned,'public_outcome':public,
                'missing_feedback':bool(hits) and not delivered,'until':until};t.persist()
            status='owned_melee_feedback_pass' if require_feedback else 'owned_melee_capture_pass'
            return {'status':status if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':t.receipt['melee_capture']}
        with t.bounded_combat_observation(60):
            require(t.step('combat.autoattack_capture','Start normal owner auto attacks on the reviewed passive dummy.',
                {'attack':{'kind':'chat','value':'/startattack'}},outcome,diagnostic_action='attack',before_input=admitted),
                'owned_melee_feedback_pass' if require_feedback else 'owned_melee_capture_pass')
    finally:
        with t.bounded_combat_observation(60):
            try:
                if since is not None:
                    stop_started=time.time();t.execute({'kind':'chat','value':'/stopattack'})
                    if require_feedback:
                        state,frame=t.observe('owned_melee_stopped');until=time.time()
                        packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if
                            p.get('session')==session and stop_started<=p.get('time',0)<=until]
                        stops=combat_pairs(packets,session,stop_started,until,owner,target,'SMSG_ATTACK_STOP')
                        checks={'one_modern_stop':sum(p.get('name')=='CMSG_ATTACK_STOP' and
                            p.get('direction')=='from_client' for p in packets)==1,
                            'one_native_stop':sum(p.get('name')=='CMSG_ATTACK_STOP' and
                            p.get('direction')=='to_native' and p.get('body')=='' for p in packets)==1,
                            'native_stop_delivered':bool(stops) and all(p['client'] for p in stops),
                            'public_autoattack_inactive':state['owner_melee']['active'] is False}
                        t.receipt['melee_stop']={'checks':checks,'pairs':stops,'frame':frame};t.persist()
                        if not all(checks.values()):raise RuntimeError('ordinary owned melee stop differs')
            finally:capture.restore(t,o,inventory,old,fixture,d['original_spell'],d['original_position'])
    t.receipt.update(completed=True,phase='owned_melee_capture_complete',qualified_scope=
        'Attributable owner melee diagnostic only. Passive dummy health is unchanged; '
        'Client hit feedback is checked separately when requested. No applied health damage, kill or cadence qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','stage','review','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--require-feedback',action='store_true');a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.stage,a.review,a.require_feedback)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({key:t.receipt.get(key) for key in ('completed','failure','restoration_checks')}),flush=True)
