"""Inspect an owned player chat-link menu from a reviewed attributable seed."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import controls
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


def play(t,source,review_path,point):
    source=source.resolve();review_path=review_path.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence') or \
        not review_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires private owned seed and review sources')
    old=json.loads(source.read_text());peer=json.loads((source.parent.parent/'scout/episode.json').read_text())
    seed=old['player_link_seed']
    if (not old['completed'] or not old.get('finished_at') or old['actor']!=t.fixture or
        old['runtime']!=t.receipt['runtime'] or t.fixture['actor']!='primary' or t.fixture['guid']!=1 or
        not peer['completed'] or peer['actor']['guid']!=2 or
        seed['expected_native_guid']!=2 or not all(seed['checks'].values()) or
        any(len(d['native_restoration']['checks'])!=10 or not all(d['native_restoration']['checks'].values())
            for d in [old,peer])):
        raise RuntimeError('closed owned chat seed or its restoration differs')
    review=json.loads(review_path.read_text());frame=review['frame'];image=review_path.parent/frame['file']
    monitor=frame['monitor'];current=owned_input.focus()
    if (review.get('source_sha256')!=lab.sha256(source) or review.get('point')!=point or
        not image.is_relative_to(lab.ROOT/'evidence') or lab.sha256(image)!=frame['sha256'] or
        not monitor.get('second_monitor_verified') or monitor['pid']!=t.receipt['runtime']['client']['pid'] or
        monitor['input_isolation']['actor']!='primary' or
        monitor['input_isolation']['game_pid']!=current['input_isolation']['game_pid'] or
        not 0<=time.time()-image.stat().st_mtime<=120):
        raise RuntimeError('fresh reviewed owned chat-link point differs')
    state,_=t.observe('player_link_seed_guard')
    matches=[r for r in state.get('chat_probes',[]) if r.get('event')=='CHAT_MSG_WHISPER' and
        r.get('text')==seed['token'] and r.get('sender')==seed['observed_sender']]
    if len(matches)!=1:raise RuntimeError('fresh public owned chat seed differs')
    t.receipt.update(seed_source={'path':str(source),'sha256':lab.sha256(source)},
        reviewed_link={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':frame});t.persist()
    def outcome(b,a,s):
        rows=controls(t);state,frame=t.observe('owned_player_menu_rendered')
        t.receipt['player_menu']={'controls':rows,'state':state,'frame':frame};t.persist()
        return {'status':'owned_player_menu_inspected' if s=='menu' and
            any('whisper' in c['text'].lower() for c in rows) else 'client_or_protocol_failure'}
    try:
        require(t.step('fixture.player_chat_link_menu','Right-click the reviewed owned player chat link.',
            {'menu':{'kind':'click','value':point,'button':3,'hold':1.2}},outcome,diagnostic_action='menu'),
            'owned_player_menu_inspected')
    finally:t.clean_panels()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','review','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:native_suite(t,operations=lambda t:play(t,a.source,a.review,a.point),preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
