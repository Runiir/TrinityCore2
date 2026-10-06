"""Verify stock Defensive1 and return to original Assist3 through real native state."""
import argparse,json,time
from pathlib import Path
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_pet_react_modes import suite
from .interaction_social import actor
from .interaction_trial import Trial


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,sequence=((1,'pets.defensive'),(3,'fixture.pet_assist_restore')))
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
