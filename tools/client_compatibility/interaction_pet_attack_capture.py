"""Capture one reviewed stock Attack request against a passive existing dummy."""
import argparse,copy,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,SCRIPT_BOUNDARY,character,saved,pets
from .interaction_spellbook_pet_recon import entry_source
from .interaction_retained_class_fixture import closed
from .interaction_pet_commands import eligibility,PET_KEYS
from .interaction_pet_command_probe import read,expected_guid,follow_row
from .interaction_pet_target import pair
from .interaction_pet_spell import SpellPresence,pet_vitals,restore_spell
from .pet_spell_evidence import buffs
from .interaction_pet_dismiss import vitals
from .interaction_pet_react_modes import public_bar
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_pet_control_training import protected
from .interaction_pet_follow_capture import follow_request
from . import interaction_pet_moveto_capture as cleanup
from .pet_attack_fixture import PetAttackFixture
from .pet_attack_capture_evidence import button,target_checks
from .observation.inventory import Inventory
from .observation.journal import latest
from .world.native_objects import records
from .world.gameobjects import modern_guid
from .interaction_macros import require


class AttackPresence(SpellPresence):
    def __init__(self,session,owner,started):
        super().__init__(session,owner,started);self.target=None

    def inspect_packet(self,p):
        super().inspect_packet(p)
        if p.get('direction')!='from_native' or p.get('name')!='SMSG_UPDATE_OBJECT':return
        for r in records(bytes.fromhex(p['body'])):
            if r.get('kind')==3 and r['guid']>>52==0xf13 and r['guid']&0xffffffff==279984:self.target=r
            elif self.target and r.get('guid')==self.target['guid']:self.target['fields'].update(r.get('fields',{}))
            if self.target and self.target['guid'] in r.get('removed',[]):self.target=None


def restore(t,o,inventory,old,fixture,original,original_position):
    def before_whole():
        try:
            state,_=t.observe('attack_selection_cleanup')
            if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        finally:
            t.receipt['attack_fixture_restoration']=fixture.restore()
            t.receipt['baseline']['position']=original_position;t.persist()
            restore_spell(t,o,original)
    cleanup.restore(t,o,inventory,old,before_whole=before_whole)


