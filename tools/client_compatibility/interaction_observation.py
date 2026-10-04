"""Wait for a requested read-only diagnostic page without resending input."""
import time
from PIL import Image
from .interaction_operations import command
from .interaction_bridge_deploy import shot
from .observation.interactions import decode_image


def read_page(t,label,mode,text,ready=None):
    command(t,text)
    return read_current_page(t,label,mode,ready)


def read_current_page(t,label,mode,ready=None):
    """Read a selected or automatically cycled page without sending any input."""
    deadline=time.monotonic()+28;pending=[];path=t.out/(label+'.png')
    suffix=1
    while path.exists():
        path=t.out/(label+'_'+str(suffix)+'.png');suffix+=1
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
        if time.monotonic()>deadline:
            t.receipt.setdefault('diagnostic_timeouts',[]).append({'label':label,'mode':mode,
                'samples':pending[-64:],'last_frame':frame,'input_replayed':False})
            t.persist();raise RuntimeError(mode+' diagnostic did not become visible')
        # Avoid repeatedly sampling the same phase of the passive page cycle.
        time.sleep(.13+(len(pending)%7)*.027)
