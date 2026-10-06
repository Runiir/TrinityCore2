"""Verify the retained one-time Hunter name after an ordinary logout and entry."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_rename_acceptance import NAME,native_name,modern_name
from .interaction_hunter_pet_recon import saved_pet_unchanged,pet_frame_menu
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import PetOracle
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import detail
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .world.gameobjects import modern_guid


def source(t,old,path):
    e=closed(path);sources=old.get('sources',[])
    if (len(sources)!=3 or e.get('phase')!='hunter_renamed' or e.get('actor')!=t.fixture or
        e.get('runtime')!=t.receipt['runtime'] or e.get('fixture_source',{}).get('sha256')!=sources[0]['sha256'] or
        len(e.get('rename_checks',{}))!=18 or not all(e['rename_checks'].values()) or
        len(e.get('restoration_checks',{}))!=13 or not all(e['restoration_checks'].values()) or
        len(e.get('pet_menu',{}).get('checks',{}))!=4 or not all(e['pet_menu']['checks'].values()) or
        e.get('public_pet',{}).get('name')!=NAME or
        set(e.get('protected_checks',{}))!={f'actor_{g}_unchanged' for g in range(1,6)} or
        not all(e['protected_checks'].values())):
        raise RuntimeError('requires the whole verified owned Hunter one-time Rename')
    paths=[Path(s['path']).resolve() for s in sources]
    if any(lab.sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):
        raise RuntimeError('ordinary name persistence logout chain changed')
    previous,park,finish=[closed(p) for p in paths]
    if (e['fixture_source']['sha256']!=lab.sha256(paths[0]) or
        not e['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at']<finish['finished_at'] or
        not saved_pet_unchanged(e['restored_pets'],park['retained_class_pets'],time.time()) or
        old.get('retained_class_pets')!=park['retained_class_pets'] or
        old.get('natural_saved')!=e['baseline_saved']):
        raise RuntimeError('ordinary retained Rename boundary differs')
    t.receipt['rename_source']={'path':str(path.resolve()),'sha256':lab.sha256(path)}
    return e


def fresh_entry(entered,renamed):
    """Character logout/login reuses its healthy bridge transport session."""
    start,end=entered.get('started_at',0),entered.get('finished_at',0)
    packets=entered.get('login_packets',[])
    return (renamed['finished_at']<start<end and
        entered.get('native_before_entry',{}).get('online')==0 and
        bool(packets) and all(start<=p.get('time',0)<=end for p in packets) and
        any(p.get('name')=='CMSG_PLAYER_LOGIN' and p.get('direction')=='from_client' for p in packets) and
        any(p.get('name')=='SMSG_LOGIN_VERIFY_WORLD' and p.get('direction')=='from_native' for p in packets))


def suite(t,preparation,entry,renamed):
    old=prepared(t,preparation);e=source(t,old,renamed);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);since=min(p['time'] for p in entered['login_packets'])
    o=Presence(session,6,since).poll();inv=Inventory(lab.ROOT,session,6).poll();retained=pets(6)
    if not o.present():raise RuntimeError('retained renamed Hunter pet is absent')
    identity=expected_guid(o.pet);initial,_=t.observe('hunter_name_reentry_before');before=resources(inv)
    t.receipt.update(native_session=session,native_pet=o.pet,entry_source={'path':str(entry.resolve()),'sha256':lab.sha256(entry)},
        baseline_resources=before,retained_pet=retained)
    try:
        require(click_case(t,'diagnostic.hunter_rename.persisted_book','Read the retained Hunter name after normal reentry.',
            lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'hunter_pet_book_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}),'hunter_pet_book_pass')
        public=detail(t,'hunter_name_reentry')['pet'];t.clean_panels();o.poll()
        packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==session and
            p.get('time',0)>=since and p.get('name') in ('SMSG_PET_NAME_QUERY_RESPONSE','SMSG_QUERY_PET_NAME_RESPONSE')]
        n=[{'packet':p,'decoded':native_name(p)} for p in packets if p['direction']=='from_native']
        m=[{'packet':p,'decoded':modern_name(p)} for p in packets if p['direction']=='to_client']
        timestamp=o.pet['fields'].get(INDEX['UNIT_FIELD_PET_NAME_TIMESTAMP'])
        checks={'fresh_character_entry':fresh_entry(entered,e),
            'new_runtime_guid_same_saved_pet':o.pet['guid']!=e['native_pet']['guid'] and
                o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==4,
            'native_one_time_permission':o.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255==2,
            'saved_pet_persisted':saved_pet_unchanged(e['restored_pets'],retained,time.time()),
            'public_name':public.get('exists') is True and public.get('guid')==identity and public.get('name')==NAME,
            'native_name_reply':bool(n) and all(x['decoded']=={'pet_number':4,'name':NAME,'timestamp':timestamp} for x in n),
            'modern_name_reply':bool(m) and all(x['decoded']=={'guid':list(modern_guid(o.pet['guid'],0)),
                'name':NAME,'timestamp':timestamp} for x in m),
            'resources':before==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],**protected(old)}
        t.receipt.update(persistence_checks=checks,public_pet=public,name_replies={'native':n,'modern':m},
            protected_checks=protected(old));t.persist()
        if not all(checks.values()):raise RuntimeError('ordinary owned Hunter name persistence differs')
        t.execute({'kind':'chat','value':'/target pet'});state,_=t.observe('hunter_name_reentry_target')
        oracle=PetOracle(session,6,since).poll()
        if state.get('target',{}).get('guid')!=identity or oracle.selected()!=o.pet['guid']:
            raise RuntimeError('normal retained pet selection differs')
        pet_frame_menu(t,oracle,identity,name=NAME,rename_allowed=False)
    finally:
        t.clean_panels();target=initial.get('target',{})
        if not target.get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        elif target.get('name')=='Benjamin Foxworthy':t.execute({'kind':'chat','value':'/targetexact Benjamin Foxworthy'})
        else:raise RuntimeError('Hunter name persistence baseline target cannot be restored normally')
        state,frame=t.observe('hunter_name_reentry_restored');o.poll()
        checks={'resources':resources(inv.poll())==before,'saved_rows':saved(6)==e['baseline_saved'],
            'retained_pet':saved_pet_unchanged(retained,pets(6),time.time()),'owned_pet_present':o.present(),
            'position':state['world_position']==initial['world_position'],
            'selection':state.get('target',{}).get('guid')==target.get('guid'),'panels_closed':not state.get('panels'),
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('Hunter name reentry preservation differs')
    t.receipt.update(completed=True,phase='hunter_rename_persisted',qualification_added=False,
        qualified_scope='Ordinary logout/reentry retains the saved synthetic Hunter name and one-time permission removal; '
            'all prior actors and native/saved resources preserved. No repeated Rename or forced name setter.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('preparation','entry','renamed','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.renamed)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
