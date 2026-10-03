"""Wait for a requested read-only diagnostic page without resending input."""
import time
from PIL import Image
from .interaction_operations import command
from .interaction_bridge_deploy import shot
from .observation.interactions import decode_image


def read_page(t,label,mode,text,ready=None):
    command(t,text);deadline=time.monotonic()+12;pending=[];path=t.out/(label+'.png')
    while True:
        frame=shot(path)
        with Image.open(path) as image:state=decode_image(image)
        if state.get('guid')!=t.guid:raise RuntimeError('diagnostic page belongs to another actor')
        if state.get('mode')==mode and (ready is None or ready(state)):
            if pending:
                t.receipt.setdefault('observation_settling',[]).append({'label':label,
                    'samples':pending,'input_replayed':False});t.persist()
            return state,frame
        pending.append({'sequence':state['sequence'],'mode':state.get('mode')})
        if time.monotonic()>deadline:raise RuntimeError(mode+' diagnostic did not become visible')
        time.sleep(.2)
