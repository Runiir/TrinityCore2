"""Prove ordinary owner melee reduces one existing target's native/public health."""
import argparse,copy,json,math,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,SCRIPT_BOUNDARY,saved,character
from .interaction_spellbook_pet_recon import entry_source
from .interaction_retained_class_fixture import closed
from .interaction_pet_commands import eligibility,PET_KEYS
from .interaction_pet_spell import SpellPresence,pet_vitals,restore_spell
from .interaction_pet_summon import SummonOracle,summon_checks
from .interaction_spellbook_navigation import wire_known
from .interaction_pet_dismiss import vitals
from .interaction_pet_command_probe import read,follow_row
from .interaction_pet_react_modes import mode,public_bar,active_mode
from .interaction_sit_stand import pose,afk
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_pet_control_training import protected
from .interaction_pet_target import pair
from .interaction_bridge_deploy import shot
from .interaction_macros import require
from .interaction_observation import read_page
from .interaction_operations import command
from .interaction_pet_attack_capture import restore
from .melee_health_fixture import MeleeHealthFixture,native_target
from .pet_attack_capture_evidence import target_guid
from .melee_result_evidence import pairs as hit_pairs,public_events,health_checks,stop_request_contract
from .pet_attack_evidence import combat_pairs
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.native_objects import records,guid
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .world.objects import INDEX
from .pet_attack_landing import acknowledgement


class HealthPresence(SpellPresence):
    def __init__(self,*args):super().__init__(*args);self.target=None

    def inspect_packet(self,p):
        super().inspect_packet(p)
        if p.get('direction')!='from_native' or p.get('name')!='SMSG_UPDATE_OBJECT':return
        for r in records(bytes.fromhex(p['body'])):
            if native_target(r):
                if self.target and self.target['guid']!=r['guid']:raise RuntimeError('ambiguous health target creation')
                self.target=r
            elif self.target and r.get('guid')==self.target['guid']:self.target['fields'].update(r.get('fields',{}))
            if self.target and self.target['guid'] in r.get('removed',[]):self.target['removed']=True


def health(o):return o.target['fields'][INDEX['UNIT_FIELD_HEALTH']]


def load_target(row):
    result=copy.deepcopy(row);fields={int(k):v for k,v in result['fields'].items()}
    if len(fields)!=len(result['fields']):raise ValueError('ambiguous numeric native target fields')
    result['fields']=fields;return result


def entry_pvp(session,entry):
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if (p.get('session')!=session or p.get('direction')!='from_native' or p.get('name')!='SMSG_UPDATE_OBJECT' or
            not entry['started_at']<=p.get('time',0)<=entry['finished_at']):continue
        for row in records(bytes.fromhex(p['body'])):
            if row.get('guid')==5 and row.get('kind')==4:
                return {'value':row['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)&0xff00,'packet':p,
                    'zero_default_from_creation':INDEX['UNIT_FIELD_BYTES_2'] not in row['fields']}
    raise RuntimeError('entry-bound original native PvP bytes are absent')


def retained_presence(t,o,label):
    o.poll()
    if o.present():return
    absence=read(t,label+'_absence');o.poll()
    if o.present() or pair(o.player,'UNIT_FIELD_SUMMON') or absence['probe'].get('pet_guid') or 688 not in wire_known(t,o.session):
        raise RuntimeError('normal transfer recovery requires native/public pet absence and known Summon Imp')
    summon=SummonOracle(o.session,5,o.started).poll();old=o.pet['guid'] if o.pet else 0;since=time.time()
    def outcome(before,after,selected):
        summon.poll();checks,packets=summon_checks(summon,since,old,t.receipt['baseline']['pet'],selected,True)
        return {'status':'owned_retained_transfer_summon_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':packets,'preparation_or_cleanup_only':True}}
    require(t.step(label,'Restore the retained Imp after actual native/public transfer absence.',
        {'summon':{'kind':'chat','value':'/cast Summon Imp'}},outcome,diagnostic_action='summon',
        await_state=lambda state:summon.poll().present() and not state.get('player_cast',{}).get('active')),
        'owned_retained_transfer_summon_pass');o.poll()


def original_pvp(t,o):
    deadline=time.monotonic()+330;samples=[];expected=t.receipt['baseline']['pvp_bytes']
    while o.poll().player.get(INDEX['UNIT_FIELD_BYTES_2'],0)&0xff00!=expected:
        samples.append({'time':time.time(),'native_pvp_bytes':o.player.get(INDEX['UNIT_FIELD_BYTES_2'],0)&0xff00})
        if time.monotonic()>deadline:raise RuntimeError('ordinary native PvP timeout did not restore the original bytes')
        time.sleep(2)
    t.receipt['pvp_restoration']={'checks':{'original_native_pvp_bytes':True},'samples':samples,
        'source':'Passive native PvP expiry after returning to the original friendly zone; no PvP setter or toggle.'};t.persist()


