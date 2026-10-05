"""Wait for a requested read-only diagnostic page without resending input."""
import time,shutil
from PIL import Image
from .interaction_operations import command
from .interaction_bridge_deploy import shot
from .observation.interactions import decode_image
from . import lab_runtime as lab,owned_input


def retain_decode_skip(t,label,path,error,frame=None):
    records=t.receipt.setdefault('observation_decode_skips',[])
    row=next((r for r in records if r['label']==label and r['error']==str(error)),None)
    if row is None:
        saved=t.out/('decode_skip_'+str(len(records))+'.png');shutil.copyfile(path,saved)
        retained=dict(frame) if frame is not None else {'monitor':owned_input.focus()}
        retained.update(file=saved.name,sha256=lab.sha256(saved))
        row={'label':label,'error':str(error),'count':0,'frame':retained,'input_replayed':False};records.append(row)
    row['count']+=1;t.persist()


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
        try:
            with Image.open(path) as image:state=decode_image(image)
        except ValueError as error:
            retain_decode_skip(t,label,path,error,frame)
            if time.monotonic()>deadline:raise RuntimeError(mode+' diagnostic did not become decodable') from error
            time.sleep(.2);continue
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
