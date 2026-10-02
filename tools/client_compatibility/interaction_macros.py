"""Reversible macro lifecycle using Laya-selected physical UI inputs."""
import argparse
import json
from pathlib import Path
import time
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case

NAME='TC442Test'
BODY='/cast Battle Shout'


def body_matches(state):
    macro=state.get('test_macro') or []
    return len(macro)>=3 and macro[0]==NAME and macro[2].rstrip('\r\n')==BODY


def edit_case(trial,case_id,goal,predicate,value):
    rows=controls(trial)
    field=next((c for c in rows if c['kind']=='EditBox' and c['enabled'] and predicate(c)),None)
    if field is None:raise RuntimeError('expected editable field is absent: '+case_id)
    actions={'field':{'kind':'edit','point':point(field),'value':value,
        'description':f'Type {value!r} into the visible text field {field["name"] or "in this dialog"}.'},
        'escape':{'kind':'key','value':'Escape','description':'Close the dialog with Escape.'},
        'tab':{'kind':'key','value':'Tab','description':'Move focus to the next control with Tab.'}}
    def oracle(before,after,selected):
        observed=controls(trial)
        matches=[c for c in observed if c['kind']=='EditBox' and predicate(c)]
        entered=any(c['text']==value for c in matches)
        return {'status':'ui_edit_pass' if entered else ('controller_failure' if selected!='field' else 'client_or_protocol_failure'),
            'oracle':{'field_value_matches':entered,'qualified_scope':'visible edit field'}}
    return trial.step(case_id,goal,actions,oracle,diagnostic_action='field')


def require(row,status):
    if row['status']!=status:raise RuntimeError('operation did not advance: '+row['id']+' '+row['status'])


def suite(trial):
    trial.clean_panels()
    initial,_=trial.observe('macro_fixture')
    if initial.get('test_macro') or initial.get('macros')!=[0,0]:
        raise RuntimeError('macro trial requires its empty disposable account fixture')
    row=trial.step('macros.open','Open the macro editor.',{
        'a':{'kind':'chat','value':'/macro','description':'Type /macro to open the macro editor.'},
        'b':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'c':{'kind':'key','value':'o','description':'Press O to open friends.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'MacroFrame' in a['panels'] else 'controller_failure'})
    require(row,'panel_open_pass')
    row=click_case(trial,'macros.create_dialog','Create a new macro.',lambda c:c['name']=='MacroNewButton',
        lambda b,a,s:{'status':'panel_open_pass' if 'MacroPopupFrame' in a['panels'] else 'controller_failure'})
    require(row,'panel_open_pass')
    require(edit_case(trial,'macros.name','Name the new macro '+NAME+'.',lambda c:not c['name'],NAME),'ui_edit_pass')
    require(click_case(trial,'macros.create','Confirm the new macro name.',lambda c:c['text']=='Okay',
        lambda b,a,s:{'status':'macro_create_pass' if (a.get('test_macro') or [None])[0]==NAME else ('controller_failure' if not s else 'client_or_protocol_failure')}),'macro_create_pass')
    require(edit_case(trial,'macros.body','Set the macro commands to '+BODY+'.',lambda c:c['name']=='MacroFrameText',BODY),'ui_edit_pass')
    require(click_case(trial,'macros.save','Save the edited macro commands.',lambda c:c['name']=='MacroSaveButton',
        lambda b,a,s:{'status':'macro_save_pass' if body_matches(a) else ('controller_failure' if not s else 'client_or_protocol_failure')}),'macro_save_pass')
    trial.clean_panels()
    require(trial.step('macros.reload','Reload the interface to check that the saved macro survives.',{
        'a':{'kind':'chat','value':'/reload','description':'Type /reload to reload the interface.'},
        'b':{'kind':'chat','value':'/macro','description':'Type /macro to open the macro editor.'},
        'c':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'}},
        lambda b,a,s:{'status':'macro_reload_pass' if s=='a' and body_matches(a) else ('controller_failure' if s!='a' else 'client_or_protocol_failure'),
            'oracle':{'macro_body_matches':body_matches(a),'normalization':'ignore trailing CR/LF only'}}),'macro_reload_pass')
    cleanup(trial)


def cleanup(trial):
    # Delete the disposable fixture via ordinary controls. This is cleanup, not model qualification.
    trial.execute({'kind':'chat','value':'/macro'})
    rows=controls(trial);button=next(c for c in rows if c['name']=='MacroDeleteButton')
    trial.execute({'kind':'click','value':point(button)})
    rows=controls(trial);button=next(c for c in rows if c['name']=='StaticPopup1Button1' and c['text']=='Okay')
    trial.execute({'kind':'click','value':point(button)})
    state,_=trial.observe('deleted_macro')
    if state.get('macros')!=[0,0]:raise RuntimeError('macro cleanup failed')
    trial.receipt['cleanup'].append({'time':time.time(),'source':'code_fixture_cleanup','deleted_macro':NAME,'macros_after':state['macros']})
    trial.clean_panels()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist()
        print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
