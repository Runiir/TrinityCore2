"""Roundtrip the stock AddOns version-check checkbox through ordinary inputs."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_addons_settings import (AddonsTrial,COMPAT,HARNESS,valid_row,cadence_ready,
    detail,settings,open_panel,cancel,control_layout)
from .interaction_operations import controls,point
from .interaction_control_target import target
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


def version_checks(current,original,wanted):
    return {'panel_visible':current.get('visible') is True,
        'version_check_exact':type(current.get('version_check')) is bool and current['version_check'] is wanted,
        'addon_rows_preserved':current.get('rows')==original.get('rows'),
        'other_public_state_preserved':all(current.get(k)==v for k,v in original.items() if k!='version_check')}


def checkbox(t,label,checked=None):
    return target(t,label,lambda c:c.get('name')=='AddonListForceLoad' and
        c['kind']=='CheckButton' and c['enabled'] is True and
        (checked is None or c.get('checked') is checked))


def select(t,original,wanted,label):
    # ForceLoad is the inverse of the public "version check enabled" flag.
    button=checkbox(t,label+'_target',wanted)
    state,frame=t.observe(label+'_cadence_guard')
    t.receipt.setdefault('addons_click_cadence_guards',[]).append({'label':label,'frame':frame,
        'framerate':state.get('framerate'),'hold':.2,'input_replayed':False});t.persist()
    if not cadence_ready(state):raise RuntimeError('200ms AddOns click requires a freshly observed rate of at least10FPS')
    def outcome(b,a,s):
        after=detail(t,label+'_public');rendered=checkbox(t,label+'_checked',not wanted)
        checks=version_checks(after,original,wanted)
        checks.update(ordinary_checkbox=s=='click',rendered_inverse=rendered['checked'] is (not wanted),
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        state,frame=t.observe(label+'_rendered')
        return {'status':'addons_version_check_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'checkbox':rendered,'state':state,'frame':frame}}
    require(t.step(label,'Change the observed Load out of date AddOns checkbox through ordinary mouse input.',
        {'click':{'kind':'click','value':point(button),'hold':.2}},outcome,diagnostic_action='click'),
        'addons_version_check_pass')


def suite(t):
    original=None;layout=None;baseline_controls=None
    t.receipt.update(qualified_scope='Stock Load out of date AddOns checkbox on/off roundtrip only. '
        'The public version-check flag and inverse rendered checkbox must agree. All addon enable rows, '
        'original AddOns checkbox layout, settings and native fixture must restore. No reload or effective '
        'out-of-date addon loading is exercised.',custom_script_permission='blocked_by_user');t.persist()
    try:
        layout=settings(t,'version_check_original_settings')
        if layout.get('visible') or layout.get('unapplied'):raise RuntimeError('requires clean closed original settings')
        open_panel(t,'settings.addons.version_check');original=detail(t,'version_check_baseline')
        t.receipt['addons_baseline']=original;baseline_controls=control_layout(controls(t))
        t.receipt['addons_control_baseline']=baseline_controls;t.persist()
        if (type(original.get('version_check')) is not bool or original.get('visible') is not True or
            set(original.get('rows',{}))!={COMPAT,HARNESS} or not all(valid_row(original['rows'][n],n) and
                original['rows'][n]['enable_all']==original['rows'][n]['enable_character']==2 for n in (COMPAT,HARNESS))):
            raise RuntimeError('requires both owned addons loaded, all-character enabled, and a boolean version-check flag')
        checkbox(t,'version_check_original_checkbox',not original['version_check'])
        t.receipt['version_check_selection_attempted']=True;t.persist()
        select(t,original,not original['version_check'],'settings.addons.pending_version_check_change')
        select(t,original,original['version_check'],'settings.addons.pending_version_check_restore')
        after=detail(t,'version_check_restored');rendered=control_layout(controls(t))
        state,frame=t.observe('version_check_restored_rendered')
        checks={'public':after==original,'rendered':rendered==baseline_controls,
            'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
        t.receipt['addons_version_check_restoration']={'checks':checks,'state':state,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('original AddOns version-check layout differs after roundtrip')
    except Exception as error:t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        state,_=t.observe('version_check_cleanup_guard')
        if 'AddonList' in state.get('panels',[]):
            if original is not None and t.receipt.get('version_check_selection_attempted'):
                current=checkbox(t,'version_check_cleanup_checkbox')
                if type(current.get('checked')) is not bool:raise RuntimeError('original AddOns version checkbox is unreadable')
                if current['checked'] is original['version_check']:
                    select(t,original,original['version_check'],'fixture.restore_addons_selection_version_check')
            cancel(t,'fixture.close_addons_version_check')
        if original is not None:
            after=detail(t,'version_check_final_closed',closed=True)
            t.receipt['addons_final_public_restored']=after=={**original,'visible':False};t.persist()
            if not t.receipt['addons_final_public_restored']:raise RuntimeError('final AddOns public state differs')
        if layout is not None:
            after=settings(t,'version_check_settings_restored');checks={k:after.get(k)==layout.get(k) for k in layout}
            t.receipt['addons_settings_restoration']={'checks':checks};t.persist()
            if not all(checks.values()):raise RuntimeError('AddOns version-check trial changed saved settings')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=AddonsTrial(a.output,controller='code')
        try:
            state,_=t.observe('version_check_observer_guard')
            if state.get('observer_version',0)<114:raise RuntimeError('requires read-only AddOns observer114')
            native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
