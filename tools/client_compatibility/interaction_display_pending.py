"""Select stock pending display options and discard each before Apply."""
import argparse,json,math,re,time
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

SPECS={'resolution':('Resolution','PROXY_RESOLUTION',1),
    'window_mode':('Display Mode','PROXY_DISPLAY_MODE',-1),
    'monitor_selection':('Monitor','PROXY_PRIMARY_MONITOR',1)}


def fixture(layout):
    values=layout['values'];display=layout.get('display_state') or {}
    if (layout.get('unapplied') is not False or layout.get('discard_dialogs') or
            values.get('PROXY_RESOLUTION')!='1280x720' or values.get('PROXY_DISPLAY_MODE') is not False or
            type(values.get('PROXY_PRIMARY_MONITOR')) not in (int,float) or values['PROXY_PRIMARY_MONITOR']!=0 or
            layout['cvars'].get('gxMaximize')!='0' or layout['cvars'].get('gxMonitor')!='0' or
            display.get('window_size')!={'width':1280,'height':720} or
            type(display.get('monitor')) not in (int,float) or display.get('monitor')!=0 or
            display.get('fullscreen') is not False or not all(type(display.get(k)) in (int,float) and
                math.isfinite(display[k]) and display[k]>0 for k in ['screen_width','screen_height'])):
        raise RuntimeError('requires the clean owned1280x720 Windowed/Primary active-display fixture')


def candidate(kind,value,original):
    if kind=='window_mode':return value is True and original is False
    if kind=='monitor_selection':return type(value) in (int,float) and value==1 and original==0
    if kind!='resolution' or not isinstance(value,str):return False
    match=re.fullmatch(r'([1-9][0-9]{2,3})x([1-9][0-9]{2,3})',value)
    if not match:return False
    width,height=map(int,match.groups())
    return 800<=width<=1920 and 600<=height<=1080 and value!=original


def active_checks(current,baseline):
    return {'active_cvars':current.get('cvars')==baseline['cvars'],
        'active_display':current.get('display_state')==baseline['display_state']}


def checks(current,baseline,kind,pending,expected=None):
    variable=SPECS[kind][1];wanted=expected if pending else baseline['values'][variable]
    actual=current.get('values',{}).get(variable)
    typed=(candidate(kind,actual,baseline['values'][variable]) if pending else type(actual)==type(wanted))
    result=active_checks(current,baseline)
    result.update(pending_value=typed and actual==wanted,
        other_settings={k:v for k,v in current.get('values',{}).items() if k!=variable}==
            {k:v for k,v in baseline['values'].items() if k!=variable},
        unapplied_state=current.get('unapplied') is pending)
    return result


