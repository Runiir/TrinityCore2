"""Repeat the reviewed native stable opening while its existing window renders normally."""
import argparse,json,time
from pathlib import Path
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_hunter_stable_capture import suite
from .interaction_owned_visibility import visible_scout


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('preparation','entry','source','review','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            with visible_scout(t):suite(t,a.preparation,a.entry,'capture',a.source,a.review)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','outcome_checks','restoration_checks',
            'owned_window_visibility')}),flush=True)
