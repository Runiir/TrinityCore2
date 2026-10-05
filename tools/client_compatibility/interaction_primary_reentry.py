"""Recover a primary deployment precheck interrupted by an ordinary prior logout."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,actors,owned_input
from .interaction_trial import Trial
from .interaction_bridge_restoration import restore
from .interaction_bridge_deploy import shot
from .interaction_quest_link import detail,saved
from .interaction_quest_settings import snapshot as settings
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_ground_movement import position
from .observation.journal import Cursor
from .interaction_quest_selection_recovery import LAYOUT,NATIVE


def baseline_matches(old,current):
    native=old.get('native_restoration',{}).get('checks',{})
    layout=old.get('quest_link_restoration',{}).get('checks',{})
    return (old.get('completed') is True and old.get('failure') is None and old.get('finished_at') and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('quest_trial_kind')=='link' and old.get('quest_no_message_request') is True and
        old.get('quest_link_original',{}).get('selection')==0 and
        set(native)==NATIVE and all(v is True for v in native.values()) and
        set(layout)==LAYOUT and all(v is True for v in layout.values()))


def enter(t,baseline_source,interrupted_source,review_path):
    paths=[p.resolve() for p in (baseline_source,interrupted_source,review_path)]
    if any(not p.is_relative_to(lab.ROOT/'evidence') for p in paths):raise ValueError('requires owned closed evidence')
    baseline_source,interrupted_source,review_path=paths
    old=json.loads(baseline_source.read_text());interrupted=json.loads(interrupted_source.read_text())
    if not baseline_matches(old,t.receipt) or t.fixture['guid']!=1:
        raise RuntimeError('last fully restored primary baseline differs')
    if (interrupted.get('completed') is not False or not interrupted.get('finished_at') or
        interrupted.get('failure')!='RuntimeError: UI observation did not become decodable' or
        interrupted.get('actor')!=t.fixture or interrupted.get('runtime')!=t.receipt['runtime'] or
        interrupted.get('cases') or interrupted.get('cleanup')):
        raise RuntimeError('interrupted deployment precheck differs or sent gameplay input')
    review=json.loads(review_path.read_text());frame=review.get('frame',{});image=review_path.parent/frame.get('file','')
    current=owned_input.focus();monitor=frame.get('monitor',{})
    if (review.get('reviewed') is not True or review.get('episode_sha256')!=lab.sha256(interrupted_source) or
        review.get('selected_character')!='Harnessone' or review.get('selected_level')!=85 or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        frame.get('sha256')!=lab.sha256(image) or not 0<=time.time()-image.stat().st_mtime<=120 or
        not monitor.get('second_monitor_verified') or monitor.get('pid')!=t.receipt['runtime']['client']['pid'] or
        monitor.get('input_isolation',{}).get('actor')!='primary' or
        monitor.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh owned primary selection review differs')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT name,level,online FROM client442_characters.characters WHERE guid=1 AND account=%s',
                  (t.fixture['account_id'],))
        if q.fetchone()!=('Harnessone',85,0):raise RuntimeError('reviewed primary is not offline at its original identity')
    native=old['native_baseline']
    if known(1)!=native['spells'] or saved_actions(1)!=native['actions'] or position(1)!=native['position']:
        raise RuntimeError('offline native primary differs from the restored baseline')
    prepared=Path(old['source']['file'])
    if not prepared.resolve().is_relative_to(lab.ROOT/'evidence') or lab.sha256(prepared)!=old['source']['sha256']:
        raise RuntimeError('original settings/group baseline source differs')
    prior=json.loads(prepared.read_text())
    t.receipt.update(baseline_source={'file':str(baseline_source),'sha256':lab.sha256(baseline_source)},
        interrupted_source={'file':str(interrupted_source),'sha256':lab.sha256(interrupted_source)},
        selection_review_source={'file':str(review_path),'sha256':lab.sha256(review_path)},
        custom_script_permission='blocked_by_user',qualified_scope=
        'Preparation recovery only: one reviewed ordinary same-character entry after a preexisting logout. No gameplay qualification or server deployment.');t.persist()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time()
    t.io.key('Return',hold=1.2);state,frame=t.observe('primary_reentered',seconds=240)
    session=actors.session_entry(t.fixture)['session']
    rows=[r for r in cursor.poll() if r.get('session')==session and r.get('time',0)>=started and
          r.get('name') in ('CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD')]
    checks={'same_character':state.get('player')=='Harnessone' and state.get('level')==85 and state.get('guid')==t.guid,
        'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in rows),
        'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in rows)}
    t.receipt.update(reentry_checks=checks,reentry_frame=frame,session=session);t.persist()
    if not all(checks.values()):raise RuntimeError('ordinary primary reentry did not match')
    restore(t,native);state,quest=detail(t,'primary_reentry_quest');current_settings=settings(t,'primary_reentry_settings')
    restore(t,native)
    checks={'quest_layout':quest==old['quest_link_original'],'native_quests':saved(1)==old['quest_link_native_original'],
        'group':state['group']==prior['quest_original_group'],
        **{k:current_settings.get(k)==prior['original_settings'].get(k) for k in ('cvars','values','category','search','unapplied')}}
    t.receipt['primary_reentry_restoration']={'checks':checks};t.persist()
    if not all(checks.values()):raise RuntimeError('original primary quest/settings baseline did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline-source',type=Path,required=True);p.add_argument('--interrupted-source',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code',chat_key_hold=1.2)
    try:enter(t,a.baseline_source,a.interrupted_source,a.review);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt[k] for k in ('completed','failure')}),flush=True)
