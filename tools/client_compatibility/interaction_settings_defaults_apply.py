"""Apply stock Current Settings defaults to one guarded Colorblind Mode fixture."""
import argparse,json,math,re,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,click_control,restore_layout
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search,toggle
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite

VARIABLES={'colorblindMode','colorblindSimulator','colorblindWeaknessFactor'}


def numeric(value):
    if isinstance(value,bool):raise RuntimeError('colorblind numeric value must not be boolean')
    try:value=float(value)
    except (TypeError,ValueError):raise RuntimeError('missing colorblind numeric value') from None
    if not math.isfinite(value):raise RuntimeError('non-finite colorblind numeric value')
    return value


def fixture(probe):
    cvars=probe.get('cvars',{});values=probe.get('values',{})
    if (cvars.get('colorblindMode')!='0' or values.get('colorblindMode') is not False or
            numeric(cvars.get('colorblindSimulator'))!=0 or numeric(values.get('colorblindSimulator'))!=0 or
            not 0<=numeric(cvars.get('colorblindWeaknessFactor'))<=1 or
            numeric(cvars.get('colorblindWeaknessFactor'))!=numeric(values.get('colorblindWeaknessFactor')) or
            probe.get('unapplied') is not False or probe.get('discard_dialogs') or probe.get('defaults_dialogs')):
        raise RuntimeError('requires a clean disabled Colorblind Mode and filter fixture')


def catalog(probe,original,enabled):
    rows=probe.get('colorblind_defaults')
    if not isinstance(rows,list) or len(rows)!=3 or {r.get('variable') for r in rows}!=VARIABLES:
        raise RuntimeError('requires exactly the three source-backed current-category settings')
    values={r['variable']:r for r in rows}
    mode=values['colorblindMode'];sim=values['colorblindSimulator'];strength=values['colorblindWeaknessFactor']
    if (mode.get('value') is not enabled or mode.get('default') is not False or
            type(sim.get('value')) not in (int,float) or type(sim.get('default')) not in (int,float) or
            sim['value']!=0 or sim['default']!=0 or
            type(strength.get('value')) not in (int,float) or type(strength.get('default')) not in (int,float) or
            numeric(strength['value'])!=numeric(original['values']['colorblindWeaknessFactor']) or
            numeric(strength['default'])!=numeric(strength['value'])):
        raise RuntimeError('current-category defaults would change an unowned fixture value')
    return values


def checks(probe,original,enabled):
    cvars=dict(original['cvars']);values=dict(original['values'])
    cvars['colorblindMode']='1' if enabled else '0';values['colorblindMode']=enabled
    return {'cvars':probe.get('cvars')==cvars,'values':probe.get('values')==values,
        'active_display':probe.get('display_state')==original.get('display_state'),
        'no_pending':probe.get('unapplied') is False and not probe.get('discard_dialogs')}


def popup(probe):
    rows=probe.get('defaults_dialogs') or []
    if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('which')!='GAME_SETTINGS_APPLY_DEFAULTS' or
            not re.fullmatch(r'StaticPopup[1-3]',rows[0].get('name',''))):
        raise RuntimeError('requires one exact stock Defaults confirmation')
    return rows[0]['name']