def stage(t,preparation,entry):
    old,e,base,inventory,identity=eligibility(t,preparation,entry);t.clean_panels()
    o=AttackPresence(base.session,5,base.started).poll();sample=read(t,'attack_original_bar')
    state,frame=t.observe('attack_original_scene');catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']]
    follow=follow_row(sample['probe'])
    if (not catalogs or catalogs[-1]['command']!=1 or catalogs[-1]['react']!=3 or
        not follow or not follow.get('active') or not sample['ui_clean'] or state.get('spell_targeting') is not False):
        raise RuntimeError('requires original idle Assist/Follow and no target cursor')
    baseline={'resources':resources(inventory),'saved':e['entered_saved'],'position':position(5),'vitals':vitals(o),
        'pet':{k:identity[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),
        'money':character(5,2)['money'],'public_bar':public_bar(sample['probe'])}
    original={'auras':copy.deepcopy(o.auras),'public_buffs':buffs(state),'pet_vitals':pet_vitals(o)}
    if 6307 in original['public_buffs']:raise RuntimeError('requires the restored original aura baseline')
    t.receipt.update(baseline=copy.deepcopy(baseline),original_spell=original,original_position=baseline['position'],
        qualification_added=False);t.persist();fixture=PetAttackFixture(t.out,t.fixture)
    try:
        staged_position=fixture.prepare();t.receipt['baseline']['position']=staged_position;t.persist()
        t.execute({'kind':'chat','value':'/targetexact Training Dummy'})
        state,frame=t.observe('attack_selected_dummy');o.poll();sample=read(t,'attack_observed_button');o.poll()
        row,point=button(sample['probe'],o.pet);checks=target_checks(o.target,state,o.player)
        checks.update(current_owned_pet=o.present(),owner_vitals=vitals(o)==baseline['vitals'],
            saved=saved(5)==baseline['saved'],protected=all(protected(old).values()),ui_clean=sample['ui_clean'])
        t.receipt.update(checks=checks,staged_position=staged_position,native_target=copy.deepcopy(o.target),
            native_pet=copy.deepcopy(o.pet),observed_button=row,attack_point=point,frame=frame,
            fixture_file={'path':str(t.out/'pet_attack_fixture.json'),'sha256':lab.sha256(t.out/'pet_attack_fixture.json')})
        t.persist()
        if not all(checks.values()):raise RuntimeError('selected owned passive dummy or pet control differs')
        t.receipt.update(completed=True,phase='await_owned_pet_attack_review',qualified_scope=
            'Owned native pose staging, ordinary exact-name target and passive control inspection only. '
            'Attack requires a separate fresh visual review; no gameplay qualification.')
    except Exception:
        t.receipt['baseline']['position']=position(5)
        restore(t,o,inventory,old,fixture,original,baseline['position']);raise


def run(t,preparation,entry,stage_path,review_path):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);d=closed(stage_path)
    if (d.get('phase')!='await_owned_pet_attack_review' or d.get('actor')!=t.fixture or
        d.get('runtime')!=t.receipt['runtime'] or d.get('native_session')!=session or
        [s['sha256'] for s in d.get('sources',[])]!=[lab.sha256(p) for p in (preparation,entry)] or
        len(d.get('checks',{}))!=10 or not all(d['checks'].values()) or
        d.get('qualification_added') is not False or d['fixture_file']['sha256']!=lab.sha256(Path(d['fixture_file']['path']))):
        raise RuntimeError('closed selected pet Attack fixture differs')
    fixture=PetAttackFixture.resume(t.out,t.fixture,Path(d['fixture_file']['path']))
    o=AttackPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),stage_source={'path':str(stage_path),'sha256':lab.sha256(stage_path)},
        native_session=session,qualification_added=False);t.persist()
    try:
        checked=reviewed(t,review_path,'owned_pet_attack_dummy')
        if (checked.get('stage_source_sha256')!=lab.sha256(stage_path) or checked.get('dummy_visible') is not True or
            checked.get('point')!=d['attack_point'] or checked['frame']['sha256']!=d['frame']['sha256']):
            raise RuntimeError('fresh source-bound visible Attack fixture review differs')
        state,_=t.observe('attack_reviewed_input');sample=read(t,'attack_current_control');o.poll()
        row,point=button(sample['probe'],o.pet)
        if (not all(target_checks(o.target,state,o.player).values()) or point!=d['attack_point'] or
            not o.present() or o.pet['guid']!=d['native_pet']['guid'] or
            resources(inventory)!=d['baseline']['resources'] or saved(5)!=d['baseline']['saved']):
            raise RuntimeError('reviewed current owned Attack pet or target differs')
        pet=copy.deepcopy(o.pet);target=copy.deepcopy(o.target);since=time.time()
        t.receipt.update(native_pet=pet,native_target=target,attack_started_at=since);t.persist()
        def outcome(b,a,s):
            sample=read(t,'attack_actual_request');state,frame=t.observe('attack_capture_scene');o.poll()
            requests=cleanup.packets(o,since);modern=[p for p in requests if p['direction']=='from_client']
            native=[p for p in requests if p['direction']=='to_native']
            decoded=follow_request(modern[0]) if len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION' else None
            rejection=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                r.get('time',0)>=since and r.get('event')=='pet_action_translation_rejected')
            checks={'one_actual_stock_pet_action':len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION',
                'submitted_owned_pet':bool(decoded and decoded['guid']==list(modern_guid(pet['guid'],pet['map']))),
                'submitted_selected_dummy':bool(decoded and decoded['target']==list(modern_guid(target['guid'],target['map']))),
                'actual_action_readable':bool(decoded and type(decoded['action_type']) is int and type(decoded['action_value']) is int),
                'finite_position':bool(decoded and all(math.isfinite(v) for v in decoded['position'])),
                'no_native_command':not native,'healthy_rejection':bool(rejection),
                'same_owned_pet':o.present() and o.pet['guid']==pet['guid'],
                'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(pet),
                'owner_vitals':vitals(o)==d['baseline']['vitals'],'position':position(5)==d['staged_position'],
                'saved':saved(5)==d['baseline']['saved'],'ui_clean':sample['ui_clean']}
            checks.update(target_checks(o.target,state,o.player))
            return {'status':'owned_pet_attack_shape_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'rejection':rejection,
                    'native_pet':copy.deepcopy(o.pet),'native_target':copy.deepcopy(o.target),'public':sample,
                    'state':state,'frame':frame,'wire_layout_inferred':False,'qualification_added':False}}
        require(t.step('diagnostic.pet_attack.request','Click the separately reviewed owned stock Attack button once.',
            {'attack':{'kind':'click','value':point,'hold':.4}},outcome,diagnostic_action='attack'),
            'owned_pet_attack_shape_capture_pass')
    finally:restore(t,o,inventory,old,fixture,d['original_spell'],d['original_position'])
    t.receipt.update(completed=True,phase='owned_pet_attack_shape_capture_complete',qualified_scope=
        'One actual owned stock Attack request and selected passive dummy identity, healthy refusal and no native '
        'command, followed by ordinary Follow/Assist and full fixture/aura/vitals restoration. Native Attack remains open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','run'])
    for n in ('preparation','entry','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--stage',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='run' and (a.stage is None or a.review is None):p.error('run requires closed staging and a fresh review')
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='stage':stage(t,a.preparation,a.entry)
            else:run(t,a.preparation,a.entry,a.stage,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
