"""Confirm stock Abandon only for the source-bound disposable owned Wolf."""
import argparse,json,time
from contextlib import contextmanager
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_abandon import disposable_pair,primary_absent,dialog
from .hunter_pair_identity import identities
from .hunter_abandon_identity import named_preserved,exact_requests
from .interaction_hunter_stable_slots import bound
from .interaction_pet_dismiss import Presence,public_pet
from .interaction_pet_target import pair
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_operations import point
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.gameobjects import modern_guid
from .world.objects import INDEX
from .hunter_disposable_tame import deployed_number,pair_preserved


@contextmanager
def capture(t,session,guid,number=6,tame_source=None):
    path=lab.ROOT/'run/owned_pet_abandon_probe.json'
    if path.exists():raise RuntimeError('another owned pet Abandon capture is armed')
    started=time.time();config={'schema':'client442_owned_pet_abandon_probe_v1','owner':6,'pet_number':6,
        'session':session,'native_pet_guid':guid,'modern_pet_guid':list(modern_guid(guid,0)),
        'created_at':started,'expires_at':started+90}
    if tame_source:
        config.update(schema='client442_owned_pet_abandon_probe_v2',pet_number=number,
            tame_source={'path':str(tame_source.resolve().relative_to(lab.ROOT)),'sha256':lab.sha256(tame_source)})
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_config=config,capture_config_sha256=digest,capture_disarmed=False);t.persist()
    try:yield
    finally:
        journal=lab.ROOT/'evidence/owned_pet_abandon_packets.jsonl';until=time.time()
        t.receipt['capture_packets']=[p for p in entries(journal) if p.get('session')==session and
            started<=p.get('time',0)<=until] if journal.is_file() else []
        t.persist()
        if not path.is_file() or lab.sha256(path)!=digest:
            raise RuntimeError('owned Abandon probe changed; refusing to remove another capture')
        path.unlink();t.receipt['capture_disarmed']=True;t.persist()


def run(t,preparation,entry,source,review_path,tame_source=None,deployment=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);s=closed(source);before=pets(6)
    number=deployed_number(t,tame_source,before,deployment) if tame_source else 6
    frozen=pair_preserved if tame_source else identities
    if ((t.fixture['guid'],t.fixture['class'],t.fixture['level'])!=(6,3,10) or (not tame_source and not disposable_pair(before)) or
        not frozen(old['retained_class_pets'],before) or not primary_absent() or
        s.get('phase')!='owned_test_pet_abandon_dialog' or s.get('actor')!=t.fixture or
        s.get('runtime')!=t.receipt['runtime'] or s.get('fixture_source')!=bound(preparation) or
        s.get('entry_source')!=bound(entry) or s.get('native_session')!=session or
        len(s.get('checks',{}))!=11 or not all(s['checks'].values()) or
        not frozen(s.get('retained_pet_before',[]),before) or
        (tame_source and (s.get('disposable_tame_source')!=bound(tame_source) or s.get('disposable_pet_number')!=number))):
        raise RuntimeError(f'requires whole same-entry disposable Wolf{number} dialog with named Harnesswolf stored5')
    o=Presence(session,6,e['started_at']).poll();inv=Inventory(lab.ROOT,session,6).poll()
    if (not o.present() or o.pet['guid']!=s['native_pet']['guid'] or o.pet.get('map')!=0 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=number or
        o.pet['fields'].get(INDEX['OBJECT_FIELD_ENTRY'])!=299 or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=6 or
        resources(inv)!=e['resources'] or saved(6)!=e['entered_saved']):
        raise RuntimeError(f'current disposable native Wolf{number} or owner baseline differs')
    d=reviewed(t,review_path,f'Confirm Abandon Wolf{number}');button=next(c for c in s['dialog_controls'] if c['text']=='Okay')
    if d.get('source')!=bound(source) or d.get('frame')!=s['frame'] or d['point']!=point(button):
        raise RuntimeError('fresh stock Okay review differs')
    state,_=t.observe('test_pet_abandon_confirm_before')
    if not dialog(state) or state['pet_popups']!=s['state']['pet_popups']:
        raise RuntimeError(f'current disposable Wolf{number} dialog differs')
    guid=o.pet['guid'];t.receipt.update(fixture_source=bound(preparation),entry_source=bound(entry),source=bound(source),
        native_session=session,native_pet_before=o.pet,retained_pet_before=before,
        ordinary_input={'kind':'click','value':d['point'],'hold':.4},input_sent=False,
        qualification_added=False,abandon_confirmation_sent=False)
    t.persist()
    if tame_source:t.receipt.update(disposable_tame_source=bound(tame_source),disposable_pet_number=number)
    with capture(t,session,guid,number,tame_source):
        t.receipt.update(input_sent=True,abandon_confirmation_sent=True);t.persist();t.execute(t.receipt['ordinary_input'])
        deadline=time.monotonic()+30
        while True:
            state,frame=t.observe('test_pet_abandon_confirm_settled');o.poll()
            if not o.present() and guid in o.removed and not state.get('pet_popups'):break
            if time.monotonic()>=deadline:raise RuntimeError('ordinary Abandon outcome did not settle; no input replay')
            time.sleep(.25)
    public=public_pet(t,'test_pet_abandon_confirm_public');initial=s['initial_target']
    if not initial.get('exists') or initial.get('guid')==expected_guid(s['native_pet']):
        t.execute({'kind':'chat','value':'/cleartarget'});expected_target=None
    elif initial.get('name')=='Erma':t.execute({'kind':'chat','value':'/targetexact Erma'});expected_target=initial.get('guid')
    else:raise RuntimeError('Abandon original target has no ordinary restoration')
    state,frame=t.observe('test_pet_abandon_confirm_restored');o.poll();after=pets(6)
    checks={**exact_requests(t.receipt['capture_packets'],guid),
        'native_disposable_removed':guid in o.removed and not o.present(),
        'native_summon_cleared':pair(o.player,'UNIT_FIELD_SUMMON')==0,
        'public_pet_absent':public.get('exists') is False,'disposable_saved_row_removed':all(r['id']!=number for r in after),
        'named_pet_preserved':named_preserved(before,after),'probe_disarmed':t.receipt['capture_disarmed'],
        'resources':resources(inv.poll())==e['resources'],'saved_rows':saved(6)==e['entered_saved'],
        'position':state['world_position']==s['initial_position'],
        'target_restored':state['target'].get('guid')==expected_target,
        'dialogs_closed':not state.get('pet_popups') and not state.get('panels'),
        'primary_absent':primary_absent(),'protected_actors':all(protected(old).values()),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(checks=checks,state=state,frame=frame,public_pet=public,retained_pet_after=after,
        native_removed=sorted(o.removed),native_player_after=o.player,completed=all(checks.values()),
        phase='owned_disposable_pet_abandoned',intentional_fixture_change=f'Only disposable Wolf{number} is removed; named Harnesswolf4 remains stored5.')
    if not all(checks.values()):raise RuntimeError('whole disposable Abandon or protected preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','source','review','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--tame-source',type=Path);p.add_argument('--deployment',type=Path);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.source,a.review,a.tame_source,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