def choose(t,index,label):
    if type(index) is not int or index not in (2,3):raise ValueError('only Cancel or Current Settings is permitted')
    before=detail(t,label+'_before');name=popup(before)
    if not all(checks(before,t.defaults_layout,True).values()):
        raise RuntimeError('Defaults choice requires the exact enabled fixture')
    catalog(before,t.defaults_layout,True)
    if before.get('category')!=t.defaults_category or before.get('search')!='':
        raise RuntimeError('Defaults choice category or search changed')
    control=target(t,label+'_button',lambda c:c['kind']=='Button' and c['name']==name+'Button'+str(index)
        and c['enabled'])
    if index==3:t.receipt['defaults_apply_attempted']=True;t.persist()
    wanted=index==2
    def outcome(b,a,s):
        current=detail(t,label+'_result',lambda p:not p.get('defaults_dialogs') and
            p['values'].get('colorblindMode') is wanted)
        catalog(current,t.defaults_layout,wanted)
        result=checks(current,t.defaults_layout,wanted)
        result.update(ordinary_choice=s=='click',dialog_closed=not current.get('defaults_dialogs'),
            category=current.get('category')==t.defaults_category,search=current.get('search')=='',
            settings_visible=current.get('visible') is True,
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'stock_current_category_defaults_pass' if all(result.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':result,'button_index':index,'public':current}}
    require(t.step(label,'Use the observed stock '+('Current Settings' if index==3 else 'Cancel')+' choice.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_current_category_defaults_pass')


def cleanup(t,layout):
    current=detail(t,'defaults_cleanup_before')
    if current.get('defaults_dialogs'):
        if t.receipt.get('defaults_cancel_attempted'):raise RuntimeError('failed Defaults Cancel is not replayed')
        t.receipt['defaults_cancel_attempted']=True;t.persist();choose(t,2,'fixture.defaults.cancel')
        current=detail(t,'defaults_cleanup_cancelled')
    enabled=current['values'].get('colorblindMode')
    if type(enabled) is not bool or not all(checks(current,layout,enabled).values()):
        raise RuntimeError('Defaults cleanup requires all other observed fixture values unchanged')
    if enabled:toggle(t,'colorblindMode','0','fixture.defaults.restore_mode')
    current=detail(t,'defaults_cleanup_values');result=checks(current,layout,False)
    result['no_defaults_dialog']=not current.get('defaults_dialogs')
    t.receipt['defaults_value_restoration']={'checks':result};t.persist()
    if not all(result.values()):raise RuntimeError('original Colorblind Mode values did not restore')
    restore_layout(t,layout,'fixture.defaults.layout')
    t.receipt['defaults_layout_restoration']=t.receipt.pop('volume_layout_restoration');t.persist()


def suite(t):
    state,_=t.observe('defaults_observer_guard')
    if state.get('observer_version',0)<120:raise RuntimeError('requires read-only Defaults observer120')
    t.receipt.update(custom_script_permission='blocked_by_user',qualified_scope=
        'Owned primary: enable stock UI Colorblind Mode, then select exact Defaults Current Settings to apply the source-backed false default immediately. Filter and weakness values already equal their defaults; all other observed settings/CVars and active display stay unchanged. Original layout and native fixture restore. All Settings, other categories, pending graphics defaults and persistence remain open.');t.persist()
    t.settings_search=open_search(t);layout=detail(t,'defaults_layout_baseline');fixture(layout)
    t.defaults_layout=layout;t.receipt['defaults_layout_baseline']=layout;t.persist()
    try:
        if layout.get('search'):search(t,'','fixture.defaults.clear_search')
        control=target(t,'defaults_colorblind_category',lambda c:c['text']=='Colorblind Mode')
        click_control(t,'fixture.defaults.category',control,lambda a:
            bool(detail(t,'defaults_category_selected').get('colorblind_defaults')),'defaults_category_selected')
        category=detail(t,'defaults_category_fixture');fixture(category);catalog(category,layout,False)
        if not all(checks(category,layout,False).values()) or category.get('search')!='':
            raise RuntimeError('Colorblind category differs from the saved settings fixture')
        t.defaults_category=category['category'];t.receipt['defaults_category']=t.defaults_category;t.persist()
        toggle(t,'colorblindMode','1','fixture.defaults.enable_mode')
        current=detail(t,'defaults_enabled_fixture');catalog(current,layout,True)
        if not all(checks(current,layout,True).values()):raise RuntimeError('enabled Colorblind fixture differs')
        control=target(t,'defaults_header_button',lambda c:c['kind']=='Button' and c['enabled'] and
            c.get('settings_defaults_button') is True)
        def opened(a):
            probe=detail(t,'defaults_dialog_open',lambda p:bool(p.get('defaults_dialogs')))
            return popup(probe) in a['panels'] and all(checks(probe,layout,True).values())
        click_control(t,'settings.defaults_apply.open',control,opened,'stock_defaults_dialog_pass')
        choose(t,3,'settings.defaults_apply.current_colorblind')
    finally:cleanup(t,layout)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
