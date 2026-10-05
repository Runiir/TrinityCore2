"""Select the owned compatibility addon off, cancel, and verify its restoration."""
import argparse,json,time,re
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_operations import controls,point,command
from .interaction_control_target import target
from .interaction_observation import read_current_page,read_page
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite

COMPAT='Client442Compatibility'
HARNESS='ClientMovementHarness'


def valid_row(row,name):
    return (row.get('name')==name and isinstance(row.get('title'),str) and bool(row['title']) and
        row.get('loaded') is True and row.get('loaded_or_loading') is True and
        isinstance(row.get('version'),str) and bool(row['version']) and
        all(type(row.get(k)) is int and row[k] in (0,1,2) for k in ('enable_all','enable_character')))


def pending_checks(current,original):
    rows=current.get('rows',{});base=original.get('rows',{})
    compat=rows.get(COMPAT,{});saved=base.get(COMPAT,{})
    return {'panel_visible':current.get('visible') is True,
        'only_owned_addons':set(rows)==set(base)=={COMPAT,HARNESS},
        'public_enable_states_typed':valid_row(compat,COMPAT),
        'compat_still_loaded':compat.get('loaded') is True,
        'harness_preserved':rows.get(HARNESS)==base.get(HARNESS),
        'compat_identity_preserved':all(compat.get(k)==v for k,v in saved.items()
            if k not in ('enable_all','enable_character')),
        'other_public_state_preserved':all(current.get(k)==v for k,v in original.items() if k!='rows')}


