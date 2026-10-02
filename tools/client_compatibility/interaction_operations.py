"""Model-selected visible controls for reversible player UI operations."""
import argparse
import json
from pathlib import Path
import time
from contextlib import redirect_stdout
from io import StringIO
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
    pages={};total=None;deadline=time.monotonic()+25;panels=None
    while time.monotonic()<deadline:
        path=trial.out/'controls_latest.png'
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        state=decode_image(Image.open(path))
        if state['guid']!=trial.guid:raise RuntimeError('control page identity mismatch')
        if state['mode']!='controls':continue
        current=state.get('panels') or []
        if panels is None:panels=current
        if current!=panels:raise RuntimeError('panels changed during control observation')
        total=state['control_count'];page=state['page']
        if page not in pages:
            pages[page]=state.get('controls') or []
            target=trial.out/f'controls_{len(trial.receipt["cases"]):03}_{page:02}_{state["sequence"]}.png'
            path.replace(target)
        if total is not None and len(pages)==__import__('math').ceil(total/18):
            return [c for p in sorted(pages) for c in pages[p]]
        time.sleep(.1)
    raise RuntimeError('automatic control observation page deadline exceeded')


def click_case(trial,case_id,goal,target,oracle,additional=None):
    rows=controls(trial)
    candidates=[c for c in rows if c['enabled'] and c['kind'] in ['Button','CheckButton'] and
        (target(c) or c['text'] in ['Cancel','Okay','New','Save','General Macros','Character-Specific Macros','Spellbook','Professions','Alchemy','Tailoring','Cooking','First Aid','Archaeology'])]
    selected=next((c for c in candidates if target(c)),None)
    if not selected:raise RuntimeError(f'{case_id}: expected control is absent')
    other=[c for c in candidates if c is not selected]
    # Add normal panel bindings as alternatives if a dialog exposes few buttons.
    offered=[selected]+trial.rng.sample(other,min(3,len(other)))
    trial.rng.shuffle(offered);actions={};target_key=None
    for i,c in enumerate(offered):
        key='button_'+str(i)
        if c is selected:target_key=key
        actions[key]={'kind':'click','value':point(c),
            'description':f"Click visible {c['kind']} {c['text'] or c['name']}."+(' Row: '+c['context']+'.' if c.get('context') else '')}
    actions['escape']={'kind':'key','value':'Escape','description':'Press Escape to close the current dialog.'}
    if len(actions)<3:actions['spellbook']={'kind':'key','value':'p','description':'Press P to toggle the spellbook.'}
    if additional:actions.update(additional)
    return trial.step(case_id,goal,actions,lambda b,a,s:oracle(b,a,s==target_key))


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
