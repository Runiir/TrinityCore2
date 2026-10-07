"""Stop only an unchanged, offline owned scout after one captured loading failure."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_retained_class_fixture import closed
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot,gone
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .observation.journal import entries
from .reentry_no_login_boundary import validate


def preflight(preparation,stage,failed):
    if failed.name!='episode.json' or failed.is_symlink() or not failed.resolve().is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the closed private failed capture')
    old=closed(preparation);p=closed(stage);f=json.loads(failed.read_text())
    runtime={k:identity(k) for k in ('worldserver','modern_world','client')};before=snapshot()
    validate(p,f,before,runtime,bound(stage),bound(preparation))
    if p['sources'][0]!=bound(preparation) or actors.load()!=f['actor']:
        raise RuntimeError('prepared source or current Hunter registration differs')
    stop_path=Path(p['primary_stop_source']['path']);stop=closed(stop_path)
    if (bound(stop_path)!=p['primary_stop_source'] or stop.get('phase')!='user_requested_primary_client_stopped' or
        stop.get('action')!='stop_owned_primary_client' or stop.get('actor',{}).get('guid')!=1 or
        stop.get('input_sent') is not False or stop.get('runtime',{}).get('worldserver')!=runtime['worldserver'] or
        len(stop.get('checks',{}))!=8 or
        not all(v is True for v in stop['checks'].values()) or stop.get('before')!=stop.get('after') or
        before['1']!=stop['after']):raise RuntimeError('original primary stop differs')
    c=f['capture_config'];requests=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if
        r.get('session')==c['session'] and c['created_at']<=r.get('time',0)<=f['capture_until'] and
        (r.get('name'),r.get('direction'))==('CMSG_PLAYER_LOGIN','to_native')]
    if requests or any((lab.ROOT/'run'/n).exists() for n in ('owned_entry_request_probe.json',
        'owned_tame_request_probe.json','owned_pet_abandon_probe.json','owned_stable_request_probe.json')):
        raise RuntimeError('cannot retire an armed capture or an attempt that sent native login')
    with actor('primary'):
        if lab.owned_process('client'):raise RuntimeError('primary must remain stopped')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original registration differs')
    return p,f,before,runtime


def retire(t,preparation,stage,failed,p,f,before,runtime):
    if t.receipt['runtime']!=runtime or snapshot()!=before:raise RuntimeError('retirement preflight changed')
    monitor=owned_input.focus();game=monitor['input_isolation']['game_pid'];ticks=lab.proc_start(game)
    t.receipt.update(source=bound(failed),preparation_source=bound(preparation),stage_source=bound(stage),
        primary_stop_source=p['primary_stop_source'],before=before,
        game_before={'pid':game,'start_ticks':ticks},frame=shot(t.out/'failed_loading_screen.png'),
        action='stop_owned_scout_after_captured_no_login',input_sent=False,qualification_added=False,
        no_login_recovery={'native_login_requests':[],'capture_disarmed':True,'snapshot_unchanged':True,
            'captured_requests':f['capture_packets'],'ordinary_input_replayed':False});t.persist()
    lab.stop('client');after=snapshot()
    with actor('primary'):primary_absent=lab.owned_process('client') is None
    checks={'scout_launcher_absent':lab.owned_process('client') is None,'owned_game_absent':gone(game,ticks),
        'all_retained_saved_state':after==before,'all_characters_offline':all(v['native']['online']==0 for v in after.values()),
        'primary_still_stopped':primary_absent and after['1']==before['1'],
        'native_lifetime':identity('worldserver')==runtime['worldserver'],
        'bridge_lifetime':identity('modern_world')==runtime['modern_world'],
        'origin_registration':actors.load()==p['actor']}
    t.receipt.update(after=after,checks=checks,completed=all(checks.values()),phase='parked_scout_resource_paused')
    if not all(checks.values()):raise RuntimeError('captured no-login retirement preservation differs')


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','stage','failed','output'):a.add_argument('--'+name,type=Path,required=True)
    a=a.parse_args()
    with actor('scout'):
        p,f,before,runtime=preflight(a.preparation,a.stage,a.failed)
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:retire(t,a.preparation,a.stage,a.failed,p,f,before,runtime)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
