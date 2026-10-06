"""Probe one stock owned-Imp dismissal and restore the retained pet normally."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import prepared,origin_checks,saved,pets,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_target import PetOracle,pair,source,read_menu
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import detail
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.native_objects import records
from .world.objects import INDEX


class Presence:
    def __init__(self,session,owner,started):
        self.session,self.owner,self.started=session,owner,started
        self.cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
        self.player={};self.pet=None;self.removed=set();self.requests=[]

    def poll(self):
        for p in self.cursor.poll():
            if p.get('session')!=self.session or p.get('time',0)<self.started:continue
            if p.get('name') in ('CMSG_PET_ACTION','CMSG_PET_ABANDON'):self.requests.append(p)
            if p.get('direction')!='from_native':continue
            if p.get('name')=='SMSG_DESTROY_OBJECT':
                self.removed.add(struct.unpack_from('<Q',bytes.fromhex(p['body']))[0])
            if p.get('name')!='SMSG_UPDATE_OBJECT':continue
            for r in records(bytes.fromhex(p['body'])):
                fields=r.get('fields',{})
                if r.get('guid')==self.owner:self.player.update(fields)
                if r.get('kind')==3 and r['guid']>>52==0xf14 and pair(fields,'UNIT_FIELD_SUMMONEDBY')==self.owner:
                    self.pet=r
                elif self.pet and r.get('guid')==self.pet['guid']:self.pet['fields'].update(fields)
                self.removed.update(r.get('removed',[]))
        return self

    def present(self):
        return bool(self.pet and self.pet['guid'] not in self.removed and
            pair(self.player,'UNIT_FIELD_SUMMON')==self.pet['guid'])


def vitals(oracle):
    names=('UNIT_FIELD_HEALTH','UNIT_FIELD_MAXHEALTH','UNIT_FIELD_POWER1','UNIT_FIELD_MAXPOWER1')
    if any(INDEX[name] not in oracle.player for name in names):raise RuntimeError('owned native vitals are incomplete')
    return {name:oracle.player[INDEX[name]] for name in names}


def dismiss_checks(oracle,guid,since,state,selected):
    requests=[p for p in oracle.requests if p['time']>=since]
    modern=[p for p in requests if p['name']=='CMSG_PET_ACTION' and p['direction']=='from_client']
    native=[p for p in requests if p['name']=='CMSG_PET_ACTION' and p['direction']=='to_native']
    expected=struct.pack('<QIQfff',guid,0x07000003,0,0,0,0).hex()
    return {'ordinary_dismiss':selected,'one_modern_request':len(modern)==1,
        'one_native_dismiss':len(native)==1 and native[0]['body']==expected,
        'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in requests),
        'native_pet_removed':guid in oracle.removed,'native_summon_cleared':pair(oracle.player,'UNIT_FIELD_SUMMON')==0,
        'public_target_cleared':not state['target'].get('exists'),
        'menu_closed':'ContextMenu' not in state.get('panels',[]),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')},requests


def public_pet(t,label):
    require(click_case(t,'fixture.pet_dismiss.book_'+label,'Open the stock book for passive pet presence.',
        lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
            'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}),'spellbook_open_pass')
    probe=detail(t,label);t.clean_panels();return probe['pet']


def suite(t,preparation,entry,probe,menu):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry);m=closed(menu)
    restore={'original_character','original_saved_rows','native_worldserver','empty_selection',
        'resources','saved_rows','position','panels_closed','ui_clean'}
    if (m.get('phase')!='owned_pet_target_menu_recon_complete' or m.get('actor')!=t.fixture or
        m.get('runtime')!=t.receipt['runtime'] or m.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        m.get('sources')!=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)] or
        set(m.get('restoration_checks',{}))!=restore or not all(m['restoration_checks'].values()) or
        len([c for c in m['pet_menu']['controls'] if c.get('text')=='Dismiss' and c.get('enabled') and
            c.get('kind')=='Button'])!=1):
        raise RuntimeError('requires the closed same-entry owned stock dismiss menu')
    base=PetOracle(session,t.fixture['guid'],e['started_at']).poll()
    o=Presence(session,t.fixture['guid'],e['started_at']).poll()
    inventory=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    retained=pets(t.fixture['guid']);guid=base.pet['guid'];expected=p['public_pet']['guid']
    if (not o.present() or o.pet['guid']!=guid or base.selected()!=0 or resources(inventory)!=e['resources'] or
        saved(t.fixture['guid'])!=e['entered_saved'] or len(retained)!=1 or
        (retained[0]['id'],retained[0]['entry'],retained[0]['owner'],retained[0]['name'])!=(1,416,4,'Volrot') or
        [688,1,0] not in e['entered_saved']['spells']):
        raise RuntimeError('owned retained pet or known normal recovery spell differs')
    before,frame=t.observe('dismiss_baseline')
    baseline_vitals=vitals(o)
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe,menu)],
        native_session=session,retained_pet_before=retained,native_pet_before=base.pet,before_frame=frame,
        native_vitals_before=baseline_vitals,
        qualified_scope='One stock Imp dismissal. Normal summon is cleanup only; no summon qualification yet.')
    t.persist()
    try:
        t.execute({'kind':'chat','value':'/targetexact '+p['public_pet']['name']})
        state,_=t.observe('owned_pet_before_menu');base.poll()
        if state['target'].get('guid')!=expected or base.selected()!=guid:raise RuntimeError('owned target differs')
        read_menu(t,base,expected)
        since=time.time();t.receipt['dismiss_started_at']=since;t.persist()
        def outcome(b,a,selected):
            o.poll();checks,requests=dismiss_checks(o,guid,since,a,selected)
            return {'status':'native_owned_pet_dismiss_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests}}
        require(click_case(t,'pets.dismiss','Dismiss the owned summoned Imp through its stock menu.',
            lambda c:c['kind']=='Button' and c.get('text')=='Dismiss',outcome,
            await_state=lambda a:'ContextMenu' not in a.get('panels',[])),'native_owned_pet_dismiss_pass')
        pet=public_pet(t,'dismissed_pet')
        t.receipt['dismissed_public_pet']=pet;t.persist()
        if pet.get('exists'):raise RuntimeError('public owned pet remains after native dismissal')
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
            if not o.present():raise RuntimeError('normal retained Imp recovery did not complete')
        state,_=t.observe('dismiss_cleanup_before')
        if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels();public=public_pet(t,'restored_pet');state,frame=t.observe('dismiss_cleanup_complete');o.poll()
        fields=o.pet['fields'];current=pets(t.fixture['guid'])
        pet_guid=o.pet['guid'];public_guid=f"Pet-0-1-{o.pet['map']}-0-{pet_guid>>32&0xfffff}-{pet_guid&0xffffffff:010X}"
        identity={k:retained[0][k] for k in ('id','entry','owner','name','CreatedBySpell','PetType')}
        checks=origin_checks(old);checks.update(empty_selection=pair(o.player,'UNIT_FIELD_TARGET')==0 and not state['target']['exists'],
            resources=resources(inventory)==e['resources'],saved_rows=saved(t.fixture['guid'])==e['entered_saved'],
            position=state['world_position']==before['world_position'],panels_closed=not state.get('panels') and not state.get('bags'),
            ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'),owned_pet=o.present() and
                pair(fields,'UNIT_FIELD_SUMMONEDBY')==t.fixture['guid'] and fields.get(INDEX['UNIT_FIELD_PETNUMBER'])==1,
            native_vitals=vitals(o)==baseline_vitals,
            public_pet=public.get('exists') is True and public.get('guid')==public_guid and public.get('name')==identity['name'],
            retained_pet=len(current)==1 and all(current[0].get(k)==v for k,v in identity.items()))
        t.receipt.update(restoration_checks=checks,restored_frame=frame,restored_public_pet=public,
            retained_pet_after=current,native_pet_after=o.pet,native_vitals_after=vitals(o));t.persist()
        if not all(checks.values()):raise RuntimeError('owned pet dismiss restoration differs')
    t.receipt.update(completed=True,phase='owned_pet_dismiss_complete')


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
