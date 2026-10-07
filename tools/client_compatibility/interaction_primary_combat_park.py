"""Normally park the diagnosed original primary and verify its saved boundary."""
import argparse,json,time
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


def run(t,path):
    d=json.loads(path.read_text())
    if (path.resolve().name!='episode.json' or not path.resolve().is_relative_to(lab.ROOT/'evidence') or path.is_symlink() or
        not d.get('finished_at') or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        t.fixture['guid']!=1 or t.fixture['actor']!='primary' or
        len(d.get('restoration_checks',{}))!=10 or not all(d['restoration_checks'].values())):
        raise RuntimeError('requires a closed primary diagnostic with whole restoration')
    base=d['baseline'];t.receipt.update(source={'path':str(path.resolve()),'sha256':lab.sha256(path)},
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
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.source)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','checks')}),flush=True)
