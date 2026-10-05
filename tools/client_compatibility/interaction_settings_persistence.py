"""Keep one applied render-scale value through ordinary UI reload, then restore."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_render_scale import scale,value_checks,pending_step,apply,restore
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


def close(t,expected,label):
    probe=detail(t,label+'_before')
    if not all(value_checks(probe,t.render_layout,expected,expected,False).values()):
        raise RuntimeError('reload setup requires the exact applied scale and unchanged other settings')
    control=target(t,label+'_button',lambda c:c['kind']=='Button' and c['text']=='Close' and c['enabled'])
    require(t.step(label,'Close the applied stock settings before an ordinary UI reload.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},
        lambda b,a,s:{'status':'stock_settings_reload_close_pass' if s=='click' and
            'SettingsPanel' not in a['panels'] and not a.get('lua_errors') and not a.get('blocked_actions')
            else 'client_or_protocol_failure'},diagnostic_action='click',
        await_state=lambda a:'SettingsPanel' not in a['panels']),'stock_settings_reload_close_pass')


def reload_checks(before,after,session,current_session,submissions,guid):
    return {'same_native_session':current_session==session,
        'ordinary_reload':any(row.get('selected_text')=='/reload' and row.get('matches') is True
            and row.get('submitted') is True for row in submissions),
        'sequence_reset':after['sequence']<before['sequence'],
        'owned_observer':before['guid']==after['guid']==guid}


def reload(t,expected,label):
    t.clean_panels();before,before_frame=t.observe(label+'_before_reload')
    session=actors.session_entry(t.fixture)['session'];previous=len(t.receipt.get('chat_submission_checks',[]))
    t.execute({'kind':'chat','value':'/reload'})
    state,frame=t.observe(label+'_world',seconds=240)
    if state.get('observer_version',0)<117 or state.get('lua_errors') or state.get('blocked_actions'):
        raise RuntimeError('ordinary UI reload did not return a clean owned observer')
    t.settings_search=open_search(t)
    probe=detail(t,label+'_persisted',lambda p:abs(scale(p)[0]-expected)<1e-6 and
        abs(scale(p)[1]-expected)<1e-6 and p.get('unapplied') is False)
    checks=value_checks(probe,t.render_layout,expected,expected,False)
    checks.update(reload_checks(before,state,session,actors.session_entry(t.fixture)['session'],
        t.receipt.get('chat_submission_checks',[])[previous:],t.guid))
    t.receipt.setdefault('settings_reload_checks',[]).append({'label':label,'checks':checks,
        'expected_scale':expected,'session':session,'before_frame':before_frame,'world_frame':frame,'public':probe})
    t.persist()
    if not all(checks.values()):raise RuntimeError('applied settings did not persist through the owned UI reload')


def suite(t):
    state,_=t.observe('persistence_fixture')
    if state.get('observer_version',0)<117:raise RuntimeError('requires read-only observer117')
    t.receipt.update(custom_script_permission='blocked_by_user',ordinary_chat_key_hold=1.2,
        qualified_scope='Owned primary: lower one render-scale step and Apply, close Settings and ordinary /reload, then reopen Settings and verify applied/pending values with the same native session. Inverse step and Apply restore the original scale, which must also survive another ordinary UI reload. Original settings layout and native fixture restore. Full client restart, account/character storage and other settings persistence remain open.')
    t.persist();t.settings_search=open_search(t);layout=detail(t,'persistence_layout_baseline');t.render_layout=layout
    original,pending=scale(layout)
    if layout.get('unapplied') is not False or abs(original-pending)>=1e-6 or not .5<original<=1:
        raise RuntimeError('requires an applied reversible render-scale fixture')
    t.receipt['render_layout_baseline']=layout;t.persist()
    try:
        search(t,'Render Scale','settings.persistence.render_search')
        lower=pending_step(t,-1,'settings.persistence.lower_pending')
        apply(t,lower,'settings.persistence.lower_apply')
        close(t,lower,'settings.persistence.lower_close')
        reload(t,lower,'settings.persistence.lower_reload')
        search(t,'Render Scale','settings.persistence.original_search')
        pending_step(t,1,'settings.persistence.original_pending',expected=original)
        apply(t,original,'settings.persistence.original_apply')
        close(t,original,'settings.persistence.original_close')
        reload(t,original,'settings.persistence.original_reload')
    finally:
        state,_=t.observe('persistence_cleanup_visibility')
        if 'SettingsPanel' not in state['panels']:
            t.clean_panels();t.settings_search=open_search(t)
        restore(t,layout)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code',chat_key_hold=1.2)
        try:native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':main()
