"""Reenter the reviewed owned primary after idle logout without restarting it."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_bridge_deploy import identity,shot
from .interaction_bridge_restoration import restore
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_ground_movement import position
from .observation.journal import Cursor


def source(t,failed_path,baseline_path):
    for p in [failed_path,baseline_path]:
        if p.name!='episode.json' or not p.resolve().is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires owned private episode sources')
    failed=json.loads(failed_path.read_text());old=json.loads(baseline_path.read_text())
    if (t.fixture['actor']!='primary' or t.fixture['guid']!=1 or failed['actor']!=t.fixture or
        old['actor']!=t.fixture or failed['runtime']!=t.receipt['runtime'] or old['runtime']!=t.receipt['runtime'] or
        failed.get('completed') or not failed.get('finished_at') or failed.get('native_baseline') or
        failed.get('cases') or failed.get('failure')!='RuntimeError: UI observation did not become decodable' or
        not old.get('completed') or not old.get('finished_at')):
        raise RuntimeError('failed preflight or completed primary baseline differs')
    p=baseline_path.parent.parent/'deployment.json';deployment=json.loads(p.read_text())
    attempt=deployment['reconnect_attempts']['primary'];checks=old['bridge_native_restoration']['checks']
    if (not deployment['completed'] or not deployment['native_unchanged'] or len(checks)!=9 or
        not all(checks.values()) or attempt['episode']!=str(baseline_path.resolve()) or
        attempt['sha256']!=lab.sha256(baseline_path) or deployment['native']!=identity('worldserver') or
        deployment['after']!=identity('modern_world')):
        raise RuntimeError('completed deployment source is not bound to the current lifetime')
    return deployment


def run(t,failed_path,baseline_path,review_path):
    deployment=source(t,failed_path,baseline_path);base=deployment['native_baselines']['primary']
    review=json.loads(review_path.read_text());frame=review['frame'];image=review_path.parent/frame['file']
    current=owned_input.focus();monitor=frame['monitor']
    if (review.get('failed_episode_sha256')!=lab.sha256(failed_path) or
        review.get('baseline_episode_sha256')!=lab.sha256(baseline_path) or lab.sha256(image)!=frame['sha256'] or
        not monitor.get('second_monitor_verified') or monitor['pid']!=t.receipt['runtime']['client']['pid'] or
        monitor['input_isolation']['actor']!='primary' or
        monitor['input_isolation']['game_pid']!=current['input_isolation']['game_pid'] or
        not 0<=time.time()-image.stat().st_mtime<=120):
        raise RuntimeError('fresh reviewed primary selection differs')
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=1 AND account=%s',
            (t.fixture['account_id'],))
        offline=q.fetchone()==(0,)
    if not offline or known(1)!=base['spells'] or saved_actions(1)!=base['actions'] or position(1)!=base['position']:
        raise RuntimeError('offline primary differs from the completed deployment baseline')
    t.receipt.update(sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in [failed_path,baseline_path]],
        reviewed_selection={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':frame},
        selection_before=shot(t.out/'selection_before.png'));t.persist()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time();t.io.key('Return',hold=1.2);time.sleep(8)
    state,frame=t.observe('primary_idle_reentered',seconds=240)
    session=actors.session_entry(t.fixture)['session']
    packets=[{k:r[k] for k in ['time','name','direction']} for r in cursor.poll() if r.get('session')==session and
        r.get('time',0)>=started and r.get('name') in ['CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD']]
    checks={'owned_name':state['player']=='Harnessone','owned_guid':state['guid']==t.guid,'level':state['level']==85,
        'public_baseline':all(state.get(k)==v for k,v in deployment['baselines']['primary'].items()),
        'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in packets),
        'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in packets)}
    t.receipt.update(reentry_checks=checks,packets=packets,frame=frame,session=session);t.persist()
    if not all(checks.values()):raise RuntimeError('owned primary reentry differs')
    restore(t,base)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['failed-source','baseline','review','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:run(t,a.failed_source,a.baseline,a.review);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
