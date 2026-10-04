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


def preview(t,control,item,label):
    before,frame=t.observe(label+'_before');since=time.time()
    row={'id':label,'time':since,'status':'started','before':before,'before_frame':frame,
        'input':{'modifier':'ctrl','kind':'click','value':point(control)},'native_item':item}
    t.receipt['cases'].append(row);t.persist()
    with t.io.hold_modifier('ctrl'):t.io.click(*point(control))
    deadline=time.monotonic()+16
    while True:
        after,frame=t.observe(label+'_after');model=after.get('dressup') or {}
        event=model.get('last_try_on') or {};match=re.search(r'item:(\d+)',event.get('link',''))
        if model.get('model_visible') and match and int(match[1])==item['id']:break
        if time.monotonic()>deadline:raise RuntimeError('stock preview did not settle; refusing input replay')
        time.sleep(.2)
    checks={'observed_control':bool(control),'ordinary_modified_click':bool(event.get('ctrl') and event.get('dressup')),
        'native_item_link':bool(match and int(match[1])==item['id']),
        'visible_model':model.get('visible') and model.get('model_visible'),
        'geometry_ready':model.get('geometry_ready') is True,'model_facing_available':isinstance(model.get('facing'),(int,float)),
        'native_fixture_preserved':stable(baseline())==t.dressup_baseline,
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
    row.update(after=after,after_frame=frame,oracle={'checks':checks,'model':model},
        status='stock_dressup_preview_pass' if all(checks.values()) else 'client_or_protocol_failure');t.persist()
    require(row,'stock_dressup_preview_pass');return model


def rotate(t,name,label):
    before,_=t.observe(label+'_before');facing=before['dressup']['facing']
    def moved(a):return abs((a.get('dressup') or {}).get('facing',facing)-facing)>1e-4
    require(click_case(t,label,'Rotate the stock dress-up model through its observed arrow.',
        lambda c:c['name']==name,
        lambda b,a,s:{'status':'stock_dressup_rotation_pass' if s and moved(a) and
            not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure',
            'oracle':{'facing_before':facing,'model_after':a.get('dressup')}},await_state=moved),
        'stock_dressup_rotation_pass')


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    t.clean_panels();state,_=t.observe('dressup_fixture')
    if state.get('observer_version',0)<65:raise RuntimeError('requires passive dress-up observer65')
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
        require(click_case(t,'dressup.reset','Reset the preview to the normally worn equipment.',
            lambda c:c['name']=='DressUpFrameResetButton',
            lambda b,a,s:{'status':'stock_dressup_reset_pass' if s and
                (a.get('dressup') or {}).get('mainhand_appearance')==original.get('mainhand_appearance') and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure',
                'oracle':{'original_model':original,'reset_model':a.get('dressup')}},
            await_state=lambda a:(a.get('dressup') or {}).get('mainhand_appearance')==original.get('mainhand_appearance')),
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


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
