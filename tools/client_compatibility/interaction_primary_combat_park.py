"""Normally park the diagnosed original primary and verify its saved boundary."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_primary_combat_reentry import inventory,protected_snapshot
from .interaction_owned_language_fixture import logout
from .interaction_ground_movement import position
from .interaction_bridge_deploy import shot


def run(t,path,user_movement=None):
    d=json.loads(path.read_text())
    if (path.resolve().name!='episode.json' or not path.resolve().is_relative_to(lab.ROOT/'evidence') or path.is_symlink() or
        not d.get('finished_at') or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        t.fixture['guid']!=1 or t.fixture['actor']!='primary' or
        len(d.get('restoration_checks',{}))!=10):
        raise RuntimeError('requires a closed primary diagnostic restoration record')
    checks=d['restoration_checks'];base=copy.deepcopy(d['baseline'])
    if user_movement:
        authority=user_movement.resolve()
        if user_movement.is_symlink() or not authority.is_relative_to(lab.ROOT/'evidence'):
            raise RuntimeError('user movement authority is outside owned evidence')
        a=json.loads(authority.read_text())
        if (a.get('user_confirmed_movement') is not True or
            a.get('statement')!='Yes, I moved Harnessone' or
            a.get('source')!={'path':str(path.resolve()),'sha256':lab.sha256(path)} or
            {k for k,v in checks.items() if not v}!={'saved_user_pose'}):
            raise RuntimeError('requires explicit user attribution of the sole failed pose guard')
        state,frame=t.observe('user_moved_primary_before_park')
        if (state['guid']!=t.guid or state['owner_melee']['active'] or
            frame['movement']['in_combat']):
            raise RuntimeError('user moved primary is not safely idle')
        base['position']=position(1)
        t.receipt['user_movement_authority']={'path':str(authority),'sha256':lab.sha256(authority),
            'previous_position':d['baseline']['position'],'preserved_position':base['position']}
    elif not all(checks.values()):
        raise RuntimeError('requires whole restoration or explicit user movement attribution')
    t.receipt.update(source={'path':str(path.resolve()),'sha256':lab.sha256(path)},
        baseline=base,qualification_added=False);t.persist()
    if position(1)!=base['position'] or protected_snapshot()!=base['protected']:raise RuntimeError('primary parking baseline differs')
    t.clean_panels();logout(t)
    native=character(1,t.fixture['account_id'])
    checks={'offline':native['online']==0,'saved_user_pose':position(1)==base['position'],
        'saved_rows':saved(1)==base['saved'],'inventory':inventory(1)==base['inventory'],
        'retained_pets':pets(1)==base['pets'],'money':native['money']==base['money'],
        'protected_actors':protected_snapshot()==base['protected']}
    t.receipt.update(checks=checks,parked_native=native,frame=shot(t.out/'primary_offline.png'),
        phase='primary_combat_closed_offline',qualified_scope='Normal primary logout and saved boundary; no new gameplay qualification.')
    t.persist()
    if not all(checks.values()):raise RuntimeError('primary parking saved boundary differs')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--user-movement',type=Path);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.source,a.user_movement)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','checks')}),flush=True)