def detail(t,label,*,closed=False):
    try:
        state,frame=read_page(t,label,'addons','/tcui addons') if closed else read_current_page(t,label,'addons')
        t.receipt.setdefault('addons_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['addons_probe']
    finally:
        if closed:command(t,'/tcui state')


def settings(t,label):
    try:
        state,frame=read_page(t,label,'settings','/tcui settings')
        t.receipt.setdefault('settings_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['settings_probe']
    finally:command(t,'/tcui state')


def open_panel(t,label):
    require(t.step(label+'.menu','Open the stock game menu.',
        {'open':{'kind':'key','value':'Escape','hold':1.2}},
        lambda b,a,s:{'status':'menu_open_pass' if s=='open' and 'GameMenuFrame' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='open',await_state=lambda a:'GameMenuFrame' in a['panels']),
        'menu_open_pass')
    button=target(t,label+'.open_target',lambda c:c['kind']=='Button' and c['text']=='AddOns' and c['enabled'])
    require(t.step(label+'.open','Open the stock AddOns list.',
        {'open':{'kind':'click','value':point(button),'hold':1.2}},
        lambda b,a,s:{'status':'addons_panel_open' if s=='open' and 'AddonList' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='open',await_state=lambda a:'AddonList' in a['panels']),
        'addons_panel_open')


def checkbox(t,label,caption,checked=None):
    return target(t,label,lambda c:c['kind']=='CheckButton' and c['enabled'] and
        c['name'].startswith('AddonListEntry') and c['name'].endswith('Enabled') and
        c['context']==caption and (checked is None or c.get('checked') is checked))


def row_matches(row,check,caption):
    name=check.get('name','')
    if not re.fullmatch(r'AddonListEntry\d+Enabled',name):return False
    return (row.get('name')==name.removesuffix('Enabled') and row.get('kind')=='Button' and
        row.get('text')==caption and row.get('enabled') is True and row.get('addon_onclick') is True)


def select(t,original,wanted,label):
    caption=original['rows'][COMPAT]['title'];check=checkbox(t,label+'_target',caption,not wanted)
    button=target(t,label+'_row_target',lambda c:row_matches(c,check,caption))
    t.io.move(*point(button));time.sleep(1)
    def outcome(b,a,s):
        rendered=checkbox(t,label+'_checked',caption,wanted);after=detail(t,label+'_public')
        checks=pending_checks(after,original)
        checks.update(ordinary_row=s=='click' and row_matches(button,check,caption),rendered_selection=rendered['checked'] is wanted,
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        state,frame=t.observe(label+'_rendered')
        return {'status':'addons_pending_selection_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'checkbox':rendered,'row':button,'state':state,'frame':frame,
                'public_enable_changed':{k:after.get('rows',{}).get(COMPAT,{}).get(k)!=original['rows'][COMPAT][k]
                    for k in ('enable_all','enable_character')}}}
    require(t.step(label,'Change only the observed compatibility-addon selection through its stock row button.',
        {'click':{'kind':'click','value':point(button),'hold':1.2}},outcome,diagnostic_action='click'),
        'addons_pending_selection_pass')


def cancel(t,label):
    button=target(t,label+'_target',lambda c:c['kind']=='Button' and c['name']=='AddonListCancelButton' and c['enabled'])
    require(t.step(label,'Cancel pending changes through the observed stock AddOns Cancel button.',
        {'cancel':{'kind':'click','value':point(button),'hold':1.2}},
        lambda b,a,s:{'status':'addons_cancelled' if s=='cancel' and 'AddonList' not in a['panels'] and
            not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'},
        diagnostic_action='cancel',await_state=lambda a:'AddonList' not in a['panels']),'addons_cancelled')
    t.clean_panels()


def control_layout(rows):
    return {c['name']:{k:c.get(k) for k in ('checked','enabled','context','text','x','y')} for c in rows
        if c['kind']=='CheckButton' and c['name'].startswith('AddonList')}


def suite(t):
    original=None;layout=None;baseline_controls=None
    t.receipt['qualified_scope']='Pending owned compatibility-addon checkbox selection and Cancel only. No addon is unloaded or reloaded. Public getter states and reopened rendered selections must restore, along with all observed settings and native fixture. Other addons, Okay/apply, effective enable/disable and persistence remain open.'
    t.receipt['custom_script_permission']='blocked_by_user';t.persist()
    try:
        layout=settings(t,'addons_original_settings')
        if layout.get('visible') or layout.get('unapplied'):raise RuntimeError('requires clean closed original settings')
        open_panel(t,'settings.addons');original=detail(t,'addons_baseline')
        t.receipt['addons_baseline']=original;rows=controls(t);baseline_controls=control_layout(rows)
        t.receipt['addons_control_baseline']=baseline_controls;t.persist()
        if (original.get('visible') is not True or set(original.get('rows',{}))!={COMPAT,HARNESS} or
            not all(valid_row(original['rows'][n],n) and
                original['rows'][n]['enable_all']==original['rows'][n]['enable_character']==2 for n in (COMPAT,HARNESS))):
            raise RuntimeError('requires both owned addons loaded and enabled for all characters')
        for name in (COMPAT,HARNESS):checkbox(t,'addons_original_'+name,original['rows'][name]['title'],True)
        t.receipt['addons_selection_attempted']=True;t.persist()
        select(t,original,False,'settings.addons.pending_off')
        cancel(t,'settings.cancel.addons')
        after=detail(t,'addons_after_cancel',closed=True)
        expected={**original,'visible':False}
        t.receipt['addons_cancel_public_restored']=after==expected;t.persist()
        if after!=expected:raise RuntimeError('AddOns Cancel did not restore exact public getter state')
        open_panel(t,'fixture.verify_addons_cancel');reopened=detail(t,'addons_reopened')
        rendered=control_layout(controls(t));state,frame=t.observe('addons_cancel_restored_rendered')
        checks={'public':reopened==original,'rendered':rendered==baseline_controls,
            'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
        t.receipt['addons_cancel_restoration']={'checks':checks,'state':state,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('reopened AddOns selections differ after Cancel')
    except Exception as error:t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        state,_=t.observe('addons_cleanup_guard')
        if 'AddonList' in state.get('panels',[]):
            if original is not None and t.receipt.get('addons_selection_attempted'):
                current=checkbox(t,'addons_cleanup_checkbox',original['rows'][COMPAT]['title'])
                if current.get('checked') is False:select(t,original,True,'fixture.restore_addons_selection')
                elif current.get('checked') is not True:raise RuntimeError('original AddOns checkbox is unreadable')
            cancel(t,'fixture.close_addons')
        if original is not None:
            after=detail(t,'addons_final_closed',closed=True)
            t.receipt['addons_final_public_restored']=after=={**original,'visible':False};t.persist()
            if not t.receipt['addons_final_public_restored']:raise RuntimeError('final AddOns public state differs')
        if layout is not None:
            after=settings(t,'addons_settings_restored')
            checks={k:after.get(k)==layout.get(k) for k in layout}
            t.receipt['addons_settings_restoration']={'checks':checks};t.persist()
            if not all(checks.values()):raise RuntimeError('AddOns trial changed saved settings')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:
            state,_=t.observe('addons_observer_guard')
            if state.get('observer_version',0)<112:raise RuntimeError('requires read-only AddOns observer112')
            native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
