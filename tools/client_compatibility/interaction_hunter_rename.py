"""Open the normal owned Hunter rename dialog; confirmation is a separate step."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_pet_recon import starting_wolf,saved_pet_unchanged,pet_frame_menu
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import PetOracle
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .observation.inventory import Inventory
from .world.objects import INDEX


def menu_source(t,path,session):
    e=closed(path)
    if (e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or
        e.get('native_session')!=session or e.get('phase')!='hunter_pet_menu_recon' or
        e.get('fixture_source')!=t.receipt['fixture_source'] or
        len(e.get('checks',{}))!=6 or not all(e['checks'].values()) or
        len(e.get('restoration_checks',{}))!=13 or not all(e['restoration_checks'].values()) or
        set(e.get('pet_menu',{}).get('checks',{}))!={'owned_menu_title','player_menu_absent','stock_rename_visible'} or
        not all(e['pet_menu']['checks'].values())):
        raise RuntimeError('requires the complete same-entry owned Hunter Rename menu')
    return e


def open_dialog(t,preparation,entry,menu):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);m=menu_source(t,menu,session)
    if (t.fixture['guid'],t.fixture['character_name'],t.fixture['class'],t.fixture['level'])!=(6,'Harnesshunt',3,10):
        raise RuntimeError('requires the exact normally controlled Hunter')
    since=min(p['time'] for p in e['login_packets']);o=Presence(session,6,since).poll()
    retained=pets(6);inv=Inventory(lab.ROOT,session,6).poll();before=resources(inv);before_saved=saved(6)
    if (not starting_wolf(retained,6) or not o.present() or o.pet['guid']!=m['native_pet']['guid'] or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=4 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255!=3):
        raise RuntimeError('owned starting Wolf has no native rename/abandon authority')
    initial,_=t.observe('hunter_rename_before');t.clean_panels()
    t.receipt.update(native_session=session,source={'path':str(menu.resolve()),'sha256':lab.sha256(menu)},
        native_pet=o.pet,retained_pet=retained,baseline_resources=before,baseline_saved=before_saved,
        initial_target=initial.get('target',{}),rename_confirmation_sent=False,
        qualified_scope='Normal owned Hunter Rename dialog staging only; no rename confirmation or qualification.')
    t.persist()
    try:
        t.execute({'kind':'chat','value':'/target pet'});state,_=t.observe('hunter_rename_pet_target')
        oracle=PetOracle(session,6,since).poll();guid=expected_guid(o.pet)
        if state.get('target',{}).get('guid')!=guid or oracle.selected()!=o.pet['guid']:
            raise RuntimeError('normal owned Wolf selection differs')
        pet_frame_menu(t,oracle,guid)
        require(click_case(t,'diagnostic.hunter_rename.open','Open the observed owned Wolf Rename control.',
            lambda c:c.get('text')=='Rename' and c.get('enabled') is True,
            lambda b,a,s:{'status':'hunter_rename_dialog_pass' if s and
                any(p.startswith('StaticPopup') for p in a.get('panels',[])) and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'}),
            'hunter_rename_dialog_pass')
        state,frame=t.observe('hunter_rename_dialog');rows=controls(t);after_pets=pets(6)
        checks={'resources':resources(inv.poll())==before,'saved_rows':saved(6)==before_saved,
            'pet_rows':saved_pet_unchanged(retained,after_pets,time.time()),
            'position':state['world_position']==initial['world_position'],
            'edit_visible':len(state.get('edit_fields',[]))==1,
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(state=state,frame=frame,dialog_controls=rows,dialog_checks=checks,protected_checks=protected(old))
        t.persist()
        if not all(checks.values()):raise RuntimeError('owned normal Rename dialog staging differs')
        t.receipt.update(completed=True,phase='hunter_rename_dialog_open')
    except Exception:
        t.clean_panels()
        if initial.get('target',{}).get('name')=='Benjamin Foxworthy':
            t.execute({'kind':'chat','value':'/targetexact Benjamin Foxworthy'})
        elif not initial.get('target',{}).get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','menu','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:open_dialog(t,a.preparation,a.entry,a.menu)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
