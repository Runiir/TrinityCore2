"""Clear prior passive diagnostic history through ordinary primary interface reload."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_primary_combat_reentry import inventory,protected_snapshot
from .interaction_ground_movement import position


def run(t,path):
    d=json.loads(path.read_text())
    if (path.is_symlink() or not path.resolve().is_relative_to(lab.ROOT/'evidence') or path.name!='episode.json' or
        not d.get('finished_at') or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        t.fixture['guid']!=1 or len(d.get('restoration_checks',{}))!=10 or not all(d['restoration_checks'].values())):
        raise RuntimeError('requires closed restored primary diagnostic')
    base=d['baseline'];t.receipt.update(source={'path':str(path.resolve()),'sha256':lab.sha256(path)},
        baseline=base,qualification_added=False);t.persist()
    before,_=t.observe('before_reload')
    if position(1)!=base['position'] or protected_snapshot()!=base['protected'] or before['owner_melee']['active'] or before['target'].get('exists'):
        raise RuntimeError('reload preflight differs')
    t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('after_reload',seconds=60)
    checks={'owned_guid':state['guid']==t.guid,'observer141':state.get('observer_version')==141,
        'history_clear':not state.get('errors'),'saved_user_pose':position(1)==base['position'],
        'public_pose':math.dist(state['world_position'][:2],base['position'][:2])<.2,
        'saved_rows':saved(1)==base['saved'],'inventory':inventory(1)==base['inventory'],
        'pets':pets(1)==base['pets'],'money':character(1,t.fixture['account_id'])['money']==base['money'],
        'protected':protected_snapshot()==base['protected'],'idle':not state['owner_melee']['active'],
        'empty_selection':not state['target'].get('exists'),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(checks=checks,state=state,frame=frame,phase='primary_passive_history_cleared');t.persist()
    if not all(checks.values()):raise RuntimeError('ordinary primary reload differs')
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
