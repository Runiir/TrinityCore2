"""Reach the installed character macro cap through stock input and restore it."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_macro_controls import detail,open_editor,close_editor,tab,create,delete_selected
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_macros import require


def limit(t,label,expected):
    button=target(t,label,lambda c:c['name']=='MacroNewButton')
    before=detail(t,label+'_before')
    if button['enabled'] or before['counts']!=[0,expected] or before['tab']!=2:
        raise RuntimeError('requires the observed full character macro bank and disabled New button')
    def outcome(b,a,s):
        after=detail(t,label+'_after')
        fresh=target(t,label+'_new_button_after',lambda c:c['name']=='MacroNewButton')
        checks={'ordinary_click':s=='click','installed_cap':after['character_limit']==expected,
            'count_at_cap':after['counts']==[0,expected],'new_disabled':fresh['enabled'] is False,
            'no_new_dialog':not after['popup']['visible'],'selection_unchanged':after['selected']==before['selected'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'character_macro_limit_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'new_button':fresh}}
    require(t.step(label,'Verify the stock New button prevents an additional character macro at its installed cap.',
        {'click':{'kind':'click','value':point(button),'description':'Click the observed disabled stock New button.'}},
        outcome,diagnostic_action='click'),'character_macro_limit_pass')


def operations(t):
    state,_=t.observe('macro_limit_fixture')
    if state.get('macros')!=[0,0] or state.get('action_probe',{}).get('kind'):
        raise RuntimeError('requires zero original macros and an empty action probe')
    t.targeted_controls=True;open_editor(t);p=detail(t,'installed_macro_limits')
    cap=p['character_limit']
    if not isinstance(cap,int) or not 1<=cap<=30:raise RuntimeError('installed character macro cap exceeds the bounded fixture')
    t.owned_macro_names=tuple('TC442Limit'+str(i).zfill(2) for i in range(1,cap+1))
    t.receipt['owned_macro_names']=t.owned_macro_names;t.receipt['macro_limit_baseline']=state;t.persist()
    try:
        if p['tab']!=2:tab(t,2,'fixture.character_macro_bank')
        for name in t.owned_macro_names:create(t,name)
        limit(t,'macros.macro_limit',cap)
        current=detail(t,'cap_before_reopen')['selected']['name']
        delete_selected(t,'fixture.reopen_one_macro_slot')
        button=target(t,'new_reenabled',lambda c:c['name']=='MacroNewButton')
        reopened=detail(t,'macro_slot_reopened')
        t.receipt['macro_limit_reopened']={'checks':{'one_free_slot':reopened['counts']==[0,cap-1],
            'new_reenabled':button['enabled'] is True},'button':button};t.persist()
        if not all(t.receipt['macro_limit_reopened']['checks'].values()):raise RuntimeError('New did not reenable below the cap')
        create(t,current);limit(t,'fixture.macro_limit_repeated',cap)
    except Exception as error:
        t.receipt['operation_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        close_editor(t);open_editor(t)
        if detail(t,'cleanup_macro_limit_tab')['tab']!=2:tab(t,2,'fixture.cleanup_character_bank')
        for i in range(cap):
            if detail(t,'macro_limit_cleanup_'+str(i))['counts'][1]==0:break
            delete_selected(t,'fixture.remove_limit_macro_'+str(i))
        if detail(t,'macro_limit_cleanup_verified')['counts']!=[0,0]:raise RuntimeError('macro limit fixture cleanup differs')
        tab(t,1,'fixture.restore_account_macro_tab');close_editor(t)
        t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('macro_limit_restored',seconds=120)
        checks={'zero_macros':state.get('macros')==[0,0],'empty_action_probe':not state.get('action_probe',{}).get('kind'),
            'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt['macro_limit_restoration']={'checks':checks,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('macro limit baseline was not restored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=operations,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
