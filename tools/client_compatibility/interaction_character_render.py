"""Render gear visibility through stock character controls and a read-only camera."""
import math
from .interaction_equipment_sets import detail
from .interaction_equipment_set_roundtrip import open_character
from .interaction_operations import controls,point,click_case
from .interaction_macros import require


def angle(value):return (value+math.pi)%(2*math.pi)-math.pi


def yaw(t,label):
    model=detail(t,label)['model'];value=model.get('yaw')
    if not model['visible'] or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise RuntimeError('visible stock character camera is unavailable')
    return value


def rotate(t,target,label):
    current=yaw(t,label+'_before');rate=None
    for i in range(8):
        error=angle(target-current)
        if abs(error)<=.2:return current
        # Installed OrbitCamera yaw is reduced by a right-button increment.
        key='rotateLeftButton' if error>0 else 'rotateRightButton'
        buttons=[c for c in controls(t) if c.get('model_control')==key and c['enabled']]
        if len(buttons)!=1:raise RuntimeError('owned stock model rotation control is ambiguous or absent')
        hold=min(2,max(.15,abs(error)/rate)) if rate else .6
        before=current
        def outcome(b,a,s):
            nonlocal current,rate
            current=yaw(t,label+'_'+str(i));moved=angle(current-before)
            okay=s=='rotate' and .005<abs(moved)<math.pi and moved*error>0
            if okay:rate=abs(moved)/hold
            return {'status':'stock_camera_rotation_pass' if okay else 'client_or_protocol_failure',
                'oracle':{'yaw_before':before,'yaw_after':current,'target':target,'hold':hold,
                    'ordinary_stock_control':key,'progress':okay}}
        require(t.step(label+'.'+str(i),'Turn the stock character model toward the observed target view.',
            {'rotate':{'kind':'click','value':point(buttons[0]),'hold':hold,'description':'Hold the visible stock model rotation button.'}},
            outcome,diagnostic_action='rotate'),'stock_camera_rotation_pass')
    if abs(angle(target-current))>.2:raise RuntimeError('stock character rotation did not reach the target view')
    return current


def render(t,kind,shown):
    label='appearance.render.'+kind+('.shown' if shown else '.hidden')
    state,_=t.observe(label+'_before_close')
    if 'SettingsPanel' in state['panels']:
        require(click_case(t,label+'.close_settings','Close stock settings before inspecting the character.',
            lambda c:c['text']=='Close',lambda b,a,s:{'status':'panel_closed_pass' if s and
                'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
    open_character(t,label);original=yaw(t,label+'_front')
    try:
        if kind=='cloak':rotate(t,original+math.pi,label+'.back')
        state,frame=t.observe(label.replace('.','_'))
        if state['appearance'][kind]!=shown or not state['equipment'][0] or not state['equipment'][14]:
            raise RuntimeError('stock rendered visibility or equipped fixture differs')
        if state.get('lua_errors') or state.get('blocked_actions'):raise RuntimeError('stock character rendering has UI errors')
        t.receipt.setdefault('appearance_renders',[]).append({'kind':kind,'shown':shown,
            'yaw':yaw(t,label+'_final'),'state':state,'frame':frame,'manual_render_review_required':True});t.persist()
    finally:
        if kind=='cloak':rotate(t,original,label+'.restore_camera')
        t.clean_panels()
