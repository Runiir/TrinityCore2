"""Retain a fresh public page for one uniquely identified visible control."""
import json,time
from contextlib import redirect_stdout
from io import StringIO
from PIL import Image
from tools.second_client import ctl
from .observation.interactions import decode_image
from .interaction_operations import point,retain_control_pixels


def target(t,label,predicate):
    deadline=time.monotonic()+40;path=t.out/'target_latest.png'
    while time.monotonic()<deadline:
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        with Image.open(path) as image:state=decode_image(image)
        if state.get('guid')!=t.guid:raise RuntimeError('target control page belongs to another actor')
        if state.get('mode')=='controls':
            matches=[c for c in state.get('controls') or [] if predicate(c)]
            if len(matches)>1:raise RuntimeError('target predicate is ambiguous on its observed page')
            if matches:
                rows=t.receipt.setdefault('target_control_pages',[])
                saved=t.out/('target_'+str(len(rows))+'.png')
                frame=retain_control_pixels(path,saved,state)
                rows.append({'label':label,'control':matches[0],'sequence':state['sequence'],
                    'control_snapshot':state.get('control_snapshot'),'page':state['page'],'frame':frame})
                t.persist();return matches[0]
        time.sleep(.1)
    raise RuntimeError('fresh target control was not observed: '+label)


def click(t,label,goal,predicate,oracle):
    control=target(t,label,predicate)
    if not control.get('enabled') or control['kind'] not in ('Button','CheckButton'):
        raise RuntimeError('target is not an enabled ordinary button')
    return t.step(label,goal,{'click':{'kind':'click','value':point(control),
        'description':'Click the observed '+(control['name'] or control['text'] or 'stock button')+'.'}},
        lambda b,a,s:oracle(b,a,s=='click'),diagnostic_action='click')


def edit(t,label,goal,predicate,value):
    field=target(t,label,lambda c:c['kind']=='EditBox' and c.get('enabled') and predicate(c))
    def matches(state):
        return any(c.get('text')==value and point(c)==point(field) for c in state.get('edit_fields') or [])
    return t.step(label,goal,{'edit':{'kind':'edit','point':point(field),'value':value,
        'description':'Enter '+json.dumps(value)+' in the observed stock field.'}},
        lambda b,a,s:{'status':'ui_edit_pass' if s=='edit' and matches(a) else 'client_or_protocol_failure',
            'oracle':{'exact_visible_field_value':matches(a)}},diagnostic_action='edit',await_state=matches)
