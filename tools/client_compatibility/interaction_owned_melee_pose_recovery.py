"""Restore the sole drawn-weapon mismatch from a closed owned melee capture."""
import argparse,copy,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_attack_capture import AttackPresence
from .interaction_pet_react_modes import whole_restore
from .interaction_sit_stand import pose
from .interaction_ground_movement import position
from .interaction_spellbook_recon import resources
from .interaction_pet_dismiss import vitals
from .observation.inventory import Inventory


def recover(t,source,preparation,entry):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed melee capture')
    d=json.loads(source.read_text());checks=d.get('restoration_checks',{})
    if (d.get('completed') is not False or not d.get('finished_at') or
        d.get('failure')!='RuntimeError: native pet reaction-mode restoration differs' or
        d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        len(checks)!=17 or [k for k,v in checks.items() if not v]!=['pose'] or
        not all(d.get('protected_checks',{}).values()) or
        d.get('qualification_added') is not False or not d.get('cases') or
        d['cases'][0].get('status')!='owned_melee_capture_pass' or
        d['cases'][0].get('id')!='combat.autoattack_capture' or
        d['baseline']['pose']!={'stand':0,'sheath':0}):
        raise RuntimeError('closed exact owned melee sheath-only failure differs')
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation)
    if session!=d['native_session']:raise RuntimeError('failed melee native session differs')
    o=AttackPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    base=d['baseline']
    if (pose(inventory)!={'stand':0,'sheath':1} or resources(inventory)!=base['resources'] or
        position(5)!=base['position'] or saved(5)!=base['saved'] or vitals(o)!=base['vitals'] or
        character(5,2)['money']!=base['money']):
        raise RuntimeError('current closed-source sheath-only mismatch differs')
    t.receipt.update(source={'path':str(source),'sha256':lab.sha256(source)},baseline=copy.deepcopy(base),
        native_session=session,qualification_added=False)
    t.persist();whole_restore(t,o,inventory,old,base)
    t.receipt.update(completed=True,phase='owned_melee_pose_recovery_complete',qualified_scope=
        'Ordinary observed sheath binding restores the exact closed melee capture pose failure. '
        'All original-state checks pass separately; failed melee capture remains excluded.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:recover(t,a.source,a.preparation,a.entry)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({key:t.receipt.get(key) for key in ('completed','failure','restoration_checks')}),flush=True)
