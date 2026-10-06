"""Park a retained fixture after an attributable failed native entry already logged it out."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,character,saved,pets,SCRIPT_BOUNDARY
from .interaction_bridge_deploy import shot
from .observation.journal import entries


def failed_source(t,path,preparation):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned failed class entry')
    failed=json.loads(path.read_text())
    if (failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!='RuntimeError: UI observation did not become decodable' or
        failed.get('phase')!='owned_class_entry_started' or failed.get('actor')!=t.fixture or
        failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation)):
        raise RuntimeError('failed class entry source differs')
    return failed


def recover(t,preparation,failed_path):
    old=prepared(t,preparation);failed=failed_source(t,failed_path,preparation)
    events=[]
    for row in entries(lab.ROOT/'logs/modern_world.jsonl'):
        if failed['started_at']<=row.get('time',0)<=failed['finished_at'] and row.get('event') in (
            'native_player_created','native_stream_closed','world_connection_closed'):
            events.append(row)
    created=[r for r in events if r.get('event')=='native_player_created' and r.get('guid')==t.fixture['guid']]
    if len(created)!=1:raise RuntimeError('failed entry has no unique attributable native creation')
    session=created[0]['session']
    closed=[r for r in events if r.get('session')==session and r.get('event')=='native_stream_closed' and
        r.get('error')=='native pet talent update is not yet translated']
    if len(closed)!=1:raise RuntimeError('native pet-talent disconnect is not attributable')
    checks=origin_checks(old);guid=t.fixture['guid'];account=t.fixture['account_id']
    row=character(guid,account);current_saved=saved(guid);current_pets=pets(guid)
    keys=lambda rows:sorted((r['id'],r['entry'],r['owner']) for r in rows)
    checks.update(class_offline=row['online']==0,natural_saved_rows=current_saved==old['natural_saved'],
        retained_pet_identity=keys(current_pets)==keys(old['retained_class_pets']))
    if not all(checks.values()):raise RuntimeError('disconnected class or original actor state differs')
    t.receipt.update(failed_entry_source={'path':str(failed_path.resolve()),'sha256':lab.sha256(failed_path)},
        native_disconnect_events=[r for r in events if r.get('session')==session],recovery_checks=checks,
        input_sent=False,retained_class_fixture=row,retained_class_saved=current_saved,retained_class_pets=current_pets,
        checks={k:checks[k] for k in ['original_character','original_saved_rows','native_worldserver','class_offline']},
        qualified_scope='Offline class registration recovery after the native stream already disconnected. No logout input or gameplay qualification.')
    t.persist()
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original actor registration differs')
    t.receipt.update(completed=True,phase='await_original_selection_review',frame=shot(t.out/'origin_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','failed-entry','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:recover(t,a.preparation,a.failed_entry)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure','phase']}),flush=True)
