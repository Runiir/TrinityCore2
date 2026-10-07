"""Read the already-stored named pet after disposable Abandon; send no pet command."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_stable_slots import bound
from .interaction_hunter_fixture import protected
from .interaction_hunter_abandon import primary_absent
from .hunter_abandon_identity import named_preserved
from .interaction_pet_dismiss import Presence,public_pet
from .interaction_pet_target import pair
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .scout_relaunch_lineage import verified_deployment


def ancestor(previous,old,runtime,deployment,ref):
    before=previous.get('runtime',{});base=deployment.get('offline_baselines',{})
    if (deployment.get('schema')!='client442_resource_paused_scout_deployment_v1' or
        deployment.get('completed') is not True or deployment.get('native')!=before.get('worldserver') or
        before.get('worldserver')!=runtime.get('worldserver') or deployment.get('before')!=before.get('modern_world') or
        deployment.get('previous_scout')!=before.get('client') or deployment.get('after')!=runtime.get('modern_world') or
        deployment.get('scout_lifetime')!=runtime.get('client') or previous.get('all_offline_snapshot')!=base or
        ref not in old.get('sources',[]) or old.get('natural_native')!=base.get('6',{}).get('native') or
        old.get('natural_saved')!=base.get('6',{}).get('saved') or
        old.get('retained_class_pets')!=base.get('6',{}).get('pets')):
        raise RuntimeError('stored named-pet ancestor is not bound to the exact paused deployment')


def prior_named_pet(previous,load=closed,binding=bound):
    """Follow a no-Tame closure back to its exact successful Abandon evidence."""
    phase=previous.get('phase');checks=previous.get('checks',{})
    expected={'owned_abandon_parked_boundary':19,'owned_tame_precast_parked_boundary':20}
    if phase not in expected or len(checks)!=expected[phase] or not all(checks.values()):
        raise RuntimeError('requires a whole Abandon or no-Tame parked closure')
    sources=previous.get('sources',[])
    if phase=='owned_tame_precast_parked_boundary':
        if len(sources)!=7:raise RuntimeError('no-Tame closure source chain differs')
        ref=sources[2];stored=load(Path(ref['path']))
        if (ref!=binding(Path(ref['path'])) or stored.get('phase')!='owned_existing_stored_pet_boundary' or
            len(stored.get('checks',{}))!=15 or not all(stored['checks'].values()) or
            stored.get('runtime')!=previous.get('runtime') or stored.get('pet_command_sent') is not False or
            stored.get('fixture_source')!=sources[0] or stored.get('entry_source')!=sources[1]):
            raise RuntimeError('no-Tame closure has no exact earlier stored-pet proof')
        rows=previous.get('all_offline_snapshot',{}).get('6',{}).get('pets')
        ref=stored.get('abandon_source',{});abandoned=load(Path(ref.get('path','')))
        if (ref!=binding(Path(ref['path'])) or stored.get('baseline_pets')!=rows or
            abandoned.get('phase')!='owned_abandon_parked_boundary' or
            len(abandoned.get('checks',{}))!=19 or not all(abandoned['checks'].values()) or
            abandoned.get('retained_pets')!=rows or stored.get('confirmation_source')!=abandoned['sources'][3]):
            raise RuntimeError('no-Tame named pet is not bound to its original removal proof')
        confirmation=stored['confirmation_source']
    else:
        rows=previous.get('retained_pets');confirmation=sources[3]
    confirmed=load(Path(confirmation['path']))
    if (confirmation!=binding(Path(confirmation['path'])) or
        confirmed.get('phase')!='owned_disposable_pet_abandoned' or len(confirmed.get('checks',{}))!=16 or
        not all(confirmed['checks'].values()) or not named_preserved(confirmed['retained_pet_before'],rows)):
        raise RuntimeError('named pet continuity is not bound to successful disposable removal')
    return rows,confirmed,confirmation


def run(t,preparation,entry,abandon,deployment=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);previous=closed(abandon);rows=pets(6)
    if deployment:
        d,_=verified_deployment(deployment,t.receipt['runtime'])
        ancestor(previous,old,t.receipt['runtime'],d,bound(deployment))
        t.receipt['deployment_source']=bound(deployment)
    retained,confirmed,confirmation=prior_named_pet(previous)
    if ((t.fixture['guid'],t.fixture['class'],t.fixture['level'])!=(6,3,10) or
        (not deployment and previous.get('runtime')!=t.receipt['runtime']) or
        previous.get('actor')!=old['origin_actor'] or rows!=retained or rows!=old['retained_class_pets']):
        raise RuntimeError('requires the source-bound Abandon closure with the unchanged sole named pet')
    o=Presence(session,6,entered['started_at']).poll();inv=Inventory(lab.ROOT,session,6).poll()
    t.receipt.update(native_session=session,entry_source=bound(entry),abandon_source=bound(abandon),
        confirmation_source=confirmation,baseline_pets=rows,qualification_added=False)
    t.persist();public=public_pet(t,'already_stored_tame_pet');state,frame=t.observe('already_stored_tame_boundary')
    checks={'native_no_pet':not o.poll().present(),'native_owner_summon_clear':bool(o.player) and pair(o.player,'UNIT_FIELD_SUMMON')==0,
        'public_no_pet':public.get('exists') is False,'sole_named_pet_stored':len(rows)==1 and
            tuple(rows[0][k] for k in ('id','owner','entry','name','renamed','slot','active'))==(4,6,42717,'Harnesswolf',1,5,0),
        'named_identity':named_preserved(confirmed['retained_pet_before'],pets(6)),
        'resources':resources(inv.poll())==entered['resources'],'saved_rows':saved(6)==entered['entered_saved'],
        'owner_position':state['world_position']==entered['state']['world_position'],
        'primary_absent':primary_absent(),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
    t.receipt.update(checks=checks,baseline_resources=resources(inv),baseline_saved=saved(6),public_pet=public,
        state=state,frame=frame,input_sent=True,pet_command_sent=False,
        completed=all(checks.values()),phase='owned_existing_stored_pet_boundary')
    if not all(checks.values()):raise RuntimeError('already-stored named pet or owner boundary differs')


def stored_boundary(moved,fixture,runtime,session,preparation_ref,entry_ref):
    if moved.get('runtime')!=runtime or moved.get('actor')!=fixture or moved.get('native_session')!=session:return False
    if moved.get('phase')=='owned_stable_slot_move_verified':
        return (moved.get('destination')==5 and moved.get('capture_disarmed') is True and
            len(moved.get('move_checks',{}))==12 and all(moved['move_checks'].values()))
    return (moved.get('phase')=='owned_existing_stored_pet_boundary' and moved.get('fixture_source')==preparation_ref and
        moved.get('entry_source')==entry_ref and moved.get('pet_command_sent') is False and
        len(moved.get('checks',{}))==15 and all(moved['checks'].values()) and
        len(moved.get('baseline_pets',[]))==1 and tuple(moved['baseline_pets'][0].get(k) for k in
            ('id','owner','entry','name','renamed','slot','active'))==(4,6,42717,'Harnesswolf',1,5,0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','abandon','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--deployment',type=Path)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.abandon,a.deployment)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
