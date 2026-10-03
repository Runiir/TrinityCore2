"""Reversible macro lifecycle using Laya-selected physical UI inputs."""
import argparse
import json
from pathlib import Path
import time
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case
from . import actors,lab_runtime as lab
from .observation.journal import entries
from .world.buffer import Reader
from .world.native_objects import guid as native_guid

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
    return trial.step(case_id,goal,actions,oracle,diagnostic_action='field',
        await_state=lambda state:any(c.get('text')==value and
            [round(c['x']/65535*1280),round(c['y']/65535*720)]==point(field)
            for c in state.get('edit_fields') or []))


def require(row,status):
    if row['status']!=status:raise RuntimeError('operation did not advance: '+row['id']+' '+row['status'])


def suite(trial):
    trial.clean_panels()
    initial,_=trial.observe('macro_fixture')
    if initial.get('test_macro') or initial.get('macros')!=[0,0] or initial.get('action_probe',{}).get('kind'):
        raise RuntimeError('macro trial requires its empty disposable account fixture')
    trial.receipt['macro_fixture']=initial;trial.persist()
    row=trial.step('macros.open','Open the macro editor.',{
        'a':{'kind':'chat','value':'/macro','description':'Type /macro to open the macro editor.'},
        'b':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'c':{'kind':'key','value':'o','description':'Press O to open friends.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'MacroFrame' in a['panels'] else 'controller_failure'},diagnostic_action='a')
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
    rows=controls(trial);source=next(c for c in rows if c['name']=='MacroFrameSelectedMacroButton')
    state,_=trial.observe('macro_bar_fixture');p=state['action_probe']['point'];destination=[round(p[0]/65535*1280),round(p[1]/65535*720)]
    require(trial.step('macros.drag_to_bar','Drag the selected test macro onto the empty last action button.',{
        'drag':{'kind':'drag','start':point(source),'end':destination,'description':'Drag the selected macro icon onto the empty last action-bar button.'},
        'escape':{'kind':'key','value':'Escape','description':'Close the macro editor.'},
        'click':{'kind':'click','value':point(source),'description':'Click the selected macro icon without dragging it.'}},
        lambda b,a,s:{'status':'macro_bar_pass' if a['action_probe'].get('kind')=='macro' and a['action_probe'].get('macro')==NAME else
            ('controller_failure' if s!='drag' else 'client_or_protocol_failure')},diagnostic_action='drag'),'macro_bar_pass')
    trial.clean_panels()
    require(trial.step('macros.reload','Reload the interface to check that the saved macro survives.',{
        'a':{'kind':'chat','value':'/reload','description':'Type /reload to reload the interface.'},
        'b':{'kind':'chat','value':'/macro','description':'Type /macro to open the macro editor.'},
        'c':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'}},
        lambda b,a,s:{'status':'macro_reload_pass' if s=='a' and body_matches(a) else ('controller_failure' if s!='a' else 'client_or_protocol_failure'),
            'oracle':{'macro_body_matches':body_matches(a),'normalization':'ignore trailing CR/LF only'}},diagnostic_action='a'),'macro_reload_pass')
    session=actors.session_entry(trial.fixture)['session'];since=time.time()
    require(trial.step('macros.execute','Click the test macro action button to cast Battle Shout.',{
        'cast':{'kind':'click','value':destination,'description':'Click the action-bar button containing TC442Test to cast Battle Shout.'},
        'spellbook':{'kind':'key','value':'p','description':'Open the spellbook.'},
        'character':{'kind':'key','value':'c','description':'Open equipment.'}},
        lambda b,a,s:cast_oracle(trial,session,since,s),diagnostic_action='cast'),'macro_execute_pass')
    cleanup(trial)


def cast_oracle(trial,session,since,selected):
    completions=[];failures=[]
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if row.get('session')!=session or row.get('time',0)<since or row.get('direction')!='from_native':continue
        if row.get('name')=='SMSG_SPELL_GO':
            r=Reader(bytes.fromhex(row['body']));caster=native_guid(r);native_guid(r);counter,spell=r.unpack('Bi')
            if caster==trial.fixture['guid'] and spell==6673:completions.append({'time':row['time'],'caster':caster,'spell':spell,'counter':counter})
        elif row.get('name')=='SMSG_CAST_FAILED':failures.append(row)
    return {'status':'macro_execute_pass' if selected=='cast' and completions and not failures else
        ('controller_failure' if selected!='cast' else 'client_or_protocol_failure'),
        'oracle':{'session':session,'native_cast_completions':completions,'native_failures':failures}}


def cleanup(trial):
    # Delete the disposable fixture via ordinary controls. This is cleanup, not model qualification.
    trial.execute({'kind':'chat','value':'/macro'})
    rows=controls(trial);button=next(c for c in rows if c['name']=='MacroDeleteButton')
    trial.execute({'kind':'click','value':point(button)})
    rows=controls(trial);button=next(c for c in rows if c['name']=='StaticPopup1Button1' and c['text']=='Okay')
    trial.execute({'kind':'click','value':point(button)})
    state,_=trial.observe('deleted_macro')
    if state.get('macros')!=[0,0] or state['action_probe'].get('kind'):raise RuntimeError('macro cleanup failed')
    trial.receipt['cleanup'].append({'time':time.time(),'source':'code_fixture_cleanup','deleted_macro':NAME,'macros_after':state['macros']})
    trial.clean_panels()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--controller',choices=['laya','code'],default='laya');a=p.parse_args()
    trial=Trial(a.output,a.controller)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        if trial.receipt.get('macro_fixture'):
            try:
                state,_=trial.observe('final_macro_check')
                if state.get('test_macro'):cleanup(trial)
            except Exception as e:trial.receipt['cleanup_failure']=str(e);trial.receipt['completed']=False
        trial.receipt['finished_at']=time.time();trial.persist()
        print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
