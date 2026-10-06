"""Verify the same saved Imp after an ordinary owned logout and reentry."""
import argparse,json,time
from pathlib import Path
from types import SimpleNamespace
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import prepared,origin_checks,saved,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_spellbook_recon import resources
from .interaction_pet_target import PetOracle,pair,source
from .observation.inventory import Inventory
from .world.objects import INDEX
from .interaction_retained_class_reentry import continuity


def checks(previous,retained,oracle,public):
    pet=oracle.pet;fields=pet['fields'] if pet else {};guid=pet['guid'] if pet else 0
    expected=f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}" if pet else ''
    return {'logical_pet':retained.get('id')==1 and retained.get('entry')==416 and retained.get('owner')==oracle.owner,
        'native_identity':bool(pet and guid>>52==0xf14 and guid>>32&0xfffff==416 and
            fields.get(INDEX['UNIT_FIELD_PETNUMBER'])==retained.get('id')),
        'new_native_counter':bool(pet and guid!=previous['guid']),
        'owned_pet':bool(pet and pair(fields,'UNIT_FIELD_SUMMONEDBY')==oracle.owner and
            pair(oracle.player,'UNIT_FIELD_SUMMON')==guid),
        'public_identity':bool(pet and public.get('exists') is True and public.get('guid')==expected),
        'saved_name':bool(previous.get('name') and previous['name']==retained.get('name')==public.get('name'))}


def previous_source(t,preparation,previous_power):
    old=closed(previous_power);sources=preparation.get('sources',[])
    if len(sources)!=3:raise RuntimeError('requires the exact closed reentry restoration chain')
    rows=[]
    for s in sources:
        p=Path(s['path']);row=closed(p)
        if lab.sha256(p)!=s['sha256']:raise RuntimeError('reentry restoration source changed')
        rows.append(row)
    prior,park,finish=rows;prior_path=Path(sources[0]['path'])
    continuity(SimpleNamespace(fixture=preparation['origin_actor'],receipt=t.receipt),prior,park,finish,lab.sha256(prior_path))
    prepared_keys={'original_character','original_saved_rows','native_worldserver','class_offline',
        'retained_character','retained_saved_rows','retained_pets','origin_registration'}
    restoration={'original_character','original_saved_rows','native_worldserver','empty_selection',
        'resources','saved_rows','position','panels_closed','ui_clean'}
    power_keys={'native_target','owned_pet','public_target','public_pet','mana_type','power','visible_target','ui_clean','detail_ui_clean'}
    power=[c for c in old.get('cases',[]) if c.get('id')=='pets.pet_power']
    if (old.get('phase')!='owned_pet_target_health_power_complete' or old.get('actor')!=t.fixture or
        old.get('runtime')!=t.receipt['runtime'] or old.get('fixture_source',{}).get('sha256')!=lab.sha256(prior_path) or
        set(old.get('restoration_checks',{}))!=restoration or not all(old['restoration_checks'].values()) or
        len(power)!=1 or power[0].get('status')!='native_owned_pet_power_pass' or
        set(power[0].get('oracle',{}).get('checks',{}))!=power_keys or not all(power[0]['oracle']['checks'].values()) or
        set(preparation.get('checks',{}))!=prepared_keys or not all(preparation['checks'].values()) or
        park.get('actor')!=t.fixture or park.get('fixture_source',{}).get('sha256')!=lab.sha256(prior_path) or
        park.get('phase')!='await_original_selection_review' or not all(park.get('checks',{}).values()) or
        park.get('retained_class_pets')!=preparation.get('retained_class_pets') or
        not old['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at']<finish['finished_at']<=preparation['started_at']):
        raise RuntimeError('previous whole pet check and ordinary logout chain differ')
    pet=old['native_pet'];guid=pet['guid'];fields={int(k):v for k,v in pet['fields'].items()}
    expected=f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"
    if (guid>>52!=0xf14 or guid>>32&0xfffff!=416 or fields.get(INDEX['UNIT_FIELD_PETNUMBER'])!=1 or
        pair(fields,'UNIT_FIELD_SUMMONEDBY')!=t.fixture['guid'] or old['public_pet'].get('guid')!=expected):
        raise RuntimeError('previous whole pet identity differs')
    old_entry=Path(old['sources'][0]['path'])
    if lab.sha256(old_entry)!=old['sources'][0]['sha256']:
        raise RuntimeError('previous owned pet entry changed')
    entry_source(t,old_entry,old['native_session'],prior_path)
    return old


def suite(t,preparation,entry,probe,previous_power):
    old=prepared(t,preparation);previous=previous_source(t,old,previous_power)
    session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    public=source(t,probe,session,entry)['public_pet']
    retained=old['retained_class_pets']
    if len(retained)!=1:raise RuntimeError('retained native pet row is ambiguous')
    oracle=PetOracle(session,t.fixture['guid'],e['started_at']).poll()
    inventory=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    state,frame=t.observe('persisted_owned_pet');oracle.poll()
    valid=checks({'guid':previous['native_pet']['guid'],'name':previous['public_pet']['name']},retained[0],oracle,public)
    restored=origin_checks(old);restored.update(empty_selection=oracle.selected()==0 and not state['target']['exists'],
        resources=resources(inventory)==e['resources'],saved_rows=saved(t.fixture['guid'])==e['entered_saved'],
        position=state['world_position']==e['state']['world_position'],panels_closed=not state.get('panels') and not state.get('bags'),
        ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
    valid['restoration']=all(restored.values())
    t.receipt.update(sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (entry,probe,previous_power)],
        native_session=session,previous_pet={'guid':previous['native_pet']['guid'],'name':previous['public_pet']['name']},
        retained_pet=retained[0],native_pet=oracle.pet,public_pet=public,restoration_checks=restored,restored_frame=frame,
        qualified_scope='Same owned Imp identity and name survive ordinary logout and normal reentry; no pet command-state persistence claim.')
    row={'id':'pets.persist','time':time.time(),'input_sent':False,
        'status':'native_owned_pet_persistence_pass' if all(valid.values()) else 'client_or_protocol_failure',
        'after':state,'after_frame':frame,'oracle':{'checks':valid}}
    t.receipt['cases'].append(row);t.persist()
    if not all(valid.values()):raise RuntimeError('owned saved pet persistence differs')
    t.receipt.update(completed=True,phase='owned_pet_persistence_complete')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('preparation','entry','probe','previous-power','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.probe,a.previous_power)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
