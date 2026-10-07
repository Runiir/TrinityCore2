"""Stop only the parked owned scout to free memory for a one-job build."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot,identity
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_primary_combat_reentry import retained
from .interaction_hunter_stable_slots import bound


def snapshot():
    return {str(g):retained(g,a) for g,a in ((1,1),(2,2),(3,2),(4,2),(5,2),(6,2))}


def gone(pid,ticks):
    try:return lab.proc_start(pid)!=ticks
    except (FileNotFoundError,ProcessLookupError):return True


def pause(t,source,primary_stop):
    e=closed(source);stop=closed(primary_stop)
    if (t.fixture.get('guid')!=2 or e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or
        e.get('phase')!='owned_abandon_cancel_parked_boundary' or len(e.get('checks',{}))!=18 or not all(e['checks'].values()) or
        e.get('primary_stop_source')!=bound(primary_stop) or stop.get('phase')!='user_requested_primary_client_stopped' or
        len(stop.get('checks',{}))!=8 or not all(stop['checks'].values()) or stop['before']!=stop['after']):
        raise RuntimeError('requires the whole parked cancellation and exact user-stopped primary')
    before=snapshot()
    if before['1']!=stop['after'] or any(v['native']['online']!=0 for v in before.values()):
        raise RuntimeError('all six retained owned characters must be offline and primary unchanged')
    with actor('primary'):
        if lab.owned_process('client'):raise RuntimeError('primary client must remain stopped')
    if any((lab.ROOT/'run'/name).exists() for name in
        ('owned_pet_abandon_probe.json','owned_tame_request_probe.json','owned_stable_request_probe.json')):
        raise RuntimeError('cannot pause a client with an armed gameplay probe')
    monitor=owned_input.focus();game=monitor['input_isolation']['game_pid'];game_ticks=lab.proc_start(game)
    t.receipt.update(source=bound(source),primary_stop_source=bound(primary_stop),before=before,
        game_before={'pid':game,'start_ticks':game_ticks},frame=shot(t.out/'scout_parked.png'),
        action='stop_parked_scout_for_build_memory',input_sent=False,qualification_added=False)
    t.persist();lab.stop('client');after=snapshot()
    with actor('primary'):primary_absent=lab.owned_process('client') is None
    checks={'scout_launcher_absent':lab.owned_process('client') is None,
        'owned_game_absent':gone(game,game_ticks),'all_retained_saved_state':before==after,
        'all_characters_offline':all(v['native']['online']==0 for v in after.values()),
        'primary_still_stopped':primary_absent and after['1']==stop['after'],
        'native_lifetime':identity('worldserver')==e['runtime']['worldserver'],
        'bridge_lifetime':identity('modern_world')==e['runtime']['modern_world'],
        'origin_registration':actors.load()==t.fixture}
    t.receipt.update(after=after,checks=checks,completed=all(checks.values()),phase='parked_scout_resource_paused')
    if not all(checks.values()):raise RuntimeError('parked scout resource pause preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','primary-stop','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:pause(t,a.source,a.primary_stop)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
