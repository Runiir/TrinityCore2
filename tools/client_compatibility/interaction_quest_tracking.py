"""Toggle stock low-level quest tracking and retain the visible NPC marker frames."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_quest_reward import detail
from .interaction_quest_fixture import quest_state
from .interaction_trade import inventory
from .interaction_operations import click_case
from .interaction_macros import require
from .npc_fixture import NpcFixture

LABEL='Low Level Quests'


def tracking(t,label):
    rows=detail(t,label).get('tracking',[])
    selected=[r for r in rows if r.get('name')==LABEL]
    if len(selected)!=1 or type(selected[0].get('active'))is not bool:
        raise RuntimeError('public tracking catalog lacks one boolean low-level quest setting')
    return rows


def open_menu(t,point,label):
    state,_=t.observe('tracking_menu_precheck_'+label)
    if any(p in state['panels'] for p in ['ContextMenu','DropDownList1']):return
    require(t.step('tracking.menu.'+label,'Open minimap tracking.',
        {'open':{'kind':'click','value':point,'description':'Click the freshly reviewed minimap tracking button.'}},
        lambda b,a,s:{'status':'tracking_menu_pass' if s=='open' and any(
            p in a['panels'] for p in ['ContextMenu','DropDownList1']) else 'client_or_protocol_failure'},
        diagnostic_action='open'),'tracking_menu_pass')


def change(t,point,expected,label,baseline):
    open_menu(t,point,label)
    def outcome(b,a,s):
        rows=tracking(t,'tracking_result_'+label)
        wanted=[{**r,'active':expected} if r['name']==LABEL else r for r in baseline]
        passed=s and rows==wanted
        t.receipt.setdefault('tracking_oracles',{})[label]={'public':rows,'expected':wanted,'passed':bool(passed)};t.persist()
        return {'status':'tracking_filter_pass' if passed else 'client_or_protocol_failure',
            'oracle':t.receipt['tracking_oracles'][label]}
    require(click_case(t,'tracking.low_level.'+label,('Show' if expected else 'Hide')+' low-level quest markers.',
        lambda c:c['text']==LABEL,outcome),'tracking_filter_pass')
    t.clean_panels();state,frame=t.observe('marker_'+label)
    t.receipt.setdefault('marker_frames',{})[label]={'state':state,'frame':frame};t.persist()


def suite(t,review_file):
    actors.session_entry(t.fixture);t.clean_panels();quests,items=quest_state(1),inventory()
    baseline=tracking(t,'tracking_baseline');setting=next(r for r in baseline if r['name']==LABEL)
    if setting['active']:raise RuntimeError('requires the ordinary disabled low-level quest setting')
    t.receipt['baseline']={'quests':quests,'inventory_money':items,'tracking':baseline};t.persist()
    fixture=NpcFixture(t.out,t.fixture,261,2);point=None
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact Guard Thomas'})
        state,frame=t.observe('tracking_button_staged');t.receipt['tracking_staging']={'state':state,'frame':frame};t.persist()
        deadline=time.monotonic()+60
        while not review_file.is_file() and time.monotonic()<deadline:time.sleep(.2)
        review=json.loads(review_file.read_text());point=review.get('point')
        if (review.get('guid')!=t.guid or review.get('frame_sha256')!=frame['sha256'] or
            not isinstance(point,list) or len(point)!=2 or any(type(v)is not int or not 0<=v<b for v,b in zip(point,[1280,720]))):
            raise RuntimeError('tracking point lacks a fresh bounded screenshot review')
        t.receipt['point_review']=review;t.persist()
        change(t,point,True,'enabled',baseline)
        change(t,point,False,'disabled',baseline)
    finally:
        try:
            if point and tracking(t,'tracking_restore_check')!=baseline:
                change(t,point,False,'cleanup_disabled',baseline)
            t.clean_panels()
        finally:fixture.restore()
        checks={'quests_unchanged':quest_state(1)==quests,'inventory_money_unchanged':inventory()==items,
            'tracking_restored':tracking(t,'tracking_restored')==baseline}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('tracking trial did not restore its exact baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--review-point-file',type=Path,required=True);a=p.parse_args()
    if a.review_point_file.exists():p.error('require a fresh staged screenshot review')
    t=Trial(a.output,controller='code')
    try:suite(t,a.review_point_file);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
