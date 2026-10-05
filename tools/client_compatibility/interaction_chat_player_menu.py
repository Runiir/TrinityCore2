"""Inspect an owned player chat-link menu from a reviewed attributable seed."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import controls,point as control_point
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_chat_history import scroll


def inspect(t,source):
    old=json.loads(source.read_text())
    if not old.get('completed') or old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']:
        raise RuntimeError('completed owned chat seed differs')
    probe=detail(t,'player_link_window_layout');rows=controls(t)
    state,frame=t.observe('player_link_window_layout_rendered')
    t.receipt['player_link_layout']={'public':probe,'controls':rows,'state':state,'frame':frame};t.persist()


def prepare(t,source,review_path):
    """Reveal retained history, then accept a hash-bound visual review once."""
    if review_path.exists():raise RuntimeError('review path must be new')
    seed_source(t,source)
    before=detail(t,'player_link_history_original');row=before['windows'][0]
    if before['selected']!=1 or row['name']!='General' or row['scroll_offset']!=0 or 'WHISPER' not in before['message_types']:
        raise RuntimeError('requires original General whisper history at bottom')
    rows=controls(t);up=[r for r in rows if r['name']=='ChatFrame1ButtonFrameUpButton' and r.get('enabled')]
    if len(up)!=1:raise RuntimeError('requires one observed history up button')
    t.receipt['player_link_history_baseline']=before;t.persist()
    try:
        t.io.click(*control_point(up[0]),hold=1.2);time.sleep(1)
        state,frame=t.observe('player_link_revealed')
        t.receipt['player_link_reveal']={'control':up[0],'input':{'point':control_point(up[0]),'hold':1.2},
            'state':state,'frame':frame};t.persist()
        print(json.dumps({'review_ready':str(t.out/'episode.json'),'frame':frame['file']}),flush=True)
        deadline=time.monotonic()+180
        while not review_path.exists():
            if time.monotonic()>deadline:raise RuntimeError('visual review did not arrive; no link input sent')
            time.sleep(1)
        review=json.loads(review_path.read_text())
        play(t,source,review_path,review['point'])
    finally:
        t.clean_panels();after=detail(t,'player_link_history_cleanup')
        if after['selected']!=1:raise RuntimeError('unexpected chat selection during history cleanup')
        if after['windows'][0]['scroll_offset']!=0:
            scroll(t,'fixture.player_link_history_bottom','ChatFrame1ButtonFrameBottomButton',
                after['windows'][0]['message_count'],lambda offset:offset==0)
        after=detail(t,'player_link_history_restored')
        checks={'settings_and_offset':signature(before)==signature(after),
            'message_count':row['message_count']==after['windows'][0]['message_count']}
        t.receipt['player_link_history_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original player-link history differs')


def seed_source(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires private owned seed source')
    old=json.loads(source.read_text());peer=json.loads((source.parent.parent/'scout/episode.json').read_text())
    seed=old['player_link_seed']
    if (not old['completed'] or not old.get('finished_at') or old['actor']!=t.fixture or
        old['runtime']!=t.receipt['runtime'] or t.fixture['actor']!='primary' or t.fixture['guid']!=1 or
        not peer['completed'] or peer['actor']['guid']!=2 or
        seed['expected_native_guid']!=2 or not all(seed['checks'].values()) or
        any(len(d['native_restoration']['checks'])!=10 or not all(d['native_restoration']['checks'].values())
            for d in [old,peer])):
        raise RuntimeError('closed owned chat seed or its restoration differs')
    return seed


def play(t,source,review_path,point):
    source=source.resolve();review_path=review_path.resolve();seed=seed_source(t,source)
    t.receipt['seed_source']={'path':str(source),'sha256':lab.sha256(source)};t.persist()
    reviewed_menu(t,seed,review_path,point,lab.sha256(source))


def reviewed_menu(t,seed,review_path,point,source_sha256):
    review_path=review_path.resolve()
    if not review_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires private owned review source')
    review=json.loads(review_path.read_text());frame=review['frame'];image=review_path.parent/frame['file']
    monitor=frame['monitor'];current=owned_input.focus()
    if (review.get('approved') is not True or not isinstance(point,list) or len(point)!=2 or
        any(type(v) is not int for v in point) or not 0<=point[0]<1280 or not 0<=point[1]<720 or
        review.get('source_sha256')!=source_sha256 or review.get('point')!=point or
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
    t.receipt['reviewed_link']={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':frame};t.persist()
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


def live_seed_valid(t,peer,seed):
    return (t.fixture['actor']=='primary' and t.fixture['guid']==1 and
        peer.fixture['actor']=='scout' and peer.fixture['guid']==2 and
        seed['expected_native_guid']==2 and bool(seed['checks']) and all(seed['checks'].values()) and
        bool(t.receipt.get('native_baseline')) and bool(peer.receipt.get('native_baseline')))


def live(t,peer,seed,review_path):
    if not live_seed_valid(t,peer,seed) or review_path.exists():
        raise RuntimeError('owned live cohort seed differs')
    source=t.out/'player_link_seed_source.json';lab.private_write(source,json.dumps(seed,indent=2)+'\n')
    state,frame=t.observe('player_link_live_review')
    t.receipt['player_link_live_review']={'frame':frame,'source_sha256':lab.sha256(source)};t.persist()
    print(json.dumps({'review_ready':str(t.out/'episode.json'),'frame':frame['file']}),flush=True)
    deadline=time.monotonic()+90
    while not review_path.exists():
        if time.monotonic()>deadline:raise RuntimeError('fresh link visual review absent; no input sent')
        time.sleep(1)
    review=json.loads(review_path.read_text());reviewed_menu(t,seed,review_path,review.get('point'),lab.sha256(source))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path);p.add_argument('--point',type=int,nargs=2)
    p.add_argument('--inspect',action='store_true');p.add_argument('--await-review',action='store_true');a=p.parse_args()
    if a.inspect and a.await_review:p.error('choose inspect or await-review')
    if a.await_review and (not a.review or a.point):p.error('await-review requires a new review file and no point')
    if not a.inspect and not a.await_review and (not a.review or not a.point):p.error('menu input requires the reviewed link point')
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:
            native_suite(t,operations=lambda t:inspect(t,a.source) if a.inspect else
                prepare(t,a.source,a.review) if a.await_review else play(t,a.source,a.review,a.point),
                preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