def stage(t,preparation,entry):
    old,e,base,inventory,identity=eligibility(t,preparation,entry);t.clean_panels()
    o=HealthPresence(base.session,5,e['started_at']).poll();sample=read(t,'health_original_bar')
    state,_=t.observe('health_original_scene');row=follow_row(sample['probe'])
    if (state.get('observer_version')!=138 or state['owner_melee']['active'] or not row or not row['active'] or
        not active_mode(sample['probe'],'PET_MODE_ASSIST') or not sample['ui_clean']):
        raise RuntimeError('requires original idle Assist/Follow and loaded passive melee observer138')
    baseline={'resources':resources(inventory),'saved':e['entered_saved'],'position':position(5),
        'vitals':vitals(o),'pet':{k:identity[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),
        'money':character(5,2)['money'],'public_bar':public_bar(sample['probe']),
        'pvp_bytes':entry_pvp(o.session,e)['value']}
    original={'auras':copy.deepcopy(o.auras),'public_buffs':state.get('buffs',{}),'pet_vitals':pet_vitals(o)}
    # Use the shared spell parser's canonical public aura identity.
    from .pet_spell_evidence import buffs
    original['public_buffs']=buffs(state)
    if 6307 in original['public_buffs']:raise RuntimeError('requires the restored original aura baseline')
    t.receipt.update(baseline=baseline,original_position=baseline['position'],original_spell=original,
        qualification_added=False);t.persist();fixture=MeleeHealthFixture(t.out,t.fixture)
    try:
        t.receipt['original_pvp_source']=entry_pvp(o.session,e);original_pvp(t,o)
        mode(t,o,0,'fixture.health_pet_passive')
        staged=fixture.prepare();t.receipt['baseline']['position']=staged;t.persist()
        retained_presence(t,o,'fixture.health_transfer_pet')
        catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']]
        if not catalogs or catalogs[-1]['react']!=0:mode(t,o,0,'fixture.health_transfer_passive')
        # Honorless Target is a normal zone-transfer aura and expires naturally.
        deadline=time.monotonic()+45
        while any(r['spell']==2479 for r in o.poll().auras.values()):
            if time.monotonic()>deadline:raise RuntimeError('normal Honorless Target transfer aura did not expire')
            time.sleep(2)
        o.poll();transfer,_=t.observe('health_transfer_baseline')
        from .pet_spell_evidence import buffs
        if (o.auras!=original['auras'] or buffs(transfer)!=original['public_buffs'] or
            vitals(o)!=baseline['vitals'] or pet_vitals(o)!=original['pet_vitals']):
            passive=read(t,'health_passive_cleanup_bar')
            restore_spell(t,o,original,expected_bar=public_bar(passive['probe']))
        t.execute({'kind':'chat','value':'/targetexact '+fixture.dummy[2]})
        state,_=t.observe('health_selected_target');o.poll();sample=read(t,'health_passive_control');o.poll()
        frozen=position(5);time.sleep(.5)
        checks={'exact_native_target':native_target(o.target),'native_selection':o.selected()==o.target['guid'] if o.target else False,
            'exact_public_target':bool(o.target and state['target'].get('guid')==target_guid(o.target)),
            'undamaged_target':bool(o.target and health(o)==o.target['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]),
            'safe_target_health':bool(o.target and health(o)>=10 and any(r[0]==228 and r[1]==r[2] for r in baseline['saved']['skills'])),
            'public_health':bool(o.target and state['target'].get('health')==health(o)),
            'in_melee_range':bool(o.target and math.dist(frozen[:3],o.target['movement']['position'][:3])<4),
            'stable_position':position(5)==frozen,'native_passive':o.present() and
                o.pet['fields'][INDEX['UNIT_FIELD_PETNUMBER']]==baseline['pet']['id'] and
                any(c['guid']==o.pet['guid'] and c['react']==0 for c in o.catalogs[-1:]),
            'public_passive':active_mode(sample['probe'],'PET_MODE_PASSIVE'),
            'idle_pet':not sample['probe']['pet_combat'] and not sample['probe']['pet_target_exists'],
            'original_vitals':vitals(o)==baseline['vitals'],'original_saved':saved(5)==baseline['saved'],
            'protected':all(protected(old).values()),'ui_clean':sample['ui_clean']}
        ack=acknowledgement(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,t.receipt['started_at'],
            time.time(),5,fixture.rows[1][1:6])
        t.receipt.update(checks=checks,native_target=copy.deepcopy(o.target),native_pet=copy.deepcopy(o.pet),
            staged_position=frozen,teleport_acknowledgement=ack,
            fixture_file={'path':str(t.out/'melee_health_fixture.json'),'sha256':lab.sha256(t.out/'melee_health_fixture.json')},
            frame=shot(t.out/'health_review_ready.png'));t.persist()
        if not all(checks.values()):raise RuntimeError('reviewed damageable target staging differs')
        t.receipt.update(completed=True,phase='await_owned_melee_health_review',
            qualified_scope='Pose staging and Passive preparation only; no melee or applied damage qualification.')
    except Exception as error:
        t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist()
        fixture.restore();t.receipt['baseline']['position']=baseline['position']=t.receipt['original_position']
        retained_presence(t,o,'fixture.health_failure_pet');original_pvp(t,o)
        restore(t,o,inventory,old,fixture,original,t.receipt['original_position']);raise


def staging_source(t,preparation,entry,stage_path):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    d=closed(stage_path)
    if (d.get('phase')!='await_owned_melee_health_review' or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        d.get('native_session')!=session or len(d.get('checks',{}))!=15 or not all(d['checks'].values()) or
        [s['sha256'] for s in d.get('sources',[])]!=[lab.sha256(p) for p in (preparation,entry)] or
        d['fixture_file']['sha256']!=lab.sha256(Path(d['fixture_file']['path']))):raise RuntimeError('closed health staging differs')
    return old,session,e,d


def refresh(t,preparation,entry,stage_path):
    old,session,e,d=staging_source(t,preparation,entry,stage_path)
    o=HealthPresence(session,5,e['started_at']).poll()
    state,_=t.observe('health_refresh_scene');sample=read(t,'health_refresh_passive');o.poll()
    frozen=position(5);time.sleep(.5);baseline=d['baseline'];target=load_target(d['native_target'])
    checks={'exact_native_target':bool(o.target and native_target(o.target) and o.target['guid']==target['guid']),
        'native_selection':bool(o.target and o.selected()==o.target['guid']),
        'exact_public_target':bool(o.target and state['target'].get('guid')==target_guid(o.target)),
        'undamaged_target':bool(o.target and health(o)==target['fields'][INDEX['UNIT_FIELD_HEALTH']]
            ==o.target['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]),
        'safe_target_health':bool(o.target and health(o)>=10 and any(r[0]==228 and r[1]==r[2] for r in baseline['saved']['skills'])),
        'public_health':bool(o.target and state['target'].get('health')==health(o)),
        'in_melee_range':bool(o.target and math.dist(frozen[:3],o.target['movement']['position'][:3])<4),
        'stable_position':position(5)==frozen==d['staged_position'],
        'native_passive':o.present() and o.pet['fields'][INDEX['UNIT_FIELD_PETNUMBER']]==baseline['pet']['id']
            and any(c['guid']==o.pet['guid'] and c['react']==0 for c in o.catalogs[-1:]),
        'public_passive':active_mode(sample['probe'],'PET_MODE_PASSIVE'),
        'idle_pet':not sample['probe']['pet_combat'] and not sample['probe']['pet_target_exists'],
        'original_vitals':vitals(o)==baseline['vitals'],'original_saved':saved(5)==baseline['saved'],
        'protected':all(protected(old).values()),'ui_clean':sample['ui_clean'] and not state['owner_melee']['active']}
    if not all(checks.values()):
        t.receipt.update(checks=checks);t.persist();raise RuntimeError('read-only health scene refresh differs')
    for key in ('baseline','original_position','original_spell','fixture_file','staged_position','sources'):
        t.receipt[key]=copy.deepcopy(d[key])
    t.receipt.update(native_session=session,checks=checks,native_target=copy.deepcopy(o.target),
        native_pet=copy.deepcopy(o.pet),refresh_source={'path':str(stage_path),'sha256':lab.sha256(stage_path)},
        qualification_added=False,frame=shot(t.out/'health_review_ready.png'),
        completed=True,phase='await_owned_melee_health_review',
        qualified_scope='Read-only refresh of the same staged target, actor and Passive pet; no Attack, transfer or qualification.')


def run(t,preparation,entry,stage_path,review_path):
    old,session,e,d=staging_source(t,preparation,entry,stage_path)
    fixture=MeleeHealthFixture.resume(t.out,t.fixture,Path(d['fixture_file']['path']))
    o=HealthPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),native_session=session,qualification_added=False,
        stage_source={'path':str(stage_path),'sha256':lab.sha256(stage_path)});t.persist();since=None;stopped=False
    target=load_target(d['native_target']);owner={'guid':5,'map':0}
    try:
        checked=reviewed(t,review_path,'owned_melee_health_target')
        if (checked.get('stage_source_sha256')!=lab.sha256(stage_path) or checked.get('target_visible') is not True or
            checked['frame']['sha256']!=d['frame']['sha256'] or position(5)!=d['staged_position'] or
            not o.target or o.target['guid']!=target['guid'] or health(o)!=target['fields'][INDEX['UNIT_FIELD_HEALTH']] or
            o.catalogs[-1]['react']!=0):raise RuntimeError('fresh selected damageable target or Passive preparation differs')
        image=review_path.parent/checked['frame']['file']
        def admit():
            nonlocal since
            age=time.time()-image.stat().st_mtime;accepted=0<=age<110 and lab.sha256(image)==checked['frame']['sha256']
            if accepted:since=time.time()
            return {'accepted':accepted,'age_seconds':age,'maximum_seconds':110,'frame':checked['frame'],
                'source':str(review_path),'source_sha256':lab.sha256(review_path),'checked_at':time.time()}
        with t.bounded_combat_observation(60):
            def started(before,after,selected):
                o.poll();dead=health(o)==0
                checks={'public_active_or_native_death_stop':after['owner_melee']['active'] is True or dead,
                    'public_target_or_native_death_clear':after['target'].get('guid')==target_guid(target) or dead and not after['target'].get('exists'),
                    'native_health_loss':0<=health(o)<target['fields'][INDEX['UNIT_FIELD_HEALTH']]}
                t.receipt['first_health_observation']={'time':time.time(),'native':copy.deepcopy(o.target),
                    'public_target':copy.deepcopy(after['target']),'public_autoattack':copy.deepcopy(after['owner_melee'])};t.persist()
                return {'status':'owned_melee_health_started_pass' if all(checks.values()) else 'client_or_protocol_failure','oracle':checks}
            require(t.step('combat.autoattack_health','Apply ordinary owner melee damage to the reviewed existing target.',
                {'attack':{'kind':'chat','value':'/startattack'}},started,diagnostic_action='attack',before_input=admit),
                'owned_melee_health_started_pass')
            stop_since=time.time();t.execute({'kind':'chat','value':'/stopattack'});stopped=True
            submission=next(c for c in reversed(t.receipt['chat_submission_checks'])
                if c.get('selected_text')=='/stopattack' and c.get('matches') and c.get('submitted'))
            stop_image=t.out/submission['frame']['file'];pre_submit_at=stop_image.stat().st_mtime
            if lab.sha256(stop_image)!=submission['frame']['sha256'] or not stop_since<=pre_submit_at<=time.time():
                raise RuntimeError('ordinary Stop submission frame differs')
            t.receipt['ordinary_stop_submission']={'check':submission,'pre_submit_at':pre_submit_at};t.persist()
            public,frame=read_page(t,'health_public_swings','combat_log','/tcui combat_log')
            command(t,'/tcui state');state,health_frame=t.observe('health_stopped_outcome');o.poll();until=time.time()
            packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==session and since<=p.get('time',0)<=until]
            matched,orphaned=hit_pairs(packets,5,target['guid'],0);foreign=[];petcasts=[]
            for p in packets:
                if p.get('direction')!='from_native':continue
                if p.get('name')=='SMSG_ATTACKER_STATE_UPDATE':
                    r=Reader(bytes.fromhex(p['body']));r.unpack('I');attacker,victim=guid(r),guid(r)
                    if victim==target['guid'] and attacker!=5:foreign.append(p)
                elif p.get('name') in ('SMSG_SPELL_START','SMSG_SPELL_GO'):
                    r=Reader(bytes.fromhex(p['body']));caster=guid(r);guid(r);_,spell=r.unpack('BI')
                    if caster==d['native_pet']['guid'] and spell==3110:petcasts.append(p)
            swing_events=public_events(public['melee_probe'],t.receipt['cases'][0]['before']['owner_melee']['event_sequence'],
                matched,t.guid,target_guid(target))
            first=t.receipt['first_health_observation'];first_health=first['native']['fields'][INDEX['UNIT_FIELD_HEALTH']]
            first_hits=[p for p in matched if p['native']['time']<=first['time']]
            public_death=not first['public_target'].get('exists') and any(v.get('overkill',-1)>=0 for v in swing_events)
            checks=health_checks(target['fields'][INDEX['UNIT_FIELD_HEALTH']],first_health,first_hits,
                first['public_target'].get('health'),foreign,allow_death=True,public_death=public_death)
            starts=combat_pairs(packets,session,since,until,owner,target,'SMSG_ATTACK_START')
            stops=combat_pairs(packets,session,since,until,owner,target,'SMSG_ATTACK_STOP')
            modern=[p for p in packets if p.get('name')=='CMSG_ATTACK_SWING' and p.get('direction')=='from_client']
            native=[p for p in packets if p.get('name')=='CMSG_ATTACK_SWING' and p.get('direction')=='to_native']
            identity=None
            if len(modern)==1:r=Reader(bytes.fromhex(modern[0]['body']));identity=r.guid();r.end()
            modern_stops=sum(p.get('name')=='CMSG_ATTACK_STOP' and p.get('direction')=='from_client' and p['time']>=stop_since for p in packets)
            native_stops=sum(p.get('name')=='CMSG_ATTACK_STOP' and p.get('direction')=='to_native' and p['time']>=stop_since and p['body']=='' for p in packets)
            checks.update(one_owned_modern_attack=len(modern)==1 and identity==modern_guid(target['guid'],0),
                one_exact_native_attack=len(native)==1 and native[0]['body']==struct.pack('<Q',target['guid']).hex(),
                ordinary_stop_request_contract=stop_request_contract(modern_stops,native_stops,stops,pre_submit_at),
                attack_start_delivered=bool(starts) and all(p['client'] for p in starts),
                attack_stop_delivered=bool(stops) and all(p['client'] for p in stops),
                final_public_target=state['target'].get('guid')==target_guid(target) or health(o)==0 and not state['target'].get('exists'),
                target_max_health_unchanged=o.target['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]==target['fields'][INDEX['UNIT_FIELD_MAXHEALTH']],
                native_pet_passive=o.catalogs[-1]['react']==0,
                native_pet_target_empty=pair(o.pet['fields'],'UNIT_FIELD_TARGET')==0,
                public_autoattack_stopped=state['owner_melee']['active'] is False,no_orphan_hits=not orphaned,
                public_swing_damage=bool(swing_events),no_pet_firebolt=not petcasts,
                owner_alive=vitals(o)['UNIT_FIELD_HEALTH']>0,owner_position=position(5)==d['staged_position'],
                ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
            t.receipt['health_outcome']={'checks':checks,'native_before':target,'native_after':copy.deepcopy(o.target),
                'health_loss':target['fields'][INDEX['UNIT_FIELD_HEALTH']]-first_health,'first_observation':first,
                'first_hit_pairs':first_hits,'hit_pairs':matched,'orphan_hits':orphaned,
                'foreign_hits':foreign,'pet_firebolts':petcasts,'public_events':swing_events,'public_probe':public['melee_probe'],
                'public_frame':frame,'state':state,'health_frame':health_frame,'start_pairs':starts,'stop_pairs':stops};t.persist()
            if not all(checks.values()):raise RuntimeError('native/public owner applied damage differs')
    finally:
        try:
            if since is not None and not stopped:
                with t.bounded_combat_observation(60):t.execute({'kind':'chat','value':'/stopattack'})
        finally:
            # Move out of combat before the shared Follow/Assist/aura cleanup.
            t.receipt['early_pose_restoration']=fixture.restore();t.receipt['baseline']['position']=d['original_position'];t.persist()
            retained_presence(t,o,'fixture.health_return_pet');original_pvp(t,o)
            restore(t,o,inventory,old,fixture,d['original_spell'],d['original_position'])
    t.receipt.update(completed=True,phase='owned_melee_health_complete',qualified_scope=
        'Ordinary owner autoattack on one existing neutral level-three Sheep, exact first native/public health loss, '
        'delivered owner hit feedback and public SWING_DAMAGE, ordinary Stop or native death-stop, no pet damage, and whole actor restoration. '
        'Earned target damage/death and kill statistics are retained. Monster combat, other classes, ability damage and cadence remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('stage','refresh','run'))
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--stage',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='run' and (a.stage is None or a.review is None):p.error('run requires closed staging and fresh review')
    if a.action=='refresh' and a.stage is None:p.error('refresh requires closed staging')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='stage':stage(t,a.preparation,a.entry)
            elif a.action=='refresh':refresh(t,a.preparation,a.entry,a.stage)
            else:run(t,a.preparation,a.entry,a.stage,a.review)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase','restoration_checks')}),flush=True)
