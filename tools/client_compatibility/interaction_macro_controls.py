"""Observe and roundtrip stock macro controls on an empty owned fixture."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_operations import controls,click_case as catalog_click
from .interaction_macros import require,edit_case as catalog_edit
from .interaction_observation import read_current_page
from .interaction_control_target import click as target_click,edit as target_edit,target


def click_case(t,label,goal,predicate,oracle):
    if getattr(t,'targeted_controls',False):return target_click(t,label,goal,predicate,oracle)
    return catalog_click(t,label,goal,predicate,oracle)


def edit_case(t,label,goal,predicate,value):
    if getattr(t,'targeted_controls',False):return target_edit(t,label,goal,predicate,value)
    return catalog_edit(t,label,goal,predicate,value)


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'macros',lambda s:s.get('macro_probe') and
        (ready is None or ready(s['macro_probe'])))
    t.receipt.setdefault('macro_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['macro_probe']


def open_editor(t):
    state,_=t.observe('before_open_macro_editor')
    if 'MacroFrame' not in state['panels']:t.execute({'kind':'chat','value':'/macro'})
    return detail(t,'macro_editor_open',lambda p:p.get('open'))


def close_editor(t):
    state,_=t.observe('before_close_macro_editor')
    if 'StaticPopup1' in state['panels']:
        require(click_case(t,'fixture.cancel_macro_confirmation','Cancel the owned macro confirmation.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',lambda b,a,s:{'status':'macro_dialog_closed' if s and
                'StaticPopup1' not in a['panels'] else 'client_or_protocol_failure'}),'macro_dialog_closed')
    state,_=t.observe('before_close_macro_popup')
    if 'MacroPopupFrame' in state['panels']:
        require(click_case(t,'fixture.cancel_macro_popup','Cancel the unsaved macro name/icon dialog.',
            lambda c:c['text']=='Cancel' and c['name']!='MacroCancelButton',lambda b,a,s:{'status':'macro_dialog_closed' if s and
                'MacroPopupFrame' not in a['panels'] else 'client_or_protocol_failure'}),'macro_dialog_closed')
    state,_=t.observe('before_macro_exit')
    if 'MacroFrame' in state['panels']:
        require(click_case(t,'fixture.exit_macro_editor','Close the macro editor with its stock Exit button.',
            lambda c:c['name']=='MacroExitButton',lambda b,a,s:{'status':'macro_editor_closed' if s and
                'MacroFrame' not in a['panels'] else 'client_or_protocol_failure'}),'macro_editor_closed')
    t.clean_panels()


def recon(t):
    state,_=t.observe('macro_fixture')
    if state.get('macros')!=[0,0] or state.get('test_macro') or state.get('action_probe',{}).get('kind'):
        raise RuntimeError('requires the empty owned macro fixture and action probe')
    t.receipt['macro_baseline']=state;t.persist()
    open_editor(t)
    t.receipt['macro_editor_controls']=controls(t);t.persist()
    require(click_case(t,'fixture.new_macro_popup','Open the stock new-macro dialog.',
        lambda c:c['name']=='MacroNewButton',lambda b,a,s:{'status':'macro_popup_pass' if s and
            'MacroPopupFrame' in a['panels'] else 'client_or_protocol_failure'}),'macro_popup_pass')
    detail(t,'new_macro_popup',lambda p:p['popup']['visible'])
    t.receipt['macro_popup_controls']=controls(t);t.persist()
    require(click_case(t,'fixture.cancel_new_macro','Cancel the unchanged new-macro dialog.',
        lambda c:c['text']=='Cancel' and c['name']!='MacroCancelButton',lambda b,a,s:{'status':'macro_popup_closed' if s and
            'MacroPopupFrame' not in a['panels'] and a.get('macros')==[0,0] else 'client_or_protocol_failure'}),'macro_popup_closed')
    close_editor(t)


NAMES=('TC442A','TC442B','TC442C','TC442Renamed')


def tab(t,index,label):
    def outcome(b,a,s):
        p=detail(t,label+'_detail',lambda p:p.get('tab')==index)
        checks={'stock_tab_clicked':s,'tab':p['tab']==index,
            'base':p['base']==(0 if index==1 else p['account_limit']),
            'limit':p['limit']==p['account_limit' if index==1 else 'character_limit'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        if getattr(t,'empty_macro_guard_required',False) and p['counts'][index-1]==0:
            delete=target(t,label+'_empty_delete',lambda c:c['name']=='MacroDeleteButton')
            checks['empty_bank_no_selected_macro']=not p['selected'].get('name')
            checks['empty_bank_body_hidden']=not any(c.get('name')=='MacroFrameText' for c in a.get('edit_fields') or [])
            checks['empty_bank_delete_disabled']=delete['enabled'] is False
        return {'status':'macro_tab_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':p}}
    require(click_case(t,label,'Select the stock '+('General' if index==1 else 'Character Specific')+' Macros tab.',
        lambda c:c['name']=='MacroFrameTab'+str(index),outcome),'macro_tab_pass')


def create(t,name):
    before=detail(t,'before_create_'+name);counts=list(before['counts']);counts[before['tab']-1]+=1
    require(click_case(t,'fixture.new_'+name,'Open New for an owned disposable macro.',
        lambda c:c['name']=='MacroNewButton',lambda b,a,s:{'status':'macro_popup_pass' if s and
            'MacroPopupFrame' in a['panels'] else 'client_or_protocol_failure'}),'macro_popup_pass')
    require(edit_case(t,'fixture.name_'+name,'Name the disposable macro '+name+'.',
        lambda c:not c['name'] and c['context'].startswith('Enter Macro Name'),name),'ui_edit_pass')
    def created(b,a,s):
        p=detail(t,'created_'+name,lambda p:p['counts']==counts and p['selected'].get('name')==name)
        return {'status':'macro_fixture_created' if s and p['counts']==counts and
            p['selected'].get('name')==name and not p['popup']['visible'] else 'client_or_protocol_failure',
            'oracle':{'public':p}}
    require(click_case(t,'fixture.create_'+name,'Save the disposable macro.',
        lambda c:c['text']=='Okay',created),'macro_fixture_created')


def select(t,name,label):
    def selected(b,a,s):
        p=detail(t,label+'_detail',lambda p:p['selected'].get('name')==name)
        return {'status':'macro_selection_pass' if s and p['selected'].get('name')==name else 'client_or_protocol_failure',
            'oracle':{'public':p}}
    require(click_case(t,label,'Select the visible '+name+' macro from the stock list.',
        lambda c:c.get('macro_name')==name and c['name']!='MacroFrameSelectedMacroButton',selected),
        'macro_selection_pass')


def delete_selected(t,label):
    p=detail(t,label+'_before');name=p['selected'].get('name')
    if name not in getattr(t,'owned_macro_names',NAMES):raise RuntimeError('refusing to delete a macro outside the owned fixture')
    counts=list(p['counts']);counts[p['tab']-1]-=1
    require(click_case(t,label+'_dialog','Open deletion confirmation for the selected disposable macro.',
        lambda c:c['name']=='MacroDeleteButton',lambda b,a,s:{'status':'macro_delete_dialog_pass' if s and
            'StaticPopup1' in a['panels'] else 'client_or_protocol_failure'}),'macro_delete_dialog_pass')
    def deleted(b,a,s):
        after=detail(t,label+'_deleted',lambda p:p['counts']==counts)
        return {'status':'macro_fixture_deleted' if s and after['counts']==counts and
            'StaticPopup1' not in a['panels'] else 'client_or_protocol_failure','oracle':{'public':after,'deleted':name}}
    require(click_case(t,label,'Confirm deletion of the owned disposable macro.',
        lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Okay',deleted),'macro_fixture_deleted')


def operations(t):
    state,_=t.observe('macro_fixture')
    if state.get('macros')!=[0,0] or state.get('test_macro') or state.get('action_probe',{}).get('kind'):
        raise RuntimeError('requires the empty owned macro fixture and action probe')
    t.receipt['macro_baseline']=state;t.persist()
    try:
        open_editor(t);create(t,NAMES[0]);create(t,NAMES[1])
        tab(t,2,'macros.character_tab');create(t,NAMES[2])
        tab(t,1,'macros.account_tab');select(t,NAMES[0],'macros.select')
        original=detail(t,'before_rename')['selected']
        require(click_case(t,'fixture.edit_name_icon','Open Change Name/Icon for the selected disposable macro.',
            lambda c:c['name']=='MacroEditButton',lambda b,a,s:{'status':'macro_popup_pass' if s and
                'MacroPopupFrame' in a['panels'] else 'client_or_protocol_failure'}),'macro_popup_pass')
        require(edit_case(t,'macros.rename','Rename the selected disposable macro to '+NAMES[3]+'.',
            lambda c:not c['name'] and c['context'].startswith('Enter Macro Name'),NAMES[3]),'ui_edit_pass')
        rows=controls(t);icons=[c for c in rows if c['enabled'] and c['kind']=='Button' and
            not c['name'] and not c['text'] and isinstance(c.get('macro_icon_texture'),int) and
            c['macro_icon_texture']!=original['icon']]
        if not icons:raise RuntimeError('no observed alternative stock macro icon')
        chosen=icons[0];t.receipt['chosen_icon_control']=chosen;t.persist()
        require(click_case(t,'macros.icon','Choose the observed alternative icon from the stock icon grid.',
            lambda c:c==chosen,lambda b,a,s:{'status':'macro_icon_clicked' if s and
                'MacroPopupFrame' in a['panels'] else 'client_or_protocol_failure'}),'macro_icon_clicked')
        def edited(b,a,s):
            p=detail(t,'renamed_icon_saved',lambda p:p['selected'].get('name')==NAMES[3] and
                p['selected'].get('icon')==chosen['macro_icon_texture'])
            checks={'stock_save':s,'name':p['selected']['name']==NAMES[3],
                'icon':p['selected']['icon']==chosen['macro_icon_texture'],'body':p['selected']['body']==original['body'],
                'counts':p['counts']==[2,1],'popup_closed':not p['popup']['visible']}
            return {'status':'macro_edit_saved_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':p}}
        require(click_case(t,'fixture.save_rename_icon','Save the changed name and icon.',lambda c:c['text']=='Okay',edited),
            'macro_edit_saved_pass')
        before=detail(t,'before_cancel_delete')
        require(click_case(t,'fixture.delete_cancel_dialog','Open the stock macro deletion confirmation.',
            lambda c:c['name']=='MacroDeleteButton',lambda b,a,s:{'status':'macro_delete_dialog_pass' if s and
                'StaticPopup1' in a['panels'] else 'client_or_protocol_failure'}),'macro_delete_dialog_pass')
        def cancelled(b,a,s):
            p=detail(t,'delete_cancelled')
            checks={'stock_cancel':s,'confirmation_closed':'StaticPopup1' not in a['panels'],
                'counts':p['counts']==before['counts'],'selected':p['selected']==before['selected']}
            return {'status':'macro_delete_cancel_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':p}}
        require(click_case(t,'macros.delete_cancel','Cancel the stock macro deletion confirmation.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',cancelled),'macro_delete_cancel_pass')
        close_editor(t);t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('macro_controls_reloaded',seconds=120)
        if state.get('macros')!=[2,1]:raise RuntimeError('macro fixture counts differ after reload')
        open_editor(t)
        if detail(t,'reloaded_macro_tab')['tab']!=1:tab(t,1,'fixture.reload_account_tab')
        select(t,NAMES[3],'fixture.reloaded_renamed_macro');after=detail(t,'reloaded_macro_detail')
        checks={'counts':after['counts']==[2,1],'name':after['selected']['name']==NAMES[3],
            'icon':after['selected']['icon']==chosen['macro_icon_texture'],'body':after['selected']['body']==original['body']}
        t.receipt['macro_controls_persistence']={'checks':checks,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('saved macro edits differ after reload')
    except Exception as error:
        t.receipt['operation_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        close_editor(t);open_editor(t)
        for index in (1,2):
            p=detail(t,'cleanup_tab_'+str(index))
            if p['tab']!=index:tab(t,index,'fixture.cleanup_tab_'+str(index))
            for number in range(3):
                p=detail(t,'cleanup_count_'+str(index)+'_'+str(number))
                if p['counts'][index-1]==0:break
                delete_selected(t,'fixture.cleanup_macro_'+str(index)+'_'+str(number))
            if detail(t,'cleanup_verified_'+str(index))['counts'][index-1]!=0:
                raise RuntimeError('owned macro cleanup left macros')
        tab(t,1,'fixture.restore_account_tab');close_editor(t)
        t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('macros_restored',seconds=120)
        checks={'zero_macros':state.get('macros')==[0,0],'empty_action_probe':not state.get('action_probe',{}).get('kind'),
            'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt['macro_restoration']={'checks':checks,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('macro baseline restoration differs')


def recover(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require a private closed macro trial receipt')
    old=json.loads(source.read_text())
    if old.get('completed') or not old.get('finished_at') or not old.get('failure') or old['actor']['guid']!=t.fixture['guid']:
        raise RuntimeError('recovery source is not a closed failed owned trial')
    if old.get('macro_baseline',{}).get('macros')!=[0,0] or not any(c['id']=='fixture.create_TC442C' and
            c['status']=='macro_fixture_created' for c in old['cases']):
        raise RuntimeError('recovery source does not prove the owned character macro fixture')
    if old['runtime']!=t.receipt['runtime']:raise RuntimeError('macro recovery runtime identity differs')
    state,_=t.observe('macro_recovery_fixture')
    if state.get('macros')!=[0,1] or state.get('action_probe',{}).get('kind'):
        raise RuntimeError('requires exactly the remaining owned character macro')
    t.targeted_controls=True;t.receipt['macro_recovery_source']={'file':str(source),'sha256':lab.sha256(source)};t.persist()
    open_editor(t)
    if detail(t,'macro_recovery_tab')['tab']!=2:tab(t,2,'fixture.recover_character_tab')
    if detail(t,'macro_recovery_selected')['selected'].get('name')!=NAMES[2]:
        raise RuntimeError('remaining character macro identity differs')
    delete_selected(t,'fixture.recover_owned_character_macro')
    tab(t,1,'fixture.recover_original_account_tab');close_editor(t)
    t.execute({'kind':'chat','value':'/reload'});state,frame=t.observe('macro_recovery_restored',seconds=120)
    checks={'zero_macros':state.get('macros')==[0,0],'empty_action_probe':not state.get('action_probe',{}).get('kind'),
        'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt['macro_recovery_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('macro source baseline did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recon',action='store_true');p.add_argument('--targeted-controls',action='store_true')
    p.add_argument('--require-empty-guard',action='store_true')
    p.add_argument('--recover-source',type=Path);a=p.parse_args()
    if a.recon and a.recover_source:p.error('recon and recovery are distinct trials')
    t=Trial(a.output,controller='code')
    t.targeted_controls=a.targeted_controls
    t.empty_macro_guard_required=a.require_empty_guard
    selected=(lambda t:recover(t,a.recover_source)) if a.recover_source else recon if a.recon else operations
    try:native_suite(t,operations=selected);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
