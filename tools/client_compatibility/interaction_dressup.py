"""Preview owned swords, rotate and reset the stock model with ordinary inputs."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .interaction_inventory_moves import slot_control
from .interaction_weapon_swap import open_fixture
from .interaction_tooltips import baseline,items
from .interaction_equipment_set_roundtrip import stable
from .observation.inventory import Inventory
from .interaction_observation import read_current_page
from .interaction_bridge_deploy import shot


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'dressup',lambda s:s.get('dressup_probe') and
        (ready is None or ready(s['dressup_probe'])))
    t.receipt.setdefault('model_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['dressup_probe'],frame


def preview(t,control,item,label):
    before,frame=t.observe(label+'_before');since=time.time()
    row={'id':label,'time':since,'status':'started','before':before,'before_frame':frame,
        'input':{'modifier':'ctrl','kind':'click','value':point(control)},'native_item':item}
    t.receipt['cases'].append(row);t.persist()
    with t.io.hold_modifier('ctrl'):t.io.click(*point(control))
    deadline=time.monotonic()+16
    while True:
        after,frame=t.observe(label+'_after')
        if after.get('dressup_visible'):break
        if time.monotonic()>deadline:raise RuntimeError('stock preview did not settle; refusing input replay')
        time.sleep(.2)
    def requested(model):
        match=re.search(r'item:(\d+)',(model.get('last_try_on') or {}).get('link',''))
        return model.get('model_visible') and model.get('geometry_ready') is True and bool(match and int(match[1])==item['id'])
    model,model_frame=detail(t,label+'_model',requested)
    event=model.get('last_try_on') or {};match=re.search(r'item:(\d+)',event.get('link',''))
    checks={'observed_control':bool(control),'ordinary_modified_click':bool(event.get('ctrl') and event.get('dressup')),
        'native_item_link':bool(match and int(match[1])==item['id']),
        'visible_model':model.get('visible') and model.get('model_visible'),
        'geometry_ready':model.get('geometry_ready') is True,'model_facing_available':isinstance(model.get('facing'),(int,float)),
        'native_fixture_preserved':stable(baseline())==t.dressup_baseline,
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
    row.update(after=after,after_frame=frame,model_frame=model_frame,oracle={'checks':checks,'model':model},
        status='stock_dressup_preview_pass' if all(checks.values()) else 'client_or_protocol_failure');t.persist()
    require(row,'stock_dressup_preview_pass');return model


def rotate(t,name,label):
    before,_=detail(t,label+'_before');facing=before['facing']
    def moved(model):return abs(model.get('facing',facing)-facing)>1e-4
    def outcome(b,a,s):
        model,frame=detail(t,label+'_model',moved)
        return {'status':'stock_dressup_rotation_pass' if s and moved(model) and
            not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure',
            'oracle':{'facing_before':facing,'model_after':model,'frame':frame}}
    require(click_case(t,label,'Rotate the stock dress-up model through its observed arrow.',
        lambda c:c['name']==name,
        outcome),
        'stock_dressup_rotation_pass')


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    t.clean_panels();state,_=t.observe('dressup_fixture')
    if state.get('observer_version',0)<66:raise RuntimeError('requires paged dress-up observer66')
    t.dressup_baseline=stable(baseline());worn=oracle.equipment(16);stored=oracle.slot(0,10)
    catalog,digest=items([worn['id'],stored['id']])
    if worn['id']!=78478 or stored['id']!=49778:raise RuntimeError('requires exact owned Gurthalak/Worn Greatsword fixture')
    t.receipt.update(baseline=t.dressup_baseline,native_session=session,
        fixture={'worn':worn,'stored':stored,'catalog':catalog,'catalog_sha256':digest},
        qualified_scope='Stock ctrl-click previews of two owned swords, visible model rotation, reset and close. Native equipment and resources stay unchanged. Other item types and model frames remain open.');t.persist()
    try:
        open_fixture(t)
        matches=[c for c in controls(t) if c['name']=='CharacterMainHandSlot']
        if len(matches)!=1:raise RuntimeError('observed equipped sword slot is absent')
        original=preview(t,matches[0],worn,'ui_misc.dressup_open')
        control=slot_control(t,0,10)
        if control is None:raise RuntimeError('owned backpack sword is not visible')
        preview(t,control,stored,'ui_misc.dressup_item')
        rotate(t,'DressUpModelFrameRotateRightButton','ui_misc.dressup_rotate.right')
        rotate(t,'DressUpModelFrameRotateLeftButton','ui_misc.dressup_rotate.left')
        def reset_outcome(b,a,s):
            model,frame=detail(t,'dressup_reset_model',lambda model:
                model.get('mainhand_appearance')==original.get('mainhand_appearance') and model.get('geometry_ready') is True)
            return {'status':'stock_dressup_reset_pass' if s and not a.get('lua_errors') and
                not a.get('blocked_actions') else 'client_or_protocol_failure',
                'oracle':{'original_model':original,'reset_model':model,'frame':frame}}
        require(click_case(t,'dressup.reset','Reset the preview to the normally worn equipment.',
            lambda c:c['name']=='DressUpFrameResetButton',
            reset_outcome),
            'stock_dressup_reset_pass')
        require(click_case(t,'ui_misc.dressup_close','Close the stock dress-up window.',
            lambda c:c['name']=='DressUpFrameCancelButton',
            lambda b,a,s:{'status':'stock_dressup_close_pass' if s and 'DressUpFrame' not in a['panels'] else
                'client_or_protocol_failure'},await_state=lambda a:'DressUpFrame' not in a['panels']),
            'stock_dressup_close_pass')
    finally:
        try:t.clean_panels()
        finally:
            t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==t.dressup_baseline;t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('dress-up preview changed the native fixture')


def recover(t,source):
    """Close the visually reviewed stock model left by the exact overflow trial."""
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require an owned failed dress-up episode')
    old=json.loads(source.read_text());original=stable(baseline())
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old.get('completed') or
        not old.get('finished_at') or old.get('failure')!='RuntimeError: UI observation did not become decodable' or
        old.get('native_resources_preserved') is not True or old.get('native_after')!=original):
        raise RuntimeError('exact overflow source and native/client baseline differ')
    frame=shot(t.out/'overflow_recovery_before.png')
    t.receipt.update(recovery_source={'file':str(source),'sha256':lab.sha256(source)},baseline=original,
        qualified_scope='Cleanup only: close the separately visually reviewed stock dressing window; no gameplay qualification.',
        cleanup_input={'kind':'key','value':'Escape','before_frame':frame});t.persist()
    t.execute({'kind':'key','value':'Escape'})
    state,frame=t.observe('model_closed',seconds=60)
    if 'DressUpFrame' in state['panels']:raise RuntimeError('one Escape did not close the stock model')
    t.receipt['model_closed']={'state':state,'frame':frame};t.persist();t.clean_panels()
    t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('overflow cleanup changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recover-overflow',type=Path);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:
        if a.recover_overflow:recover(t,a.recover_overflow)
        else:suite(t)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
