"""Apply one lower stock render-scale step and restore the original allocation."""
import argparse,copy,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite

VARIABLE='PROXY_RESOLUTION_RENDER_SCALE'


def scale(probe):
    try:actual=float(probe['cvars']['RenderScale']);pending=probe['values'][VARIABLE]
    except (KeyError,TypeError,ValueError) as error:
        raise RuntimeError('installed render-scale CVar and setting are required') from error
    if (type(pending) not in (int,float) or not math.isfinite(actual) or
            not math.isfinite(pending) or not 0<actual<=1 or not 0<pending<=1):
        raise RuntimeError('render-scale values must be finite and no greater than 100 percent')
    return actual,pending


def value_checks(current,baseline,actual,pending,unapplied):
    applied,requested=scale(current)
    return {'actual_render_scale':abs(applied-actual)<1e-6,
        'pending_render_scale':abs(requested-pending)<1e-6,
        'unapplied_state':current.get('unapplied') is unapplied,
        'other_cvars':{k:v for k,v in current['cvars'].items() if k!='RenderScale'}==
            {k:v for k,v in baseline['cvars'].items() if k!='RenderScale'},
        'other_settings':{k:v for k,v in current['values'].items() if k!=VARIABLE}==
            {k:v for k,v in baseline['values'].items() if k!=VARIABLE}}


def pending_step(t,direction,label,*,expected=None):
    before=detail(t,label+'_before');actual,previous=scale(before)
    slider=target(t,label+'_slider',lambda c:c['kind']=='Slider' and c.get('setting_variable')==VARIABLE)
    button=target(t,label+'_stepper',lambda c:c['kind']=='Button' and c.get('setting_variable')==VARIABLE
        and c['y']==slider['y'] and (c['x']-slider['x'])*direction>0)
    if not button.get('enabled'):raise RuntimeError('requested render-scale stepper is disabled')
    def outcome(b,a,s):
        current=detail(t,label+'_pending',lambda p:
            (scale(p)[1]-previous)*direction>1e-6)
        _,requested=scale(current)
        checks=value_checks(current,t.render_layout,actual,requested,True)
        checks.update(ordinary_stepper=s=='click',bounded_step=0<(requested-previous)*direction<=.1,
            expected_value=expected is None or abs(requested-expected)<1e-6,
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'stock_render_scale_pending_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'actual_before':actual,'pending_before':previous,'pending_after':requested}}
    require(t.step(label,'Change one pending render-scale step through its observed stock arrow.',
        {'click':{'kind':'click','value':point(button),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_render_scale_pending_pass')
    return t.receipt['cases'][-1]['oracle']['pending_after']


def apply(t,expected,label):
    before=detail(t,label+'_before');_,pending=scale(before)
    if before.get('unapplied') is not True or abs(pending-expected)>=1e-6:
        raise RuntimeError('Apply requires the exact observed pending scale')
    control=target(t,label+'_button',lambda c:c['kind']=='Button' and c['text']=='Apply' and c['enabled'])
    def outcome(b,a,s):
        current=detail(t,label+'_applied',lambda p:abs(scale(p)[0]-expected)<1e-6 and
            p.get('unapplied') is False)
        checks=value_checks(current,t.render_layout,expected,expected,False)
        checks.update(ordinary_apply=s=='click',ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'stock_render_scale_apply_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'expected_scale':expected,'public':current}}
    require(t.step(label,'Apply the exact observed render scale through the stock Apply button.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_render_scale_apply_pass')


def suite(t):
    state,_=t.observe('render_scale_fixture')
    if state.get('observer_version',0)<115:raise RuntimeError('requires read-only settings observer115')
    t.receipt.update(custom_script_permission='blocked_by_user',
        qualified_scope='Owned primary: one lower render-scale arrow step, ordinary Apply, inverse arrow step and Apply restoring the original scale. Pending proxy value, actual public CVar, other settings/CVars and full native fixture must agree. No higher allocation, resolution, window/monitor, quality preset or persistence qualification.')
    t.persist();t.settings_search=open_search(t);layout=detail(t,'render_layout_baseline');t.render_layout=layout
    original,pending=scale(layout)
    if layout.get('unapplied') is not False or abs(original-pending)>=1e-6 or not .5<original<=1:
        raise RuntimeError('requires an applied reversible scale between 50 and 100 percent')
    t.receipt['render_layout_baseline']=layout;t.persist()
    try:
        search(t,'Render Scale','settings.render_scale.search')
        lower=pending_step(t,-1,'settings.render_scale.lower_pending')
        apply(t,lower,'settings.apply.render_scale_lower')
        pending_step(t,1,'settings.render_scale.original_pending',expected=original)
        apply(t,original,'settings.apply.render_scale_original')
    finally:
        restore(t,layout)


def restore(t,layout):
    original,_=scale(layout)
    current=detail(t,'render_cleanup_before');_,requested=scale(current)
    if abs(requested-original)>=1e-6:
        search(t,'Render Scale','fixture.render_scale.cleanup_search')
        pending_step(t,1,'fixture.render_scale.cleanup_pending',expected=original)
        current=detail(t,'render_cleanup_pending')
    if current.get('unapplied') is True:apply(t,original,'fixture.render_scale.cleanup_apply')
    current=detail(t,'render_restored');checks=value_checks(current,layout,original,original,False)
    t.receipt['render_restoration']={'checks':checks};t.persist()
    if not all(checks.values()):raise RuntimeError('original render scale and graphics fixture did not restore')
    # Only proven-equal numeric serialization is normalized for the existing
    # layout restorer; raw probes and restoration checks remain untouched.
    normalized=copy.deepcopy(layout);normalized['cvars']['RenderScale']=current['cvars']['RenderScale']
    restore_layout(t,normalized,'fixture.render_scale.layout')
    t.receipt['render_layout_restoration']=t.receipt.pop('volume_layout_restoration');t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':main()
