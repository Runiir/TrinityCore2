"""Prove one reviewed native pet Attack, ordinary stopping and whole restoration."""
import argparse,copy,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,SCRIPT_BOUNDARY,saved,character,pets
from .interaction_spellbook_pet_recon import entry_source
from .interaction_retained_class_fixture import closed
from . import interaction_pet_attack_capture as capture
from .pet_attack_fixture import PetAttackFixture
from .pet_attack_capture_evidence import button,target_checks,target_guid
from .pet_attack_evidence import request_checks,combat_pairs
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_dismiss import vitals
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries,latest
from .world.objects import INDEX


def run(t,preparation,entry,stage_path,review_path):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);d=closed(stage_path)
    if (d.get('phase')!='await_owned_pet_attack_review' or d.get('actor')!=t.fixture or
        d.get('runtime')!=t.receipt['runtime'] or d.get('native_session')!=session or
        [s['sha256'] for s in d.get('sources',[])]!=[lab.sha256(p) for p in (preparation,entry)] or
        len(d.get('checks',{}))!=10 or not all(d['checks'].values()) or
        d.get('custom_script_permission')!='blocked_by_user' or d.get('softTargetInteract')!=SCRIPT_BOUNDARY or
        d.get('qualification_added') is not False or d['fixture_file']['sha256']!=lab.sha256(Path(d['fixture_file']['path']))):
        raise RuntimeError('closed reviewed selected pet Attack fixture differs')
    fixture=PetAttackFixture.resume(t.out,t.fixture,Path(d['fixture_file']['path']))
    o=capture.AttackPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    pet=copy.deepcopy(d['native_pet']);target=copy.deepcopy(d['native_target']);since=None
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),stage_source={'path':str(stage_path),'sha256':lab.sha256(stage_path)},
        native_session=session,qualification_added=False);t.persist()
    def stopped():
        deadline=time.monotonic()+30
        while True:
            o.poll()
            if o.present() and pair(o.pet['fields'],'UNIT_FIELD_TARGET')==0 and not o.pet['fields'].get(INDEX['UNIT_FIELD_FLAGS'],0)&0x80000:break
            if time.monotonic()>deadline:break
            time.sleep(.5)
        sample=read(t,'attack_stopped_public');o.poll();until=time.time()
        pairs=combat_pairs(list(entries(lab.ROOT/'evidence/world_packets.jsonl')),session,since,until,pet,target,'SMSG_ATTACK_STOP') if since else []
        checks={'native_attack_stop':bool(pairs),'attack_stop_delivered':bool(pairs) and all(p['client'] for p in pairs),
            'same_owned_pet':o.present() and o.pet['guid']==pet['guid'],'native_pet_target_empty':pair(o.pet['fields'],'UNIT_FIELD_TARGET')==0,
            'native_pet_combat_clear':not o.pet['fields'].get(INDEX['UNIT_FIELD_FLAGS'],0)&0x80000,
            'public_pet_target_empty':sample['probe'].get('pet_target_exists') is False and not sample['probe'].get('pet_target_guid'),
            'public_pet_combat_clear':sample['probe'].get('pet_combat') is False,'public_pet_idle':sample['probe'].get('pet_speed')==0,
            'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(pet),'ui_clean':sample['ui_clean']}
        t.receipt['attack_stop']={'checks':checks,'combat_pairs':pairs,'public':sample,'native_pet':copy.deepcopy(o.pet)};t.persist()
        if not all(checks.values()):raise RuntimeError('ordinary Follow did not prove native/public pet Attack stop')
    try:
        checked=reviewed(t,review_path,'owned_pet_attack_dummy')
        if (checked.get('stage_source_sha256')!=lab.sha256(stage_path) or checked.get('dummy_visible') is not True or
            checked.get('point')!=d['attack_point'] or checked['frame']['sha256']!=d['frame']['sha256']):
            raise RuntimeError('fresh source-bound Attack image review differs')
        state,_=t.observe('attack_reviewed_native_input');sample=read(t,'attack_current_native_control');o.poll()
        row,point=button(sample['probe'],o.pet)
        if (not all(target_checks(o.target,state,o.player).values()) or point!=d['attack_point'] or
            not o.present() or o.pet['guid']!=pet['guid'] or o.target['guid']!=target['guid'] or
            resources(inventory)!=d['baseline']['resources'] or
            saved(5)!=d['baseline']['saved'] or sample['probe'].get('player_can_attack_target') is not True or
            sample['probe'].get('pet_combat') is not False):
            raise RuntimeError('reviewed current owned Attack authority or passive combat reads differ')
        pet=copy.deepcopy(o.pet);target=copy.deepcopy(o.target)
        since=time.time();t.receipt.update(native_pet=pet,native_target=target,attack_started_at=since);t.persist()
        def outcome(b,a,s):
            sample=read(t,'attack_native_combat');state,frame=t.observe('attack_native_combat_scene');o.poll()
            until=time.time();packets=list(entries(lab.ROOT/'evidence/world_packets.jsonl'))
            checks,requests=request_checks(packets,session,since,until,pet,target)
            pairs=combat_pairs(packets,session,since,until,pet,target,'SMSG_ATTACK_START')
            rejection=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                since<=r.get('time',0)<=until and r.get('event')=='pet_action_translation_rejected')
            owner=vitals(o)
            checks.update(native_attack_start=bool(pairs),attack_start_delivered=bool(pairs) and all(p['client'] for p in pairs),
                native_pet_victim=pair(o.pet['fields'],'UNIT_FIELD_TARGET')==target['guid'],
                native_pet_combat=bool(o.pet['fields'].get(INDEX['UNIT_FIELD_FLAGS'],0)&0x80000),
                public_pet_victim=sample['probe'].get('pet_target_guid')==target_guid(target) and sample['probe'].get('pet_target_exists') is True,
                public_pet_combat=sample['probe'].get('pet_combat') is True,
                public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(pet),same_owned_pet=o.present() and o.pet['guid']==pet['guid'],
                passive_dummy_health_unchanged=o.target['fields'].get(INDEX['UNIT_FIELD_HEALTH'])==target['fields'][INDEX['UNIT_FIELD_HEALTH']],
                owner_alive=owner['UNIT_FIELD_HEALTH']>0,position=position(5)==d['staged_position'],
                resources=resources(inventory)==d['baseline']['resources'],saved=saved(5)==d['baseline']['saved'],
                money=character(5,2)['money']==d['baseline']['money'],
                retained_pet=all(retained_imp(t.fixture,pets(5))[k]==v for k,v in d['baseline']['pet'].items()),
                no_translation_rejection=rejection is None,ui_clean=sample['ui_clean'])
            checks.update(target_checks(o.target,state,o.player))
            return {'status':'owned_native_pet_attack_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'combat_pairs':pairs,'rejection':rejection,
                    'native_pet':copy.deepcopy(o.pet),'native_target':copy.deepcopy(o.target),'owner_vitals':owner,
                    'native_auras':copy.deepcopy(o.auras),'public':sample,'state':state,'frame':frame}}
        require(t.step('pets.command_attack','Click the reviewed stock Attack once and prove delivered native combat against the passive dummy.',
            {'attack':{'kind':'click','value':point,'hold':.4}},outcome,diagnostic_action='attack'),'owned_native_pet_attack_pass')
    finally:
        capture.restore(t,o,inventory,old,fixture,d['original_spell'],d['original_position'],after_follow=stopped if since else None)
    t.receipt.update(completed=True,phase='owned_native_pet_attack_complete',qualified_scope=
        'One owned retained Imp stock Attack against the selected existing passive dummy, exact native command and '
        'delivered Attack Start, native/public pet victim and combat, ordinary Follow stop and delivered Attack Stop, '
        'Assist and full aura/vitals/resources/position restoration. No damage, kill or other-target qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('preparation','entry','stage','review','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.stage,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
