"""Roundtrip the stock character-specific binding-set checkbox and saved set."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_keybindings import open_editor
from .interaction_operations import controls,click_case
from .interaction_macros import require,edit_case

VARIABLE='PROXY_CHARACTER_SPECIFIC_BINDINGS'


def setting(t):
    rows=[r for r in controls(t) if r.get('setting_variable')==VARIABLE and r['kind']=='CheckButton']
    if len(rows)!=1 or not rows[0].get('enabled'):raise RuntimeError('exact stock binding-set checkbox missing')
    return rows[0]


def choose(t,value,label):
    row=setting(t)
    if row.get('setting_value')==value:raise RuntimeError('binding-set checkbox is already at the requested value')
    expected='binding_set_checkbox_pass' if value else 'binding_set_confirmation_pass'
    require(click_case(t,label,'Toggle the stock Character Specific Key Bindings checkbox.',
        lambda c:c.get('setting_variable')==VARIABLE and c['kind']=='CheckButton',
        lambda b,a,s:{'status':expected if s and (setting(t).get('setting_value') is True if value else
            'StaticPopup1' in a['panels']) else 'client_or_protocol_failure'}),expected)
    if not value:confirm_account(t)


def confirm_account(t):
    require(click_case(t,'fixture.confirm_original_account_bindings','Confirm restoration of the original account bindings.',
        lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Okay',
        lambda b,a,s:{'status':'binding_set_checkbox_pass' if s and a.get('binding_set')==1 and
            'StaticPopup1' not in a['panels'] else 'client_or_protocol_failure'}),'binding_set_checkbox_pass')


def editor(t):
    open_editor(t)
    require(edit_case(t,'fixture.clear_binding_filter','Clear the settings filter to expose the binding-set checkbox.',
        lambda c:not c['name'],''),'ui_edit_pass')


def close(t,label,expected):
    require(click_case(t,label,'Close settings to save the selected binding set.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'binding_set_saved_pass' if s and 'SettingsPanel' not in a['panels'] and
            a.get('binding_set')==expected else 'client_or_protocol_failure'},
        await_state=lambda s:'SettingsPanel' not in s['panels'] and s.get('binding_set')==expected),'binding_set_saved_pass')


def operations(t):
    state,_=t.observe('binding_set_fixture')
    if state['binding_set']!=1 or state.get('binding_probe'):raise RuntimeError('requires original account bindings and unused test chord')
    original={k:state.get(k) for k in ['binding_set','fps_keys','binding_probe','framerate_visible']}
    account=lab.client_root()/'client/_whitemane-60895_/WTF/Account/CLIENTLAB'
    cache=account/'Client442 Lab/Harnessone/bindings-cache.wtf'
    if cache.exists():raise RuntimeError('requires no original character-specific bindings file')
    account_hash=lab.sha256(account/'bindings-cache.wtf');changed=False
    t.receipt['character_bindings_file_before']={'file':str(cache),'exists':False,'account_sha256':account_hash}
    t.receipt['binding_set_baseline']=original;t.persist()
    try:
        editor(t)
        if setting(t).get('setting_value') is not False:raise RuntimeError('original character binding checkbox differs')
        changed=True;choose(t,True,'keybindings.per_character_toggle');close(t,'fixture.save_character_set',2)
        t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('character_set_reloaded',seconds=120)
        checks={'character_set':state.get('binding_set')==2,'fps_binding':state.get('fps_keys')==original['fps_keys'],
            'test_chord_unused':not state.get('binding_probe'),'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt['character_binding_set_persistence']={'checks':checks,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('saved character binding set differs after reload')
        editor(t)
        if setting(t).get('setting_value') is not True:raise RuntimeError('saved character checkbox differs')
        choose(t,False,'fixture.restore_account_checkbox');close(t,'fixture.save_original_account_set',1)
        t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('account_set_restored',seconds=120)
        restored=all(state.get(k)==v for k,v in original.items())
        t.receipt['binding_set_restoration']={'restored':restored,'frame':frame};t.persist()
        if not restored:raise RuntimeError('original account binding state differs')
    except Exception as error:
        t.receipt['operation_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        if changed:
            state,_=t.observe('binding_set_cleanup_check')
            if state.get('binding_set')!=1:
                if 'StaticPopup1' in state['panels']:confirm_account(t)
                else:
                    if 'SettingsPanel' not in state['panels']:editor(t)
                    choose(t,False,'fixture.emergency_restore_account_checkbox')
                close(t,'fixture.emergency_save_original_set',1)
            if lab.sha256(account/'bindings-cache.wtf')!=account_hash:
                raise RuntimeError('original account binding file differs')
            if cache.exists():
                if cache.is_symlink() or cache.stat().st_mtime<t.receipt['started_at']:
                    raise RuntimeError('created character binding file identity differs')
                t.receipt['created_character_binding_file_removed']={'sha256':lab.sha256(cache)}
                cache.unlink();t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=operations);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
