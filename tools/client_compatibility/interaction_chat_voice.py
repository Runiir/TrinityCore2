"""Test local self-mute through the installed stock binding, then remove it."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_settings_search import open_search
from .interaction_operations import controls,click_case,point
from .interaction_macros import edit_case,require
from .interaction_chat_window import detail
from .interaction_keybindings_native import suite as native_suite

ACTION='TOGGLE_VOICE_SELF_MUTE'


def editor(t,label):
    field=open_search(t)
    require(click_case(t,label+'_category','Open the installed Keybindings category.',
        lambda c:c['text']=='Keybindings',lambda b,a,s:{'status':'panel_open_pass' if s and
            'SettingsPanel' in a['panels'] else 'client_or_protocol_failure'}),'panel_open_pass')
    require(edit_case(t,label+'_search','Search the installed mute binding.',
        lambda c:c['kind']=='EditBox' and point(c)==point(field),'mute'),'ui_edit_pass')
    rows=[c for c in controls(t) if c.get('binding_action')==ACTION]
    if len(rows)!=2 or {c.get('binding_slot') for c in rows}!={1,2}:
        raise RuntimeError('requires the exact two stock self-mute binding slots')
    t.receipt.setdefault('voice_binding_rows',{})[label]=rows;t.persist();return rows


def close(t,label):
    require(click_case(t,label,'Close the observed stock settings panel.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else
            'client_or_protocol_failure'}),'panel_closed_pass')


def toggle(t,before,wanted,label):
    def outcome(b,a,s):
        voice=detail(t,label+'_public')['voice'];expected={**before,'muted':wanted}
        checks={'ordinary_owned_binding':s=='mute' and b.get('binding_probe')==ACTION,
            'exact_public_voice_state':voice==expected,'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'owned_local_voice_mute_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':voice,'expected':expected}}
    require(t.step(label,'Toggle local self-mute through its observed installed binding.',
        {'mute':{'kind':'key','value':'ctrl+shift+F12','hold':1.2}},outcome,diagnostic_action='mute'),
        'owned_local_voice_mute_pass')


def play(t):
    before=detail(t,'voice_original')['voice'];state,frame=t.observe('voice_binding_original')
    if not before.get('available') or before.get('muted') is not False or state.get('binding_probe'):
        raise RuntimeError('requires public unmuted voice state and the unused owned test chord')
    t.receipt['voice_baseline']={'public':before,'frame':frame};t.persist();initial=None
    try:
        initial=editor(t,'voice_assign')
        if any(c['text']!='|cff808080Not Bound|r' or not c['enabled'] for c in initial):
            raise RuntimeError('both original self-mute slots must be unbound')
        require(click_case(t,'fixture.voice_binding_listen','Listen on the observed first self-mute slot.',
            lambda c:c.get('binding_action')==ACTION and c.get('binding_slot')==1,
            lambda b,a,s:{'status':'binding_listener_pass' if s and
                a.get('keybind_listening')=={'action':ACTION,'slot':1} else 'client_or_protocol_failure'}),
            'binding_listener_pass')
        require(t.step('fixture.voice_binding_assign','Assign the unused Control Shift F12 chord.',
            {'assign':{'kind':'key','value':'ctrl+shift+F12','hold':1.2}},
            lambda b,a,s:{'status':'binding_assign_pass' if s=='assign' and a.get('binding_probe')==ACTION and
                not a.get('keybind_listening') else 'client_or_protocol_failure'},diagnostic_action='assign'),
            'binding_assign_pass')
        close(t,'fixture.voice_binding_save');t.clean_panels()
        toggle(t,before,True,'chat.mute_voice');toggle(t,before,False,'fixture.voice_unmute')
    finally:
        state,_=t.observe('voice_cleanup_guard')
        listener=state.get('keybind_listening')
        if listener:
            if listener!={'action':ACTION,'slot':1}:raise RuntimeError('refuses unrelated binding listener')
            t.execute({'kind':'key','value':'Escape','hold':1.2})
            state,_=t.observe('voice_listener_cancelled')
            if state.get('keybind_listening'):raise RuntimeError('self-mute listener did not cancel')
        if 'SettingsPanel' in state.get('panels',[]):close(t,'fixture.voice_cleanup_panel')
        t.clean_panels();current=detail(t,'voice_cleanup_public')['voice']
        state,_=t.observe('voice_cleanup_binding_guard')
        if current.get('muted')!=before['muted']:
            if state.get('binding_probe')!=ACTION:raise RuntimeError('refuses unrelated mute cleanup binding')
            toggle(t,before,before['muted'],'fixture.voice_mute_recover')
        if state.get('binding_probe')==ACTION:
            rows=editor(t,'voice_remove');slot=next(c for c in rows if c.get('binding_slot')==1)
            require(t.step('fixture.voice_binding_remove','Remove only the temporary self-mute binding.',
                {'remove':{'kind':'click','value':point(slot),'button':3,'hold':1.2}},
                lambda b,a,s:{'status':'binding_removed_pass' if s=='remove' and not a.get('binding_probe') else
                    'client_or_protocol_failure'},diagnostic_action='remove'),'binding_removed_pass')
            restored=[c for c in controls(t) if c.get('binding_action')==ACTION]
            if len(restored)!=2 or any(c['text']!='|cff808080Not Bound|r' for c in restored):
                raise RuntimeError('original unbound self-mute slots differ')
            close(t,'fixture.voice_binding_restore_save')
        elif state.get('binding_probe'):raise RuntimeError('refuses removal of an unrelated test chord')
        t.clean_panels();after=detail(t,'voice_restored')['voice'];state,frame=t.observe('voice_restored_rendered')
        checks={'voice':after==before,'test_chord':not state.get('binding_probe'),
            'closed_ui':not state.get('panels'),'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt['voice_restoration']={'checks':checks,'public':after,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('local voice or temporary binding restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    t=Trial(p.parse_args().output,controller='code')
    try:native_suite(t,operations=play);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
