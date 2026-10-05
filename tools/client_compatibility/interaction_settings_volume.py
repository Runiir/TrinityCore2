"""Inspect and roundtrip stock Master Volume through ordinary stepper clicks."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_profession_recipes import RecipeTrial
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


class SettingsTrial(RecipeTrial):
    def step(self,case_id,goal,actions,oracle,**kwargs):
        actions={k:{**v,'hold':max(v.get('hold',0),1.2)} if v['kind']=='key' and v['value'] in ('Escape','Return') else v
            for k,v in actions.items()}
        return super().step(case_id,goal,actions,oracle,**kwargs)


def click_control(t,label,control,ready,status):
    t.io.move(*point(control));time.sleep(1)
    require(t.step(label,'Use the observed stock settings control.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},
        lambda b,a,s:{'status':status if s=='click' and ready(a) and not a.get('lua_errors') and
            not a.get('blocked_actions') else 'client_or_protocol_failure'},diagnostic_action='click',await_state=ready),status)


def value(probe):
    actual=float(probe['cvars']['Sound_MasterVolume']);setting=float(probe['values']['Sound_MasterVolume'])
    if not math.isfinite(actual) or not math.isfinite(setting) or not 0<=actual<=1 or abs(actual-setting)>1e-6:
        raise RuntimeError('public Master Volume setting and CVar disagree')
    return actual


def step_volume(t,layout,direction,label):
    if direction not in (-1,1):raise ValueError('Master Volume step direction must be -1 or 1')
    before=detail(t,label+'_before');original=value(layout);previous=value(before)
    slider=target(t,label+'_slider',lambda c:c['kind']=='Slider' and c.get('setting_variable')=='Sound_MasterVolume')
    button=target(t,label+'_stepper',lambda c:c['kind']=='Button' and c.get('enabled') and
        c.get('setting_variable')=='Sound_MasterVolume' and c['y']==slider['y'] and
        (c['x']<slider['x'] if direction<0 else c['x']>slider['x']))
    t.io.move(*point(button));time.sleep(1)
    def outcome(b,a,s):
        after=detail(t,label+'_value',lambda p:value(p)<previous if direction<0 else value(p)>previous)
        current=value(after);shown=target(t,label+'_display',lambda c:c['kind']=='Slider' and
            c.get('setting_variable')=='Sound_MasterVolume')
        checks={'ordinary_stepper':s=='click','same_variable':button['setting_variable']=='Sound_MasterVolume',
            'direction':current<previous if direction<0 else previous<current<=original,
            'rendered_percent':shown['context']==str(round(current*100))+'%',
            'control_setting':abs(float(shown['setting_value'])-current)<1e-6,
            'other_cvars_preserved':all(after['cvars'].get(k)==v for k,v in layout['cvars'].items() if k!='Sound_MasterVolume'),
            'other_settings_preserved':all(after['values'].get(k)==v for k,v in layout['values'].items() if k!='Sound_MasterVolume'),
            'no_pending_changes':after.get('unapplied')==layout.get('unapplied'),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_numeric_setting_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'before':previous,'after':current,'original':original,
                'slider':shown,'stepper':button,'public':after}}
    require(t.step(label,'Use the observed stock Master Volume '+('decrement' if direction<0 else 'increment')+' arrow.',
        {'click':{'kind':'click','value':point(button),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_numeric_setting_pass')


def restore_volume(t,layout,prefix):
    for attempt in range(4):
        current=value(detail(t,prefix+'_guard_'+str(attempt)))
        if abs(current-value(layout))<1e-6:return
        if not current<value(layout):raise RuntimeError('Master Volume exceeds the original maximum')
        step_volume(t,layout,1,prefix+'.'+str(attempt+1))
    if abs(value(detail(t,prefix+'_final'))-value(layout))>=1e-6:
        raise RuntimeError('bounded Master Volume restoration did not reach the original maximum')


def inspect(t,exercise=False):
    layout=None
    try:
        t.settings_search=open_search(t);layout=detail(t,'volume_layout_baseline')
        t.receipt['volume_layout_baseline']=layout;t.persist()
        if layout.get('unapplied'):raise RuntimeError('original settings contain unapplied changes')
        search(t,'Master Volume','fixture.find_master_volume')
        current=detail(t,'master_volume_rendered');rows=controls(t);state,frame=t.observe('master_volume_recon')
        t.receipt['volume_recon']={'settings':current,'controls':rows,'state':state,'frame':frame,
            'qualified':False,'scope':'Control reconnaissance before any requested volume exercise.'};t.persist()
        matches=[c for c in rows if c.get('setting_variable')=='Sound_MasterVolume']
        if not matches:raise RuntimeError('stock Master Volume setting controls are absent')
        if exercise:
            if value(layout)!=1 or value(current)!=1:raise RuntimeError('requires the observed original 100-percent Master Volume fixture')
            t.receipt.update(volume_exercise_attempted=True,qualified_scope=
                'One held stock decrement arrow, then bounded stock increment arrows back to the original 100-percent Master Volume. Public CVar, Settings value and rendered percentage agree; other observed settings, search/category and native fixture restore. Slider dragging, other ranges, keybindings and reconnect persistence remain open.');t.persist()
            step_volume(t,layout,-1,'settings.sound_volume.decrease')
            restore_volume(t,layout,'settings.sound_volume.restore')
    finally:
        if layout is not None:
            if t.receipt.get('volume_exercise_attempted'):restore_volume(t,layout,'fixture.restore_master_volume')
            search(t,layout.get('search') or '','fixture.restore_volume_search')
            current=detail(t,'volume_layout_restore_before')
            if current.get('category')!=layout.get('category'):
                name=layout['category']['name']
                control=target(t,'fixture.restore_volume_category',lambda c:c['text']==name or c['text'].startswith(name+'|T'))
                click_control(t,'fixture.restore_volume_category',control,lambda a:
                    detail(t,'volume_category_restored')['category']==layout['category'],'settings_category_restored')
            current=detail(t,'volume_layout_restored')
            checks={k:current.get(k)==layout.get(k) for k in ('search','category','cvars','values','unapplied')}
            t.receipt['volume_layout_restoration']={'checks':checks};t.persist()
            if not all(checks.values()):raise RuntimeError('original volume settings layout differs')
            close=target(t,'fixture.close_volume_recon',lambda c:c['kind']=='Button' and c['text']=='Close')
            click_control(t,'fixture.close_volume_recon',close,lambda a:'SettingsPanel' not in a['panels'],
                'settings_panel_closed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exercise',action='store_true');a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=lambda t:inspect(t,a.exercise),preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
