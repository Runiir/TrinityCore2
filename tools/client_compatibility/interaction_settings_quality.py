"""Select one lower pending stock graphics preset and discard it before Apply."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_settings_discard import dialog
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite

VARIABLE='PROXY_GRAPHICS_QUALITY'
CHILDREN={
    'graphicsShadowQuality':'PROXY_SHADOW_QUALITY','graphicsLiquidDetail':'PROXY_LIQUID_DETAIL',
    'graphicsParticleDensity':'PROXY_PARTICLE_DENSITY','graphicsSSAO':'PROXY_SSAO',
    'graphicsTextureResolution':'PROXY_TEXTURE_RESOLUTION','graphicsSpellDensity':'PROXY_SPELL_DENSITY',
    'graphicsProjectedTextures':'PROXY_PROJECTED_TEXTURES','graphicsEnvironmentDetail':'PROXY_ENVIRONMENT_DETAIL',
    'graphicsGroundClutter':'PROXY_GROUND_CLUTTER','graphicsSunshafts':'PROXY_SUNSHAFTS'}
PROXIES={VARIABLE,*CHILDREN.values()}


def numeric(value):return type(value) in (int,float) and math.isfinite(value)


def fixture(layout):
    values=layout['values'];original=values.get(VARIABLE);preset=layout.get('lower_graphics_values') or {}
    if (not numeric(original) or not 0<original<=9 or int(original)!=original or
            layout.get('unapplied') is not False or layout.get('discard_dialogs') or
            layout.get('lower_graphics_quality')!=original-1 or set(preset)!=set(CHILDREN.values()) or
            not all(numeric(v) for v in preset.values()) or preset.get('PROXY_PARTICLE_DENSITY',0)<1):
        raise RuntimeError('requires an applied stock quality fixture and complete read-only lower-preset map')
    for cvar,proxy in {'graphicsQuality':VARIABLE,**CHILDREN}.items():
        try:actual=float(layout['cvars'][cvar])
        except (KeyError,TypeError,ValueError) as error:raise RuntimeError('quality CVar is unavailable') from error
        if not numeric(values.get(proxy)) or not math.isfinite(actual) or abs(actual-values[proxy])>=1e-6:
            raise RuntimeError('applied stock quality values and CVars disagree')
    return original


def checks(current,baseline,pending):
    expected={k:baseline['values'][k] for k in PROXIES}
    if pending:expected.update(baseline['lower_graphics_values']);expected[VARIABLE]=baseline['lower_graphics_quality']
    return {'native_cvars_unchanged':current.get('cvars')==baseline['cvars'],
        'quality_and_children':all(numeric(current.get('values',{}).get(k)) and
            abs(current['values'][k]-v)<1e-6 for k,v in expected.items()),
        'other_settings':{k:v for k,v in current.get('values',{}).items() if k not in PROXIES}==
            {k:v for k,v in baseline['values'].items() if k not in PROXIES},
        'unapplied_state':current.get('unapplied') is pending}


def exit_dialog(t,label,layout):
    close=target(t,label+'_close',lambda c:c['kind']=='Button' and c['text']=='Close' and c['enabled'])
    def outcome(b,a,s):
        probe=detail(t,label+'_dialog',lambda p:bool(p.get('discard_dialogs')));name=dialog(probe)
        result=checks(probe,layout,True);result.update(ordinary_close=s=='click',popup_visible=name in a['panels'])
        return {'status':'pending_quality_exit_dialog_pass' if all(result.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':result,'popup_name':name}}
    require(t.step(label,'Close stock Settings with the exact pending lower quality preset.',
        {'click':{'kind':'click','value':point(close),'hold':1.2}},outcome,diagnostic_action='click'),
        'pending_quality_exit_dialog_pass')


def discard(t,layout,label):
    before=detail(t,label+'_before');name=dialog(before)
    if not all(checks(before,layout,True).values()):raise RuntimeError('discard requires the exact pending preset')
    control=target(t,label+'_exit',lambda c:c['kind']=='Button' and c['name']==name+'Button1' and c['enabled'])
    if t.receipt.get('quality_discard_attempted'):raise RuntimeError('failed quality discard is never replayed')
    t.receipt['quality_discard_attempted']=True;t.persist()
    require(t.step(label,'Discard the pending stock preset with the observed Exit choice; never Apply.',
        {'exit':{'kind':'click','value':point(control),'hold':1.2}},lambda b,a,s:
        {'status':'pending_quality_discard_closed' if s=='exit' and 'SettingsPanel' not in a['panels'] and
            name not in a['panels'] and not a.get('lua_errors') and not a.get('blocked_actions')
            else 'client_or_protocol_failure'},diagnostic_action='exit',
        await_state=lambda a:'SettingsPanel' not in a['panels'] and name not in a['panels']),
        'pending_quality_discard_closed')
    # Reopen before reading settings. Sparse hidden pages are not a cleanup oracle.
    t.clean_panels();t.settings_search=open_search(t)
    restored=detail(t,label+'_restored');result=checks(restored,layout,False)
    result['dialog_closed']=not restored.get('discard_dialogs')
    t.receipt['quality_restoration']={'checks':result,'public':restored};t.persist()
    if not all(result.values()):raise RuntimeError('discard did not restore the exact stock quality fixture')


def suite(t):
    state,_=t.observe('quality_fixture')
    if state.get('observer_version',0)<118:raise RuntimeError('requires stock quality identity observer118')
    t.receipt.update(custom_script_permission='blocked_by_user',qualified_scope=
        'Owned primary: stock base Graphics Quality decrement selects one lower pending preset. All ten child proxies match the installed read-only quality-level map while all observed native CVars stay fixed. Ordinary Close and Discard and Exit restore every proxy without Apply; original Settings layout and native fixture restore. Applied quality changes, other presets, performance and restart persistence remain open.')
    t.persist();t.settings_search=open_search(t);layout=detail(t,'quality_layout_baseline');original=fixture(layout)
    t.receipt['quality_layout_baseline']=layout;t.persist()
    try:
        search(t,'Graphics','settings.quality.search')
        control=target(t,'settings.quality.decrement_target',lambda c:c['kind']=='Button' and c['enabled'] and
            c.get('setting_variable')==VARIABLE and c.get('graphics_role')=='base' and c.get('setting_control')=='Back')
        def outcome(b,a,s):
            probe=detail(t,'quality_pending',lambda p:p['values'].get(VARIABLE)==original-1 and p.get('unapplied') is True)
            result=checks(probe,layout,True)
            slider=target(t,'quality_pending_slider',lambda c:c['kind']=='Slider' and
                c.get('setting_variable')==VARIABLE and c.get('graphics_role')=='base')
            result.update(ordinary_stepper=s=='click',rendered_level=slider.get('context')==str(int(original)),
                control_value=slider.get('setting_value')==original-1,
                ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
            return {'status':'stock_pending_quality_preset_pass' if all(result.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':result,'original':original,'pending':original-1,'slider':slider,'public':probe}}
        require(t.step('settings.quality.lower_pending','Use the observed base-quality decrement arrow.',
            {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
            'stock_pending_quality_preset_pass')
        exit_dialog(t,'settings.quality.exit_dialog',layout);discard(t,layout,'settings.quality.discard')
    finally:
        state,_=t.observe('quality_cleanup_visibility')
        if 'SettingsPanel' not in state['panels']:t.clean_panels();t.settings_search=open_search(t)
        current=detail(t,'quality_cleanup_before')
        if current.get('unapplied'):
            if not current.get('discard_dialogs'):exit_dialog(t,'fixture.quality.cleanup_dialog',layout)
            discard(t,layout,'fixture.quality.cleanup_discard')
        if not all(checks(detail(t,'quality_cleanup_values'),layout,False).values()):
            raise RuntimeError('original quality fixture differs during cleanup')
        restore_layout(t,layout,'fixture.quality.layout')
        t.receipt['quality_layout_restoration']=t.receipt.pop('volume_layout_restoration');t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':main()
