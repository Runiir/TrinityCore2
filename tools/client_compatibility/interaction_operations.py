"""Model-selected visible controls for reversible player UI operations."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .interaction_trial import Trial


def point(control):
    return [round(control['x']/65535*1280),round(control['y']/65535*720)]


def command(trial,text):
    # Observer plumbing only; never invokes a Blizzard gameplay API.
    trial.io.key('Return');trial.io.type(text);trial.io.key('Return');time.sleep(.65)


def controls(trial):
    from PIL import Image
    from tools.second_client import ctl
    from .observation.interactions import decode_image
    records=[];page=1;total=None
    try:
        while total is None or len(records)<total:
            command(trial,'/tcui controls '+str(page));path=trial.out/f'controls_{len(trial.receipt["cases"]):03}_{page:02}.png'
            ctl.shot(str(path));state=decode_image(Image.open(path));total=state['control_count']
            if state['guid']!=trial.guid or state['page']!=page:raise RuntimeError('control page identity mismatch')
            records.extend(state.get('controls') or []);page+=1
            if page>30:raise RuntimeError('control page budget exhausted')
        return records
    finally:command(trial,'/tcui state')


def click_case(trial,case_id,goal,target,oracle,additional=None):
    rows=controls(trial)
    candidates=[c for c in rows if c['enabled'] and c['kind'] in ['Button','CheckButton'] and
        (target(c) or c['text'] in ['Cancel','Okay','New','Save','General Macros','Character-Specific Macros','Spellbook','Professions','Alchemy','Tailoring','Cooking','First Aid','Archaeology'])]
    selected=next((c for c in candidates if target(c)),None)
    if not selected:raise RuntimeError(f'{case_id}: expected control is absent')
    other=[c for c in candidates if c is not selected]
    # Add normal panel bindings as alternatives if a dialog exposes few buttons.
    actions={'control_target':{'kind':'click','value':point(selected),
        'description':f"Click visible {selected['kind']} {selected['text'] or selected['name']}."}}
    for i,c in enumerate(trial.rng.sample(other,min(3,len(other)))):
        actions['control_'+str(i)]={'kind':'click','value':point(c),
            'description':f"Click visible {c['kind']} {c['text'] or c['name']}."}
    actions['escape']={'kind':'key','value':'Escape','description':'Press Escape to close the current dialog.'}
    if len(actions)<3:actions['spellbook']={'kind':'key','value':'p','description':'Press P to toggle the spellbook.'}
    if additional:actions.update(additional)
    return trial.step(case_id,goal,actions,lambda b,a,s:oracle(b,a,s=='control_target'))


def profession_suite(trial):
    for case_id,label in [('primary_one','Alchemy'),('primary_two','Tailoring'),('cooking','Cooking'),('first_aid','First Aid'),('archaeology','Archaeology')]:
        trial.clean_panels()
        trial.step('professions.open.'+case_id,'Open professions and skills.',{
            'skills':{'kind':'key','value':'k','description':'Press K to open the professions and skills spellbook.'},
            'map':{'kind':'key','value':'m','description':'Press M to open the world map.'},
            'character':{'kind':'key','value':'c','description':'Press C to open equipment.'},
            'friends':{'kind':'key','value':'o','description':'Press O to open friends.'}},
            lambda b,a,s:{'status':'panel_open_pass' if 'SpellBookFrame' in a['panels'] else 'controller_failure'})
        result=click_case(trial,'professions.'+case_id,'Open '+label+'.',lambda c:c['text']==label,
            lambda b,a,correct:{'status':('profession_recipe_pass' if a.get('recipe_count',0)>0 and a.get('trade_skill',[None])[0]==label else 'client_or_protocol_failure') if correct else 'controller_failure',
                'oracle':{'trade_skill':a.get('trade_skill'),'recipe_count':a.get('recipe_count'),'panels':a['panels']}} if label!='Archaeology' else {
                'status':'panel_open_pass' if 'ArchaeologyFrame' in a['panels'] else ('client_or_protocol_failure' if correct else 'controller_failure'),
                'oracle':{'qualified_scope':'archaeology panel only','panels':a['panels']}})
        print(json.dumps({'profession':label,'result':result['status']}),flush=True)
    trial.clean_panels()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();trial=Trial(a.output)
    try:profession_suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
