"""Summon the retained trained Imp once from confirmed native/public absence."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_target import PetOracle,pair,source,read_menu,retained_imp
from .interaction_pet_dismiss import Presence,vitals,dismiss_checks,dismiss_ready,public_pet,recovery_spell
from .interaction_pet_control_training import protected
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .pet_packet_identity import cast_identity
from .world.native_objects import records
from .world.objects import INDEX


class SummonOracle(Presence):
    def __init__(self,session,owner,started):
        super().__init__(session,owner,started)
        self.casts=[];self.creations={}

    def inspect_packet(self,packet):
        if packet.get('name') in ('CMSG_CAST_SPELL','SMSG_SPELL_GO','SMSG_CAST_FAILED'):
            self.casts.append(packet)
        if packet.get('direction')=='from_native' and packet.get('name')=='SMSG_UPDATE_OBJECT':
            for row in records(bytes.fromhex(packet['body'])):
                if (row.get('kind')==3 and row['guid']>>52==0xf14 and
                        pair(row.get('fields',{}),'UNIT_FIELD_SUMMONEDBY')==self.owner):
                    self.creations[row['guid']]=packet['time']


def summon_checks(oracle,since,old_guid,retained,selected,absence):
    packets=[p for p in oracle.casts if p['time']>=since]
    parsed=[(p,cast_identity(p)) for p in packets];parsed=[(p,row) for p,row in parsed if row]
    modern=[row for p,row in parsed if p['name']=='CMSG_CAST_SPELL' and p['direction']=='from_client']
    native=[row for p,row in parsed if p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native']
    counter=native[0]['counter'] if len(native)==1 else None
    completed=[row for p,row in parsed if p['name']=='SMSG_SPELL_GO' and row['spell']==688 and
        row['counter']==counter and row['caster']==row['unit']==oracle.owner]
    failed=[row for p,row in parsed if p['name']=='SMSG_CAST_FAILED' and row['spell']==688]
    pet=oracle.pet;fields=pet['fields'] if pet else {};guid=pet['guid'] if pet else 0
    checks={'ordinary_summon':selected=='summon','confirmed_absence_before_input':absence is True,
        'one_modern_cast':len(modern)==1 and modern[0]['spell']==688,
        'one_native_cast':len(native)==1 and native[0]['spell']==688,
        'matching_native_completion':len(completed)==1 and not failed,
        'new_native_pet':bool(pet and guid!=old_guid and oracle.creations.get(guid,0)>=since),
        'owned_retained_pet':bool(pet and pair(fields,'UNIT_FIELD_SUMMONEDBY')==oracle.owner and
            fields.get(INDEX['UNIT_FIELD_PETNUMBER'])==retained['id'] and guid>>32&0xfffff==416),
        'native_summon_link':oracle.present()}
    return checks,packets


def public_pet_matches(oracle,public,retained):
    pet=oracle.pet
    if not pet:return False
    guid=pet['guid'];expected=f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"
    return public.get('exists') is True and public.get('guid')==expected and public.get('name')==retained['name']


def suite(t,preparation,entry,probe,menu):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry);m=closed(menu)
    restore={'original_character','original_saved_rows','native_worldserver','empty_selection',
        'resources','saved_rows','position','panels_closed','ui_clean'}
    if (t.fixture['guid']!=5 or m.get('phase')!='owned_pet_target_menu_recon_complete' or
        m.get('actor')!=t.fixture or m.get('runtime')!=t.receipt['runtime'] or
        m.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        m.get('sources')!=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)] or
        set(m.get('restoration_checks',{}))!=restore or not all(m['restoration_checks'].values()) or
        len([c for c in m['pet_menu']['controls'] if c.get('text')=='Dismiss' and c.get('enabled') and
            c.get('kind')=='Button'])!=1):
        raise RuntimeError('requires the closed same-entry trained Imp stock menu')
    base=PetOracle(session,5,e['started_at']).poll();o=SummonOracle(session,5,e['started_at']).poll()
    inventory=Inventory(lab.ROOT,session,5).poll();retained=pets(5);identity=retained_imp(t.fixture,retained)
    if (not o.present() or not base.pet or o.pet['guid']!=base.pet['guid'] or base.selected()!=0 or
        resources(inventory)!=e['resources'] or saved(5)!=e['entered_saved'] or
        not p.get('native_control_demon_known') or [80388,1,0] not in e['entered_saved']['spells'] or
        not recovery_spell(e,p) or not all(protected(old).values())):
        raise RuntimeError('trained owned Imp or known normal summon eligibility differs')
    before,frame=t.observe('summon_baseline');baseline_vitals=vitals(o);guid=base.pet['guid']
    if before['target'].get('exists'):raise RuntimeError('requires the original empty selection')
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe,menu)],
        native_session=session,native_pet_before=base.pet,retained_pet_before=retained,
        native_vitals_before=baseline_vitals,before_frame=frame,
        qualified_scope='One ordinary Summon Imp from confirmed absence. Stock Dismiss is fixture preparation only.')
    t.persist()
    try:
        t.execute({'kind':'chat','value':'/targetexact '+p['public_pet']['name']})
        state,_=t.observe('summon_fixture_target');base.poll()
        if state['target'].get('guid')!=p['public_pet']['guid'] or base.selected()!=guid:
            raise RuntimeError('owned fixture pet target differs')
        read_menu(t,base,p['public_pet']['guid']);dismissed_at=time.time()
        def dismissed(b,a,selected):
            o.poll();checks,packets=dismiss_checks(o,guid,dismissed_at,a,selected)
            return {'status':'native_owned_pet_dismiss_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':packets,'fixture_preparation_only':True}}
        require(click_case(t,'fixture.pet_summon.absence','Prepare actual pet absence with one stock Dismiss.',
            lambda c:c['kind']=='Button' and c.get('text')=='Dismiss',dismissed,
            await_state=dismiss_ready),'native_owned_pet_dismiss_pass')
        absent=public_pet(t,'summon_absent_pet');o.poll();state,frame=t.observe('summon_absence_before_cast')
        absence=(absent.get('exists') is False and not o.present() and guid in o.removed and
            pair(o.player,'UNIT_FIELD_SUMMON')==0 and state['target'].get('exists') is False)
        t.receipt.update(absence_checks={'native_and_public_absence':absence},absent_public_pet=absent,
            absence_before_cast_frame=frame,summon_started_at=time.time());t.persist()
        if not absence:raise RuntimeError('native/public pet absence is not proven before cast')
        since=t.receipt['summon_started_at']
        def summoned(b,a,selected):
            o.poll();checks,packets=summon_checks(o,since,guid,identity,selected,absence)
            checks['ui_clean']=not a.get('lua_errors') and not a.get('blocked_actions')
            return {'status':'native_owned_pet_summon_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'packets':packets}}
        require(t.step('pets.summon','Summon the retained Imp once from confirmed absence.',
            {'summon':{'kind':'chat','value':'/cast Summon Imp','description':'Cast the native-known Summon Imp once.'}},
            summoned,diagnostic_action='summon',await_state=lambda a:o.poll().present() and
                not a.get('player_cast',{}).get('active')),'native_owned_pet_summon_pass')
        public=public_pet(t,'summoned_pet');o.poll();t.receipt['summoned_public_pet']=public;t.persist()
        if not public_pet_matches(o,public,identity):raise RuntimeError('summoned native/public pet identity differs')
    finally:
        t.clean_panels();o.poll()
        if not o.present():
            t.receipt['normal_summon_cleanup_sent']=True;t.persist()
            t.execute({'kind':'chat','value':'/cast Summon Imp'})
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            o.poll()
            if o.present() and vitals(o)==baseline_vitals and resources(inventory)==e['resources']:break
            time.sleep(2)
        state,_=t.observe('summon_cleanup_before')
        if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels();public=public_pet(t,'summon_restored_pet');state,frame=t.observe('summon_cleanup_complete');o.poll()
        current=pets(5);identity_keys=('id','entry','owner','name','CreatedBySpell','PetType')
        checks=origin_checks(old);checks.update(empty_selection=pair(o.player,'UNIT_FIELD_TARGET')==0 and
            state['target'].get('exists') is False,resources=resources(inventory)==e['resources'],
            saved_rows=saved(5)==e['entered_saved'],position=state['world_position']==before['world_position'],
            panels_closed=not state.get('panels') and not state.get('bags'),
            ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'),
            owned_pet=o.present() and pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5 and
                o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==identity['id'],
            native_vitals=vitals(o)==baseline_vitals,public_pet=public_pet_matches(o,public,identity),
            retained_pet=len(current)==1 and all(current[0].get(k)==identity[k] for k in identity_keys))
        protected_checks=protected(old)
        t.receipt.update(restoration_checks=checks,protected_checks=protected_checks,restored_frame=frame,
            restored_public_pet=public,native_pet_after=o.pet,retained_pet_after=current,native_vitals_after=vitals(o));t.persist()
        if not all(checks.values()) or not all(protected_checks.values()):
            raise RuntimeError('owned summon restoration or protected fixtures differ')
    t.receipt.update(completed=True,phase='owned_pet_summon_complete')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','probe','menu','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.probe,a.menu)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
