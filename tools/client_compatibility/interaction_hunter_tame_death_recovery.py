"""Recover only the owned test Hunter after the closed failed wild-wolf setup."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound,pet_identity
from .interaction_hunter_tame_stage import pose
from .interaction_pet_dismiss import Presence,vitals
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .interaction_primary_combat_reentry import inventory as persisted_inventory


def run(t,preparation,entry,failed,pose_recovery):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);f=json.loads(failed.read_text());r=closed(pose_recovery)
    if (failed.is_symlink() or failed.resolve().name!='episode.json' or
        not failed.resolve().is_relative_to(lab.ROOT/'evidence') or f.get('completed') is not False or
        not f.get('finished_at') or f.get('actor')!=t.fixture or f.get('runtime')!=t.receipt['runtime'] or
        f.get('native_session')!=session or f.get('staging_failure')!='RuntimeError: interaction fixture is unsafe' or
        r.get('stage_source')!=bound(failed) or r.get('phase')!='owned_tame_pose_restored' or
        r.get('runtime')!=t.receipt['runtime'] or r.get('actor')!=t.fixture or
        len(r.get('pose_restoration',{}).get('checks',{}))!=8 or not all(r['pose_restoration']['checks'].values())):
        raise RuntimeError('requires the closed failed owned setup and successful source-bound pose cleanup')
    o=Presence(session,6,e['started_at']).poll();before=vitals(o);inv=Inventory(lab.ROOT,session,6).poll()
    retained=pets(6);native=character(6,2)
    if (t.fixture['guid']!=6 or native['name']!='Harnesshunt' or native['online']!=1 or
        before['UNIT_FIELD_HEALTH']!=0 or before['UNIT_FIELD_MAXHEALTH']!=209 or
        o.present() or not pet_identity(f['retained_pet_before'],retained,5,0) or
        pose()!=r['pose_restoration']['restored'] or not all(protected(old).values()) or
        saved(6)!=f['baseline_saved'] or resources(inv)!=f['baseline_resources']):
        raise RuntimeError('dead owned test Hunter or protected baseline differs')
    t.receipt.update(native_session=session,failed_source=bound(failed),pose_recovery_source=bound(pose_recovery),
        native_before=native,native_vitals_before=before,retained_pet_before=retained,
        inventory_before=persisted_inventory(6),ordinary_gameplay_input_sent=False,qualification_added=False,
        recovery_command={'command':'revive Harnesshunt','started_at':time.time(),
            'scope':'Native administrative cleanup of the dead owned test fixture only; no player resurrection qualification.'})
    t.persist();lab.server_command('revive Harnesshunt');deadline=time.monotonic()+110
    while time.monotonic()<deadline:
        o.poll()
        if vitals(o)['UNIT_FIELD_HEALTH']==209:break
        time.sleep(.5)
    lab.server_command('saveall');time.sleep(.5);after=vitals(o)
    # Revive can restore half health; wait above for normal native regeneration.
    t.clean_panels();state,frame=t.observe('owned_hunter_recovered')
    checks={'native_health_restored':after['UNIT_FIELD_HEALTH']==after['UNIT_FIELD_MAXHEALTH']==209,
        'living_idle_public_hunter':not frame['movement']['dead'] and not frame['movement']['in_combat'] and
            frame['movement']['health_percent']==100,
        'native_return_pose':pose()==r['pose_restoration']['restored'],
        'retained_Harnesswolf':pet_identity(retained,pets(6),5,0),'no_runtime_pet':not o.present(),
        'resources':resources(inv)==f['baseline_resources'],'saved_rows':saved(6)==f['baseline_saved'],
        'inventory_preserved':persisted_inventory(6)==t.receipt['inventory_before'],
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
    t.receipt.update(native_after=character(6,2),native_vitals_after=after,retained_pet_after=pets(6),
        frame=frame,state=state,recovery_checks=checks);t.persist()
    if not all(checks.values()):raise RuntimeError('owned test Hunter administrative recovery differs')
    t.receipt.update(completed=True,phase='owned_failed_tame_fixture_recovered',
        qualified_scope='Source-bound cleanup only. Failed staging stays excluded; no Tame Beast or resurrection qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('preparation','entry','failed','pose-recovery','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.failed,a.pose_recovery)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','recovery_checks')}),flush=True)
