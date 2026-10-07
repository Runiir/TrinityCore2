"""Stage or cancel ordinary Abandon for the source-bound disposable Wolf."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_pet_recon import pet_frame_menu
from .hunter_pair_identity import identities
from .interaction_hunter_stable_slots import bound
from .interaction_pet_dismiss import Presence,public_pet
from .interaction_pet_target import PetOracle,pair
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_operations import controls,click_case,point
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .hunter_disposable_tame import deployed_number,pair_preserved


def disposable_pair(rows):
    return len(rows)==2 and sorted(tuple(r.get(k) for k in
        ('id','owner','entry','name','renamed','slot','active','CreatedBySpell')) for r in rows)==[
            (4,6,42717,'Harnesswolf',1,5,0,883),(6,6,299,'Wolf',0,0,1,883)]


def primary_absent():
    with actor('primary'):return lab.owned_process('client') is None


def dialog(state):
    rows=state.get('pet_popups',[])
    return len(rows)==1 and rows[0].get('which')=='ABANDON_PET' and rows[0].get('name') in (
        'StaticPopup1','StaticPopup2','StaticPopup3') and bool(rows[0].get('text'))


def events(session,since,until):
    return [p for p in entries(lab.ROOT/'logs/modern_world.jsonl') if p.get('session')==session and
        since<=p.get('time',0)<=until and p.get('name')=='CMSG_PET_ABANDON']


def run(t,preparation,entry,action,source=None,review_path=None,tame_source=None,deployment=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);retained=pets(6)
    number=deployed_number(t,tame_source,retained,deployment) if tame_source else 6
    frozen=pair_preserved if tame_source else identities
    valid_pair=lambda rows: deployed_number(t,tame_source,rows,deployment)==number if tame_source else disposable_pair(rows)
    if (t.fixture['guid'],t.fixture['class'],t.fixture['level'])!=(6,3,10) or not valid_pair(retained):
        raise RuntimeError(f'requires disposable Wolf{number} active and named Harnesswolf4 stored5')
    if not frozen(old['retained_class_pets'],retained) or not primary_absent():
        raise RuntimeError('frozen pair or user-requested primary absence differs')
    o=Presence(session,6,e['started_at']).poll();inv=Inventory(lab.ROOT,session,6).poll()
    if (not o.present() or o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=number or
        o.pet['fields'].get(INDEX['OBJECT_FIELD_ENTRY'])!=299 or
        pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=6 or
        resources(inv)!=e['resources'] or saved(6)!=e['entered_saved']):
        raise RuntimeError(f'current runtime pet{number} or owner baseline differs')
    t.receipt.update(native_session=session,entry_source=bound(entry),native_pet=o.pet,
        retained_pet_before=retained,baseline_resources=resources(inv),baseline_saved=saved(6),
        input_sent=False,qualification_added=False,abandon_confirmation_sent=False)
    if tame_source:t.receipt.update(disposable_tame_source=bound(tame_source),disposable_pet_number=number)
    t.persist()
    if action=='stage':
        t.clean_panels();initial,_=t.observe('test_pet_abandon_before')
        if initial.get('observer_version')!=145 or initial.get('pet_popups'):
            raise RuntimeError('requires passive popup observer145 and no existing pet dialog')
        t.receipt.update(initial_target=initial['target'],initial_position=initial['world_position'])
        t.persist();t.execute({'kind':'chat','value':'/target pet'})
        state,_=t.observe('test_pet_abandon_selected');oracle=PetOracle(session,6,e['started_at']).poll()
        guid=expected_guid(o.pet)
        if state['target'].get('guid')!=guid or oracle.selected()!=o.pet['guid']:
            raise RuntimeError(f'ordinary selected disposable Wolf{number} differs')
        pet_frame_menu(t,oracle,guid,name='Wolf',rename_allowed=True)
        if len([c for c in t.receipt['pet_menu']['controls'] if c.get('text')=='Abandon' and c.get('enabled')])!=1:
            raise RuntimeError('requires one observed stock Wolf Abandon menu control')
        t.receipt['input_sent']=True;t.persist()
        require(click_case(t,'diagnostic.test_pet.abandon_open',f'Open Abandon for the disposable Wolf{number}.',
            lambda c:c.get('text')=='Abandon' and c.get('enabled') is True,
            lambda b,a,s:{'status':'test_pet_abandon_dialog_pass' if s and dialog(a) and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'},
            hold=.4),'test_pet_abandon_dialog_pass')
        state,frame=t.observe('test_pet_abandon_dialog');rows=controls(t);o.poll()
        popup=state['pet_popups'][0]['name']
        buttons=[c for c in rows if c.get('name') in (popup+'Button1',popup+'Button2') and c.get('enabled')]
        checks={'exact_disposable_pair':valid_pair(pets(6)) and frozen(retained,pets(6)),
            'native_test_pet_present':o.present(),'dialog':dialog(state),
            'stock_okay_cancel':sorted(c['text'] for c in buttons)==['Cancel','Okay'],
            'no_abandon_request':not events(session,t.receipt['started_at'],time.time()),
            'resources':resources(inv.poll())==e['resources'],'saved_rows':saved(6)==e['entered_saved'],
            'position':state['world_position']==initial['world_position'],
            'primary_absent':primary_absent(),'protected_actors':all(protected(old).values()),
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(state=state,frame=frame,dialog_controls=buttons,checks=checks,
            retained_pet_after=pets(6),completed=all(checks.values()),phase='owned_test_pet_abandon_dialog')
        if not all(checks.values()):raise RuntimeError('disposable Wolf Abandon dialog differs')
        return
    stage=closed(source)
    if (stage.get('phase')!='owned_test_pet_abandon_dialog' or stage.get('actor')!=t.fixture or
        stage.get('runtime')!=t.receipt['runtime'] or stage.get('fixture_source')!=bound(preparation) or
        stage.get('entry_source')!=bound(entry) or stage.get('native_session')!=session or
        stage.get('native_pet',{}).get('guid')!=o.pet['guid'] or
        len(stage.get('checks',{}))!=11 or not all(stage['checks'].values()) or
        (tame_source and stage.get('disposable_tame_source')!=bound(tame_source))):
        raise RuntimeError(f'requires whole same-entry disposable Wolf{number} Abandon dialog')
    d=reviewed(t,review_path,'Cancel Abandon')
    button=next(c for c in stage['dialog_controls'] if c['text']=='Cancel')
    if d.get('source')!=bound(source) or d.get('frame')!=stage['frame'] or d['point']!=point(button):
        raise RuntimeError('fresh stock Abandon Cancel review differs')
    before,_=t.observe('test_pet_abandon_cancel_before')
    if not dialog(before) or before['pet_popups']!=stage['state']['pet_popups']:
        raise RuntimeError('current disposable-pet dialog differs')
    t.receipt.update(source=bound(source),ordinary_input={'kind':'click','value':d['point'],'hold':.4},input_sent=True)
    t.persist();t.execute(t.receipt['ordinary_input']);state,frame=t.observe('test_pet_abandon_cancel_after')
    public=public_pet(t,'test_pet_abandon_cancel_public');initial=stage['initial_target']
    if not initial.get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
    elif initial.get('name')=='Erma':t.execute({'kind':'chat','value':'/targetexact Erma'})
    elif initial.get('guid')==expected_guid(o.pet):t.execute({'kind':'chat','value':'/target pet'})
    else:raise RuntimeError('Abandon Cancel original target has no ordinary restoration')
    state,frame=t.observe('test_pet_abandon_cancel_restored');o.poll()
    checks={'dialog_closed':not state.get('pet_popups') and not state.get('panels'),
        'no_abandon_request':not events(session,stage['started_at'],time.time()),
        'native_test_pet_present':o.present() and o.pet['guid']==stage['native_pet']['guid'],
        'public_test_pet_present':public.get('exists') is True and public.get('guid')==expected_guid(o.pet),
        'complete_pair_preserved':frozen(stage['retained_pet_before'],pets(6)),
        'resources':resources(inv.poll())==e['resources'],'saved_rows':saved(6)==e['entered_saved'],
        'position':state['world_position']==stage['initial_position'],
        'target_restored':state['target'].get('guid')==initial.get('guid'),
        'primary_absent':primary_absent(),'protected_actors':all(protected(old).values()),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(state=state,frame=frame,public_pet=public,checks=checks,retained_pet_after=pets(6),
        completed=all(checks.values()),phase='owned_test_pet_abandon_cancelled')
    if not all(checks.values()):raise RuntimeError(f'ordinary Wolf{number} Abandon Cancel preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','cancel'])
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path);p.add_argument('--tame-source',type=Path)
    p.add_argument('--deployment',type=Path);a=p.parse_args()
    if a.action=='cancel' and (not a.source or not a.review):p.error('cancel requires whole dialog and fresh review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.action,a.source,a.review,a.tame_source,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
