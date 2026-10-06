"""Wait for Survey and gathering outcomes without delaying completed actions."""
import time
from . import action_queue, pending_find, runtime
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def survey(folder, before, send, observer, telescope):
    count=before['archaeology']['successful_surveys']
    queued=action_queue.run(folder,before,'survey',send,
        lambda row:row['archaeology']['successful_surveys']>count,observer,
        allowed=lambda row:row['archaeology']['can_survey'] and
            not any(row['archaeology'].get(k) for k in ('flying','falling')),
        failure='Mouse Button 4 did not produce a successful Survey')
    row=queued['after'];completed=row
    # The cast-success event and the object-create packet are independent.
    # A positive result returns immediately. Only absence needs a propagation
    # allowance, derived from rendered frames and the public tile cadence.
    fps=max(1,(row.get('farm_ui') or {}).get('frame_rate') or 1)
    deadline=time.monotonic()+max(.25,2/fps+.2)
    while True:
        action_queue.validate(row,before)
        ui=row.get('farm_ui') or {}
        named=(ui.get('soft_interact') or {}).get('name') in FIND_NAMES or ui.get('tooltip') in FIND_NAMES
        if telescope(row) or row.get('visible_find') or named or row['archaeology'].get('loot_open'):
            break
        if action_queue.newer(row,completed) and time.monotonic()>=deadline:break
        if time.monotonic()>=deadline+action_queue.ACCEPTANCE_TIMEOUT:
            raise RuntimeError('Survey result did not receive fresh public facts')
        time.sleep(action_queue.POLL_SECONDS);row=observer(folder/'result.png')
    queued.update(after=row,finished_at=time.time())
    runtime.write(folder/'queue.json',queued)
    return queued


def pickup(folder, before, observer):
    """Observe a selected interaction through its cast, loot, or range error."""
    baseline=pending_find.fragments(before)
    gathering=(before.get('farm_ui') or {}).get('gathering') or {}
    started=time.monotonic();deadline=started+action_queue.ACCEPTANCE_TIMEOUT
    hard_deadline=started+action_queue.UNKNOWN_CAST_TIMEOUT
    cast_seen=False
    while True:
        row=observer(folder/'pickup_feedback.png');action_queue.validate(row,before)
        ui=row.get('farm_ui') or {};now=ui.get('gathering') or {}
        cast_seen=cast_seen or now.get('starts',0)>gathering.get('starts',0)
        error=ui.get('error') or {}
        outcome=('fragments_increased' if pending_find.gained(baseline,row) else
            'out_of_range' if pending_find.range_error(error) and error.get('at',0)>=
                (before.get('farm_ui') or {}).get('uptime',0) else
            'loot_open' if row['archaeology'].get('loot_open') and not action_queue.busy(row,uses_gcd=False) else None)
        if outcome:
            result={'after':row,'outcome':outcome,'cast_observed':cast_seen,
                'elapsed_seconds':time.monotonic()-started}
            runtime.write(folder/'pickup_feedback.json',result);return result
        if action_queue.busy(row,uses_gcd=False):
            deadline=max(deadline,time.monotonic()+action_queue.cast_remaining(row)+2)
        if time.monotonic()>=min(deadline,hard_deadline):
            raise RuntimeError('artifact interaction did not confirm fragment pickup')
        time.sleep(action_queue.POLL_SECONDS)
