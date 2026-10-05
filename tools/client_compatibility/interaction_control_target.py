"""Retain a fresh public page for one uniquely identified visible control."""
import json,time,shutil
from contextlib import redirect_stdout
from io import StringIO
from PIL import Image
from tools.second_client import ctl
from .observation.interactions import decode_image
from .interaction_operations import point,retain_control_pixels
from . import lab_runtime as lab,owned_input


def target(t,label,predicate):
    from .interaction_observation import retain_decode_skip
    from .interaction_capture import retain_capture_failure
    deadline=time.monotonic()+40;path=t.out/'target_latest.png';samples=[]
    while time.monotonic()<deadline:
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        try:
            with Image.open(path) as image:loaded=image.copy()
            state=decode_image(loaded)
        except (ValueError,OSError) as error:
            if isinstance(error,OSError):retain_capture_failure(t,label,path,error)
            else:retain_decode_skip(t,label,path,error)
            time.sleep(.1);continue
        if state.get('guid')!=t.guid:raise RuntimeError('target control page belongs to another actor')
        if state.get('mode')=='controls':
            samples.append({'sequence':state['sequence'],'page':state['page'],
                'control_snapshot':state.get('control_snapshot'),'controls':state.get('controls') or []})
            samples=samples[-20:]
            matches=[c for c in state.get('controls') or [] if predicate(c)]
            if len(matches)>1:raise RuntimeError('target predicate is ambiguous on its observed page')
            if matches:
                rows=t.receipt.setdefault('target_control_pages',[])
                saved=t.out/('target_'+str(len(rows))+'.png')
                frame=retain_control_pixels(path,saved,state,loaded)
                rows.append({'label':label,'control':matches[0],'sequence':state['sequence'],
                    'control_snapshot':state.get('control_snapshot'),'page':state['page'],'frame':frame})
                t.persist();return matches[0]
        time.sleep(.1)
    rows=t.receipt.setdefault('target_control_timeouts',[]);saved=t.out/('missing_target_'+str(len(rows))+'.png')
    frame=None
    if path.exists():
        shutil.copyfile(path,saved)
        frame={'file':saved.name,'sha256':lab.sha256(saved),'monitor':owned_input.focus()}
    rows.append({'label':label,'samples':samples,'input_replayed':False,
        'frame':frame});t.persist()
    raise RuntimeError('fresh target control was not observed: '+label)


def click(t,label,goal,predicate,oracle,*,await_state=None):
    control=target(t,label,predicate)
    if not control.get('enabled') or control['kind'] not in ('Button','CheckButton'):
        raise RuntimeError('target is not an enabled ordinary button')
    return t.step(label,goal,{'click':{'kind':'click','value':point(control),
        'description':'Click the observed '+(control['name'] or control['text'] or 'stock button')+'.'}},
        lambda b,a,s:oracle(b,a,s=='click'),diagnostic_action='click',await_state=await_state)


def edit(t,label,goal,predicate,value):
    field=target(t,label,lambda c:c['kind']=='EditBox' and c.get('enabled') and predicate(c))
    def matches(state):
        return any(c.get('text')==value and point(c)==point(field) for c in state.get('edit_fields') or [])
    return t.step(label,goal,{'edit':{'kind':'edit','point':point(field),'value':value,
        'description':'Enter '+json.dumps(value)+' in the observed stock field.'}},
        lambda b,a,s:{'status':'ui_edit_pass' if s=='edit' and matches(a) else 'client_or_protocol_failure',
            'oracle':{'exact_visible_field_value':matches(a)}},diagnostic_action='edit',await_state=matches)
