"""Serialize selected commands until fresh client facts confirm their outcome.

This queue has one active command. It never chooses an action or repeats an
input. Waiting reads local telemetry, including cast end times and the GCD.
"""
import threading
import time
from . import runtime

_active = threading.Lock()
POLL_SECONDS = .05
ACCEPTANCE_TIMEOUT = 3
UNKNOWN_CAST_TIMEOUT = 15


def generations(row):
    return {key:row[section]['sequence'] for key,section in
            (('M','movement'),('A','archaeology'),('F','farm_ui'))
            if row.get(section) and 'sequence' in row[section]}


def newer(row, baseline):
    current=generations(row);previous=generations(baseline)
    if previous:return all(key in current and current[key]!=value for key,value in previous.items())
    return row.get('observed_at',0)>baseline.get('observed_at',0)


def busy(row, *, uses_gcd=True):
    ui=row.get('farm_ui') or {};cast=ui.get('casting') or {}
    if row['archaeology'].get('casting') or cast.get('name'):return 'casting'
    gcd=ui.get('gcd') or {}
    if uses_gcd and gcd.get('ends',0)>ui.get('uptime',0):return 'global_cooldown'
    return None


def cast_remaining(row):
    ui=row.get('farm_ui') or {};cast=ui.get('casting') or {}
    return max(0,(cast.get('ends') or 0)-ui.get('uptime',0))


def validate(row,before):
    if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
    if row.get('runtime')!=before.get('runtime'):raise RuntimeError('selected client action invalidated: owned client changed')
    m=row['movement']
    if not m['in_world'] or m['dead'] or m['on_taxi']:
        raise RuntimeError('selected client action invalidated: player unavailable')


def wait_ready(folder,before,observer,*,uses_gcd=True):
    """Wait for an existing cast/GCD; do not dispatch another command into it."""
    deadline=time.monotonic()+max(UNKNOWN_CAST_TIMEOUT,cast_remaining(before)+2)
    row=before
    while busy(row,uses_gcd=uses_gcd):
        validate(row,before)
        if time.monotonic()>=deadline:raise RuntimeError('selected client action readiness timed out')
        time.sleep(POLL_SECONDS);row=observer(folder/'ready.png')
    validate(row,before)
    return row


def run(folder,before,action,send,complete,observer,*,allowed=None,uses_gcd=True,failure=None):
    """Execute a previously selected command once, then retain it until settled."""
    if not _active.acquire(blocking=False):raise RuntimeError('a selected client command is already pending')
    path=folder/'queue.json'
    result={'action':action,'status':'queued','selected_at':before.get('observed_at'),
            'started_at':time.time(),'inputs':[],'samples':0,'cast_observed':False}
    def record(status):
        result['status']=status;runtime.write(path,result)
    try:
        folder.mkdir(parents=True,exist_ok=True)
        record('waiting_ready')
        row=wait_ready(folder,before,observer,uses_gcd=uses_gcd)
        # Revalidate immediately before sending, even if no cast was active.
        row=observer(folder/'precheck.png');validate(row,before)
        row=wait_ready(folder,row,observer,uses_gcd=uses_gcd)
        if complete(row):
            result.update(after=row,already_completed=True,completed=True);record('completed');return result
        if allowed and not allowed(row):raise RuntimeError('selected client action invalidated before dispatch')
        result['inputs'].append(send(row));result['sent_at']=time.time();record('sent')
        sent=row;started=time.monotonic();deadline=started+ACCEPTANCE_TIMEOUT;hard_deadline=None
        while True:
            row=observer(folder/'feedback.png');validate(row,before)
            result.update(samples=result['samples']+1,after=row,
                          last_client_error=(row.get('farm_ui') or {}).get('error'))
            fresh=newer(row,sent)
            if fresh and busy(row,uses_gcd=False)=='casting':
                if not result['cast_observed']:
                    hard_deadline=time.monotonic()+max(UNKNOWN_CAST_TIMEOUT,cast_remaining(row)+2)
                result['cast_observed']=True
                remaining=cast_remaining(row)
                deadline=max(deadline,time.monotonic()+remaining+2 if remaining else started+UNKNOWN_CAST_TIMEOUT)
                record('casting')
            if fresh and complete(row) and not busy(row,uses_gcd=uses_gcd):
                result.update(completed=True,finished_at=time.time());record('completed');return result
            if time.monotonic()>=min(deadline,hard_deadline or deadline):
                raise RuntimeError(failure or f'{action} input did not confirm its client outcome')
            time.sleep(POLL_SECONDS)
    except Exception as error:
        result.update(completed=False,failure=str(error),finished_at=time.time());record('unconfirmed');raise
    finally:
        _active.release()
