"""Return the existing scout to selection after a closed restored movement cohort."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_language_fixture import logout
from .interaction_bridge_deploy import shot
from .interaction_ground_movement import position,angle
from .interaction_groups import native_group
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_lifecycle import Packets
from .observation.inventory import Inventory


def canonical(value):return json.loads(json.dumps(value))


def park(t,source):
    source=source.resolve()
    if source.name!='cohort.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned closed movement cohort')
    cohort=json.loads(source.read_text());old_path=source.parent/'scout/episode.json'
    old=json.loads(old_path.read_text());restored=json.loads((source.parent/'nearby_restoration.json').read_text())
    if (cohort.get('schema')!='client442_ground_movement_v1' or not cohort.get('finished_at') or
        not old.get('finished_at') or old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or
        t.fixture['guid']!=2 or not old.get('ground_restoration',{}).get('checks') or
        not all(old['ground_restoration']['checks'].values()) or
        not cohort.get('temporary_party',{}).get('restoration',{}).get('native_absent')):
        raise RuntimeError('source movement cohort or restored scout lifetime differs')
    # A whole failed experiment may be safely parked after its exact cleanup.
    # This action contributes no movement qualification.
    t.clean_panels();state,frame=t.observe('scout_park_before')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,2).poll()
    baseline=old['ground_baseline'];where=position(2);expected=restored['positions']['2']
    checks={'resources':canonical(resources(oracle))==baseline['resources'],
        'stats':restored_native_state(baseline['stats'],native_state(oracle)),
        'spells':canonical(known(2))==baseline['spells'],'actions':canonical(saved_actions(2))==baseline['actions'],
        'pose':canonical(pose(oracle))==baseline['pose'],'afk':afk(oracle)==baseline['afk'],
        'position':math.dist(where[:3],expected[:3])<.01 and abs(angle(where[3],expected[3]))<.00001 and where[4]==expected[4],
        'solo':state['group']['members']==0 and native_group() is None,
        'target_cleared':not state.get('target',{}).get('exists'),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},
        restored_scout_source={'file':str(old_path),'sha256':lab.sha256(old_path)},
        before_checks=checks,before_frame=frame,qualified_scope='Setup cleanup only: ordinary owned scout logout after verified movement restoration. No new gameplay qualification.',
        custom_script_permission='blocked_by_user');t.persist()
    if not all(checks.values()):raise RuntimeError('scout differs from the closed restored movement fixture')
    packets=Packets(session);started=time.time();logout(t)
    deadline=time.monotonic()+12
    while not packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native'):
        if time.monotonic()>deadline:raise RuntimeError('owned scout logout lacks native enumeration')
        time.sleep(.2)
    t.receipt['logout_checks']={'ordinary_request':packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'),
        'native_completion':packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'),
        'native_enumeration':True,'native_offline':True}
    t.receipt['frame']=shot(t.out/'scout_parked.png');t.persist()
    if not all(t.receipt['logout_checks'].values()):raise RuntimeError('owned scout parking wire checks differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        try:park(t,a.source);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)
