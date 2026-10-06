"""Await fresh local observations without input or renewing farm inactivity."""
import time
from . import runtime
from .observe import observe


class InactiveObservation(RuntimeError):
    pass


def sample(output,session,reader=None):
    reader=reader or observe
    owner=runtime.owned_process()
    waiting=None
    while True:
        if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
        if time.time()-session['last_progress_at']>=1800:
            raise InactiveObservation('30 minutes without gameplay progress')
        if not owner or runtime.owned_process()!=owner:
            raise RuntimeError('owned live client lifetime changed while awaiting observations')
        try:
            row=reader(output)
        except RuntimeError as error:
            if not str(error).startswith(('local public tiles unavailable:',
                    'direct public addon feed unavailable:', 'live public observer is unavailable:')):
                raise
            if waiting is None:
                waiting=time.time()
                print('Waiting for fresh public telemetry; gameplay inputs are released.',flush=True)
            runtime.write(runtime.ROOT/'run/farm_observation_wait.json',{
                'status':'waiting','started_at':waiting,'updated_at':time.time(),
                'reason':str(error),'runtime':owner,'inputs_sent':0,
                'last_progress_at':session['last_progress_at']})
            time.sleep(.2)
            continue
        if waiting is not None:
            runtime.write(runtime.ROOT/'run/farm_observation_wait.json',{
                'status':'recovered','started_at':waiting,'recovered_at':time.time(),
                'runtime':owner,'inputs_sent':0,'last_progress_at':session['last_progress_at']})
            print('Fresh public telemetry recovered; resuming Laya decisions.',flush=True)
        return row