def exit_dialog(t,layout,kind,value,label,cleanup=False):
    control=target(t,label+'_close',lambda c:c['kind']=='Button' and c['text']=='Close' and c['enabled'])
    def outcome(b,a,s):
        probe=detail(t,label+'_dialog',lambda p:bool(p.get('discard_dialogs')));name=dialog(probe)
        result=active_checks(probe,layout) if cleanup else checks(probe,layout,kind,True,value)
        result.update(ordinary_close=s=='click',popup_visible=name in a['panels'],unapplied=probe.get('unapplied') is True)
        return {'status':'pending_display_exit_dialog_pass' if all(result.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':result,'popup_name':name,'cleanup_only':cleanup}}
    require(t.step(label,'Open the stock exit confirmation for the owned pending display edit.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'pending_display_exit_dialog_pass')


def discard(t,layout,kind,value,label,cleanup=False):
    before=detail(t,label+'_before');name=dialog(before)
    result=active_checks(before,layout) if cleanup else checks(before,layout,kind,True,value)
    if not all(result.values()) or before.get('unapplied') is not True:
        raise RuntimeError('discard requires unchanged active display and the attributed pending fixture')
    attempts=t.receipt.setdefault('display_discard_attempted',{})
    if attempts.get(kind):raise RuntimeError('failed display discard is never replayed')
    control=target(t,label+'_exit',lambda c:c['kind']=='Button' and c['name']==name+'Button1' and c['enabled'])
    attempts[kind]=True;t.persist()
    require(t.step(label,'Use stock Exit to discard the pending display edit without Apply.',
        {'exit':{'kind':'click','value':point(control),'hold':1.2}},lambda b,a,s:
        {'status':'pending_display_discard_closed' if s=='exit' and 'SettingsPanel' not in a['panels'] and
            name not in a['panels'] and not a.get('lua_errors') and not a.get('blocked_actions')
            else 'client_or_protocol_failure'},diagnostic_action='exit',
        await_state=lambda a:'SettingsPanel' not in a['panels'] and name not in a['panels']),
        'pending_display_discard_closed')
    t.clean_panels();t.settings_search=open_search(t)
    restored=detail(t,label+'_restored');result=checks(restored,layout,kind,False)
    result['dialog_closed']=not restored.get('discard_dialogs')
    t.receipt.setdefault('display_restorations',{})[kind]={'checks':result,'public':restored,'cleanup_only':cleanup};t.persist()
    if not all(result.values()):raise RuntimeError('stock display discard did not restore the exact original values')


def recon_matches(old,current,kinds):
    layout=old.get('settings_layout_restoration',{}).get('checks',{})
    native=old.get('native_restoration',{}).get('checks',{})
    terms={row.get('term') for row in old.get('settings_recon',[])}
    native_names={'resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions'}
    return bool(old.get('completed') is True and old.get('finished_at') and old.get('actor')==current.get('actor') and
        old.get('runtime')==current.get('runtime') and set(layout)=={'search','category','values','unapplied','cvars'} and
        all(v is True for v in layout.values()) and set(native)==native_names and
        all(v is True for v in native.values()) and all(SPECS[kind][0] in terms for kind in kinds))


def suite(t,kinds,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned closed reconnaissance episode')
    old=json.loads(source.read_text())
    if not recon_matches(old,t.receipt,kinds):
        raise RuntimeError('requires the closed owned display reconnaissance and its restoration')
    state,_=t.observe('pending_display_fixture')
    if state.get('observer_version',0)<119:raise RuntimeError('requires active-video-size observer119')
    t.receipt.update(source={'path':str(source),'sha256':lab.sha256(source)},custom_script_permission='blocked_by_user',
        requested_display_settings=kinds,qualified_scope='Owned primary: one stock pending arrow selection for each requested display proxy, then exact Close/Exit discard before Apply. All active CVars, installed video API size, screen metrics and physical HDMI-1 ownership stay fixed. Each proxy and all other settings restore before the next selection; original layout and native fixture restore. Applied resolution/mode/monitor switches, allocation, performance and persistence remain open.')
    t.persist();t.settings_search=open_search(t);layout=detail(t,'display_layout_baseline');fixture(layout)
    if any(layout[k]!=old['settings_layout_baseline'][k] for k in ['cvars','values','unapplied']):
        raise RuntimeError('original display/settings values differ from the closed reconnaissance')
    t.receipt['display_layout_baseline']=layout;t.persist();active=None;value=None
    try:
        for kind in kinds:
            active=kind;value=None;term,variable,direction=SPECS[kind];label='settings.'+kind
            search(t,term,label+'.search')
            combo=target(t,label+'_combo',lambda c:c['kind']=='Button' and c.get('setting_variable')==variable and
                bool(c['text']) and c.get('setting_value')==layout['values'][variable])
            control=target(t,label+'_arrow',lambda c:c['kind']=='Button' and c['enabled'] and not c['text'] and
                c.get('setting_variable')==variable and c['y']==combo['y'] and (c['x']-combo['x'])*direction>0)
            def outcome(b,a,s):
                nonlocal value
                probe=detail(t,label+'_pending',lambda p:p['values'].get(variable)!=layout['values'][variable]
                    and p.get('unapplied') is True);value=probe['values'].get(variable)
                result=checks(probe,layout,kind,True,value)
                result.update(ordinary_stepper=s=='click',ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
                return {'status':'stock_pending_display_selection_pass' if all(result.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':result,'kind':kind,'variable':variable,'original':layout['values'][variable],
                        'pending':value,'public':probe}}
            require(t.step(label+'.pending','Select one observed stock pending '+term+' option.',
                {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
                'stock_pending_display_selection_pass')
            exit_dialog(t,layout,kind,value,label+'.exit_dialog');discard(t,layout,kind,value,label+'.discard')
    finally:
        state,_=t.observe('display_cleanup_visibility')
        if 'SettingsPanel' not in state['panels']:t.clean_panels();t.settings_search=open_search(t)
        current=detail(t,'display_cleanup_before')
        if current.get('unapplied'):
            if active is None:raise RuntimeError('unattributed pending edit is not discarded')
            if not current.get('discard_dialogs'):exit_dialog(t,layout,active,value,'fixture.display.cleanup_dialog',True)
            discard(t,layout,active,value,'fixture.display.cleanup_discard',True)
        final=detail(t,'display_cleanup_values');result=active_checks(final,layout)
        result.update(all_settings=final['values']==layout['values'],no_pending=final.get('unapplied') is False)
        t.receipt['display_final_restoration']={'checks':result};t.persist()
        if not all(result.values()):raise RuntimeError('original active display and settings differ during cleanup')
        restore_layout(t,layout,'fixture.display.layout')
        t.receipt['display_layout_restoration']=t.receipt.pop('volume_layout_restoration');t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--setting',choices=tuple(SPECS),action='append',required=True)
    a=p.parse_args()
    if len(set(a.setting))!=len(a.setting):p.error('each pending setting may be requested once')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=lambda t:suite(t,a.setting,a.source),preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':main()
