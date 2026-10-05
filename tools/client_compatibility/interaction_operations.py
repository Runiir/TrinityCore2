"""Model-selected visible controls for reversible player UI operations."""
import argparse
import hashlib
import json
import math
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
    trial.submit_chat(text,any_mode=True)
    time.sleep(.65)


def retain_control_pixels(path,target,state):
    # Only catalog plumbing uses this lossless region. Action/cleanup frames
    # retain the complete game image for rendering and coordinate review.
    from PIL import Image
    from .observation.interactions import decode_image
    with Image.open(path) as full:
        if full.size!=(1280,720):raise RuntimeError('control capture viewport changed')
        # Retain the encoded rows actually used, including expanded packets.
        rgb=full.convert('RGB')
        header=bytes(rgb.getpixel((282,16)))+bytes(rgb.getpixel((285,16)))
        length=int.from_bytes(header[4:6],'big')
        rows=math.ceil((length+12)/(3*128))
        box=(281,15,642,15+math.ceil(rows*2.8125))
        pixels=full.crop(box)
        if decode_image(pixels,x=.25,y=0)!=state:
            raise RuntimeError('retained control pixels differ from the full capture')
        pixels.save(target,compress_level=9)
    path.unlink()
    return {'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'capture_box':list(box),'capture_dimensions':[1280,720],
        'content':'lossless public control-observation pixels; action frames retain full game rendering'}


def controls(trial):
    from .interaction_observation import retain_decode_skip
    from PIL import Image
    from tools.second_client import ctl
    from .observation.interactions import decode_image
    pages={};total=None;deadline=time.monotonic()+40;panels=None;revision=None
    while time.monotonic()<deadline:
        path=trial.out/'controls_latest.png'
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        try:state=decode_image(Image.open(path))
        except ValueError as error:
            retain_decode_skip(trial,'controls_catalog',path,error);time.sleep(.1);continue
        if state['guid']!=trial.guid:raise RuntimeError('control page identity mismatch')
        if state['mode']!='controls':continue
        current=state.get('panels') or []
        current_revision=(tuple(current),state['control_count'],state.get('control_snapshot'))
        cached=getattr(trial,'control_catalog',None)
        if state.get('control_snapshot') is not None and cached and cached['revision']==current_revision:
            # The observer fingerprints the complete current list before paging.
            # Reuse only an exact list from this Trial/actor, retaining the new
            # frame that establishes the matching current fingerprint.
            reused=trial.receipt.setdefault('control_catalog_reuse',[])
            target=trial.out/('controls_reuse_'+str(len(reused))+'.png')
            frame=retain_control_pixels(path,target,state)
            reused.append({'frame':frame,
                'sequence':state['sequence'],'control_snapshot':state['control_snapshot'],
                'control_count':state['control_count'],'source_catalog':cached['source']});trial.persist()
            return cached['rows']
        if current_revision!=revision:
            pages={};revision=current_revision
        if panels is None:panels=current
        if current!=panels:
            trial.receipt.setdefault('control_observation_transitions',[]).append({'time':time.time(),'before':panels,'after':current})
            trial.persist();pages={};panels=current
        total=state['control_count'];page=state['page']
        if not 1<=page<=__import__('math').ceil(total/state.get('page_size',18)):continue
        if page not in pages:
            pages[page]=state.get('controls') or []
            # Retain one screenshot for identical control pages within this
            # episode. Sequence pixels change even when every control is equal.
            observed={'guid':state['guid'],'panels':current,'page':page,'total':total,'controls':pages[page],
                'control_snapshot':state.get('control_snapshot')}
            digest=hashlib.sha256(json.dumps(observed,sort_keys=True).encode()).hexdigest()
            target=trial.out/('controls_'+digest+'.png')
            if target.exists():
                path.unlink();frame=trial.receipt['control_frames'][digest]
            else:frame=retain_control_pixels(path,target,state)
            trial.receipt.setdefault('control_frames',{})[digest]={**frame,'observed':observed}
            trial.persist()
        if total is not None and len(pages)==__import__('math').ceil(total/state.get('page_size',18)):
            rows=[c for p in sorted(pages) for c in pages[p]]
            trial.control_catalog={'revision':revision,'rows':rows,'source':
                {'control_snapshot':state.get('control_snapshot'),'frames':[
                    key for key,row in trial.receipt.get('control_frames',{}).items()
                    if row['observed'].get('control_snapshot')==state.get('control_snapshot')]}}
            return rows
        time.sleep(.1)
    raise RuntimeError('automatic control observation page deadline exceeded')


def click_case(trial,case_id,goal,target,oracle,additional=None,await_state=None):
    rows=controls(trial)
    candidates=[c for c in rows if c['enabled'] and c['kind'] in ['Button','CheckButton','MenuItem','ClickFrame'] and
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
    return trial.step(case_id,goal,actions,lambda b,a,s:oracle(b,a,s==target_key),diagnostic_action=target_key,
        await_state=await_state)


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
