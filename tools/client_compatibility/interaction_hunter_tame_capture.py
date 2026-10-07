"""Capture one reviewed ordinary Tame Beast on a staged existing wild wolf."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source,wire_known
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound,pet_identity
from .interaction_pet_dismiss import Presence,public_pet,vitals
from .interaction_pet_target import pair
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import detail,navigate
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_observation import read_page
from .observation.inventory import Inventory
from .observation.journal import entries
from .observation.transport import Observer
from .world.buffer import Reader
from .world.native_objects import guid as native_guid
from .world.objects import INDEX
from .world.native_objects import records
from .interaction_hunter_tame_stage import pose


class TamePresence(Presence):
    """EffectTameCreature adds the new pet to the map before SetMinion links it."""
    def __init__(self,*args):
        super().__init__(*args);self.tame_candidates={}

    def inspect_packet(self,p):
        if p.get('direction')!='from_native' or p.get('name')!='SMSG_UPDATE_OBJECT':return
        for r in records(bytes.fromhex(p['body'])):
            f=r.get('fields',{});g=r.get('guid')
            if (r.get('kind')==3 and g>>52==0xf14 and
                pair(f,'UNIT_FIELD_CREATEDBY')==self.owner and f.get(INDEX['UNIT_FIELD_PETNUMBER'],0)):
                self.tame_candidates[g]=r
            elif r.get('update_type')==0 and g in self.tame_candidates:
                self.tame_candidates[g]['fields'].update(f)

    def poll(self):
        super().poll();current=pair(self.player,'UNIT_FIELD_SUMMON')
        pet=self.tame_candidates.get(current)
        if (pet and current not in self.removed and
            pair(pet['fields'],'UNIT_FIELD_CREATEDBY')==self.owner and
            pair(pet['fields'],'UNIT_FIELD_SUMMONEDBY')==self.owner):self.pet=pet
        return self


def tame_caption(t,session):
    known=wire_known(t,session)
    if 1515 not in known:raise RuntimeError('ordinary native Tame Beast1515 is not known')
    read_page(t,'tame_book_core','state','/tcui');t.clean_panels()
    require(click_case(t,'fixture.tame.book','Open the stock book for the exact Tame Beast caption.',
        lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
        'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},hold=.4),'spellbook_open_pass')
    try:
        tabs=detail(t,'tame_book_tabs')['tabs']
        for tab in sorted(tabs,key=lambda r:r.get('name')!='Beast Mastery'):
            if tab.get('hidden') or tab.get('guild'):continue
            line=tab['index']
            require(navigate(t,known,'fixture.tame.line'+str(line),
                'SpellBookSkillLineTab'+str(line),line=line,check_content=False),'spellbook_navigation_pass')
            for page in range(3):
                p=detail(t,'tame_book_page'+str(line)+'_'+str(page),line=line)
                rows=[r for r in p['rows'] if r.get('id')==1515 and r.get('kind')=='SPELL' and
                    r.get('known') is True and r.get('name')=='Tame Beast']
                if len(rows)==1:return rows[0]
                if p.get('page',0)>=p.get('max_pages',0):break
                require(navigate(t,known,'fixture.tame.next'+str(line)+'_'+str(page),
                    'SpellBookNextPageButton',page=p['page']+1,check_content=False),'spellbook_navigation_pass')
        raise RuntimeError('known Tame Beast1515 is absent from bounded stock pages')
    finally:t.clean_panels()


def target(t,staged,session,started):
    state,frame=t.observe('tame_target_before');o=Observer(guid=6,session=session);facts=o.poll()
    selected=facts.get('selected_unit');p=TamePresence(session,6,started).poll()
    if (not selected or selected['guid']!=staged['native_target']['guid'] or
        selected['health']!=selected['max_health'] or state.get('target',{}).get('name')!='Young Wolf' or
        state['target'].get('visible') is not True or state['world_position']!=staged['state']['world_position'] or
        state.get('panels') or state.get('lua_errors') or state.get('blocked_actions') or
        p.present() or pair(p.player,'UNIT_FIELD_SUMMON')):
        raise RuntimeError('exact staged living wild wolf or no-pet baseline differs')
    return state,frame,p


def settle(t,old,entered,staged,session,failed_path,pose_path):
    path=failed_path.resolve();f=json.loads(path.read_text());p=closed(pose_path)
    if (failed_path.is_symlink() or path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or
        f.get('completed') is not False or not f.get('finished_at') or f.get('input_sent') is not True or
        f.get('failure')!='RuntimeError: one ordinary Tame Beast produced no owned native pet' or
        f.get('actor')!=t.fixture or f.get('runtime')!=t.receipt['runtime'] or f.get('native_session')!=session or
        f.get('staging_source')!=t.receipt['staging_source'] or
        len(f.get('native_cast_requests',[]))!=1 or f['native_cast_requests'][0]['spell']!=1515 or
        len(f.get('native_completions',[]))!=1 or
        f['native_completions'][0]['counter']!=f['native_cast_requests'][0]['counter'] or
        p.get('phase')!='owned_tame_pose_restored' or p.get('runtime')!=t.receipt['runtime'] or
        p.get('stage_source')!=t.receipt['staging_source'] or
        len(p.get('pose_restoration',{}).get('checks',{}))!=8 or not all(p['pose_restoration']['checks'].values())):
        raise RuntimeError('requires the closed single-Tame observation failure and exact staged pose cleanup')
    o=TamePresence(session,6,entered['started_at']).poll();current=pets(6)
    if not o.present():raise RuntimeError('late native tame ownership is not currently complete')
    fields=o.pet['fields'];number=fields.get(INDEX['UNIT_FIELD_PETNUMBER']);new=[r for r in current if r['id']==number]
    retained=[r for r in current if r['id']==4]
    if len(current)!=2 or len(new)!=1 or number==4:
        raise RuntimeError('one separately tamed test pet and stored Harnesswolf required')
    t.receipt.update(failed_source=bound(failed_path),pose_restoration_source=bound(pose_path),
        native_session=session,tame_input_replayed=False,input_sent=False,qualification_added=False,
        native_pet=o.pet,retained_pet_before=current);t.persist()
    public=public_pet(t,'late_owned_tame_public_pet');read_page(t,'late_owned_tame_core','state','/tcui')
    state,frame=t.observe('late_owned_tame_settled');inv=Inventory(lab.ROOT,session,6).poll()
    expected=f"Pet-0-1-{o.pet['map']}-0-299-{o.pet['guid']&0xffffffff:010X}"
    checks={'native_late_owner':pair(fields,'UNIT_FIELD_SUMMONEDBY')==pair(fields,'UNIT_FIELD_CREATEDBY')==6,
        'native_current_summon':pair(o.player,'UNIT_FIELD_SUMMON')==o.pet['guid'],
        'native_level10_wolf':fields.get(INDEX['OBJECT_FIELD_ENTRY'])==299 and fields.get(INDEX['UNIT_FIELD_LEVEL'])==10,
        'normal_saved_tame':tuple(new[0][k] for k in ('owner','entry','CreatedBySpell','PetType','level','slot','active'))==
            (6,299,13481,1,10,0,1),
        'stored_Harnesswolf':pet_identity(f['baseline_pets'],retained,5,0),
        'public_owned_wolf':public.get('exists') is True and public.get('name')=='Wolf' and public.get('guid')==expected,
        'resources':resources(inv)==staged['baseline_resources'],'saved_rows':saved(6)==staged['baseline_saved'],
        'native_pose_returned':pose()==p['pose_restoration']['restored'],
        'living_idle_owner':not frame['movement']['dead'] and not frame['movement']['in_combat'] and
            frame['movement']['health_percent']==100,
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
    t.receipt.update(public_pet=public,frame=frame,state=state,settling_checks=checks,
        retained_pet_after=pets(6));t.persist()
    if not all(checks.values()):raise RuntimeError('source-bound late tame ownership/public reconciliation differs')
    t.receipt.update(completed=True,phase='owned_tame_late_owner_reconciled',
        qualified_scope='Readback after the single failed observation trial, without repeating Tame. '
            'One normally tamed test pet retained; named Harnesswolf remains stored. Failed whole trial stays excluded.')


def run(t,preparation,entry,staging,action,source=None,review_path=None,pose_path=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);staged=closed(staging)
    if (staged.get('phase')!='owned_existing_wolf_staged' or staged.get('actor')!=t.fixture or
        staged.get('runtime')!=t.receipt['runtime'] or staged.get('native_session')!=session or
        staged.get('fixture_source')!=bound(preparation) or staged.get('entry_source')!=bound(entry) or
        len(staged.get('stage_checks',{}))!=13 or not all(staged['stage_checks'].values())):
        raise RuntimeError('requires the complete same-runtime existing wolf staging')
    t.receipt.update(staging_source=bound(staging),entry_source=bound(entry));t.persist()
    if action=='settle':
        settle(t,old,entered,staged,session,source,pose_path);return
    inv=Inventory(lab.ROOT,session,6).poll();retained=pets(6)
    if (not pet_identity(staged['retained_pet_before'],retained,5,0) or
        resources(inv)!=staged['baseline_resources'] or saved(6)!=staged['baseline_saved']):
        raise RuntimeError('stored Harnesswolf or owner baseline differs before Tame Beast')
    t.receipt.update(native_session=session,staging_source=bound(staging),entry_source=bound(entry),
        baseline_pets=retained,baseline_resources=resources(inv),baseline_saved=saved(6),
        qualification_added=False,input_sent=False);t.persist()
    if action=='recon':
        spell=tame_caption(t,session);read_page(t,'tame_recon_core','state','/tcui')
        state,frame,o=target(t,staged,session,entered['started_at'])
        t.receipt.update(tame_spell=spell,state=state,frame=frame,native_vitals_before=vitals(o),
            protected_checks=protected(old),completed=True,phase='await_owned_tame_cast_review');return
    recon=closed(source)
    if (recon.get('phase')!='await_owned_tame_cast_review' or recon.get('runtime')!=t.receipt['runtime'] or
        recon.get('actor')!=t.fixture or recon.get('staging_source')!=bound(staging) or
        recon.get('native_session')!=session or recon.get('tame_spell',{}).get('id')!=1515 or
        recon['tame_spell'].get('name')!='Tame Beast' or len(recon.get('protected_checks',{}))!=5 or
        not all(recon['protected_checks'].values())):
        raise RuntimeError('requires the closed observed Tame Beast caption and staged target')
    d=reviewed(t,review_path,'Tame Beast')
    if d.get('source')!=bound(source) or d.get('frame')!=recon['frame']:
        raise RuntimeError('Tame Beast review differs from the exact current target frame')
    before,_,o=target(t,staged,session,entered['started_at'])
    t.receipt.update(recon_source=bound(source),tame_spell=recon['tame_spell'],native_vitals_before=vitals(o),
        ordinary_input={'kind':'chat','value':'/cast '+recon['tame_spell']['name']},cast_started_at=time.time())
    t.persist()
    with t.bounded_combat_observation(60):
        t.receipt['input_sent']=True;t.persist();t.execute(t.receipt['ordinary_input'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            o.poll()
            if o.present():break
            time.sleep(.25)
        after,frame=t.observe('tame_outcome');o.poll()
    until=time.time();since=t.receipt['cast_started_at']
    packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if
        p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in
        ('CMSG_CAST_SPELL','SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED','SMSG_SPELL_FAILURE',
         'SMSG_SPELL_FAILED_OTHER','SMSG_SPELL_PREPARE','SMSG_UPDATE_OBJECT','SMSG_DESTROY_OBJECT',
         'SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE')]
    events=[p for p in entries(lab.ROOT/'logs/modern_world.jsonl') if
        p.get('session')==session and since<=p.get('time',0)<=until and
        (p.get('name') in ('MSG_CHANNEL_START','MSG_CHANNEL_UPDATE','SMSG_PET_ADDED',
            'SMSG_SPELL_CHANNEL_START','SMSG_SPELL_CHANNEL_UPDATE') or
         p.get('event') in ('cast_translation_rejected','native_world_failed'))]
    native=[p for p in packets if p['direction']=='to_native' and p['name']=='CMSG_CAST_SPELL']
    decoded=[]
    for p in native:
        r=Reader(bytes.fromhex(p['body']));count,spell=r.unpack('Bi');decoded.append({'counter':count,'spell':spell})
    go=[]
    for p in packets:
        if p['direction']=='from_native' and p['name']=='SMSG_SPELL_GO':
            r=Reader(bytes.fromhex(p['body']));caster=native_guid(r);native_guid(r);count,spell=r.unpack('Bi')
            if caster==6 and spell==1515:go.append({'packet':p,'caster':caster,'counter':count,'spell':spell})
    t.receipt.update(cast_packets=packets,channel_pet_events=events,native_cast_requests=decoded,
        native_completions=go,outcome_state=after,outcome_frame=frame,native_pet_after=o.pet,
        native_pet_present=o.present(),native_vitals_after=vitals(o),retained_pet_after=pets(6));t.persist()
    # Capture first, then judge. A failed trial never retries the Tame input.
    if not o.present():raise RuntimeError('one ordinary Tame Beast produced no owned native pet')
    lab.server_command('saveall');time.sleep(.5);current=pets(6)
    public=public_pet(t,'tame_public_pet');read_page(t,'tame_after_core','state','/tcui')
    fields=o.pet['fields'];new=[p for p in current if p['id']!=4];retained_after=[p for p in current if p['id']==4]
    checks={'one_native_tame_request':len(decoded)==1 and decoded[0]['spell']==1515,
        'native_cast_completion':len(go)==1 and go[0]['counter']==decoded[0]['counter'] if decoded else False,
        'native_tamed_pet':o.present() and pair(fields,'UNIT_FIELD_SUMMONEDBY')==6 and
            fields.get(INDEX['OBJECT_FIELD_ENTRY'])==299 and fields.get(INDEX['UNIT_FIELD_LEVEL'])==10,
        'normal_tamed_saved_row':len(new)==1 and tuple(new[0][k] for k in
            ('owner','entry','CreatedBySpell','PetType','level','slot','active'))==(6,299,13481,1,10,0,1),
        'retained_Harnesswolf':pet_identity(retained,retained_after,5,0),
        'public_tamed_pet':public.get('exists') is True and public.get('name')=='Wolf' and
            public.get('guid')==f"Pet-0-1-{o.pet['map']}-0-299-{o.pet['guid']&0xffffffff:010X}",
        'resources':resources(inv)==staged['baseline_resources'],'saved_rows':saved(6)==staged['baseline_saved'],
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions'),**protected(old)}
    t.receipt.update(capture_checks=checks,public_pet=public,retained_pet_after=current,
        phase='owned_tame_native_outcome_captured',qualified_scope='One ordinary Tame Beast capture only. '
        'The separate test pet is retained for occupied-slot diagnostics; whole restoration and public channel remain open.')
    t.persist()
    if not all(checks.values()):raise RuntimeError('native or public Tame Beast capture differs')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['recon','cast','settle'])
    for k in ('preparation','entry','staging','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--pose-restoration',type=Path);a=p.parse_args()
    if a.action=='cast' and (not a.source or not a.review):p.error('requires a closed caption recon and fresh image review')
    if a.action=='settle' and (not a.source or not a.pose_restoration):p.error('requires a failed single-Tame and closed pose restoration')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.staging,a.action,a.source,a.review,a.pose_restoration)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','capture_checks')}),flush=True)
