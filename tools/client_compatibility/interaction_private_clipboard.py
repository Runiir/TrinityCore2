"""Read only the clipboard selection on the verified owned nested X display."""
import hashlib,select,time,threading
from contextlib import contextmanager
from Xlib import X,Xatom,display
from Xlib.protocol import event as xevent
from . import lab_runtime as lab,owned_input


@contextmanager
def marker(t):
    """Serve a unique owned fixture selection until an ordinary Copy replaces it."""
    monitor=owned_input.focus();nested=monitor['input_isolation']['display']
    if monitor['input_isolation']['actor']!=t.fixture['actor'] or nested!=t.io.initialization['display']:
        raise RuntimeError('clipboard fixture differs from the owned input display')
    connection=display.Display(nested);window=None;worker=None;stop=threading.Event();errors=[]
    raw=('TC442UI:copy_guard_'+hashlib.sha256(str(t.out).encode()).hexdigest()[:8]).encode()
    try:
        selection=connection.intern_atom('CLIPBOARD');targets=connection.intern_atom('TARGETS')
        formats=[connection.intern_atom(name) for name in ['UTF8_STRING','STRING','TEXT']]
        window=connection.screen().root.create_window(0,0,1,1,0,X.CopyFromParent,X.InputOnly,X.CopyFromParent)
        window.set_selection_owner(selection,X.CurrentTime);connection.sync()
        owner=connection.get_selection_owner(selection)
        if not hasattr(owner,'id') or owner.id!=window.id:raise RuntimeError('private clipboard guard did not acquire selection')
        def serve():
            try:
                while not stop.is_set():
                    if not connection.pending_events():select.select([connection.fileno()],[],[],.05);continue
                    request=connection.next_event()
                    if request.type!=X.SelectionRequest:continue
                    prop=request.property or request.target;accepted=request.selection==selection
                    receiver=connection.create_resource_object('window',request.requestor.id)
                    if accepted and request.target==targets:
                        receiver.change_property(prop,Xatom.ATOM,32,[targets,*formats])
                    elif accepted and request.target in formats:
                        receiver.change_property(prop,request.target,8,raw)
                    else:prop=X.NONE
                    receiver.send_event(xevent.SelectionNotify(time=request.time,requestor=receiver,
                        selection=request.selection,target=request.target,property=prop),propagate=False)
                    connection.flush()
            except Exception as error:errors.append(f'{type(error).__name__}: {error}')
        worker=threading.Thread(target=serve,name='owned-clipboard-fixture',daemon=True);worker.start()
        yield {'display':nested,'owner_window':window.id,'marker':raw.decode(),'sha256':hashlib.sha256(raw).hexdigest(),'provider_errors':errors,
            'monitor':monitor,'scope':'Private nested selection only; original clipboard text is never read.'}
        if errors:raise RuntimeError('owned clipboard fixture provider failed: '+','.join(errors))
    finally:
        stop.set()
        if worker is not None:worker.join(timeout=1)
        if window is not None:window.destroy()
        connection.close()


def self_check(out):
    """Component-only selection roundtrip; sends no game keyboard/mouse input."""
    import json,subprocess
    from types import SimpleNamespace
    from . import actors
    from .interaction_social import actor
    out=out.resolve()
    if not out.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires a private evidence output')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    result={'schema':'client442_private_clipboard_self_check_v1','completed':False,'failure':None,
        'started_at':time.time(),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'gameplay_input_sent':False,'qualification':'Component check only; no game Copy qualification.'}
    with actor('primary'):
        t=SimpleNamespace(out=out,fixture=actors.load(),io=SimpleNamespace(initialization={'display':lab.client_environment()['DISPLAY']}))
        try:
            with marker(t) as fixture:
                result['fixture']=fixture;probe=copied_name(t,{fixture['marker']});result['probe']=probe
                if not probe['exact_owned_name'] or probe['owner_window']!=fixture['owner_window']:
                    raise RuntimeError('owned marker roundtrip differs')
            result['completed']=True
        except Exception as error:result['failure']=f'{type(error).__name__}: {error}'
        finally:
            result['finished_at']=time.time();lab.private_write(out/'self_check.json',json.dumps(result,indent=2)+'\n')
            print(json.dumps({k:result[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--self-check',type=Path,required=True)
    self_check(parser.parse_args().self_check)


def copied_name(t,expected,previous_owner=None):
    monitor=owned_input.focus();nested=monitor['input_isolation']['display']
    if monitor['input_isolation']['actor']!=t.fixture['actor'] or nested!=t.io.initialization['display']:
        raise RuntimeError('clipboard display differs from the owned input display')
    connection=display.Display(nested);window=None
    try:
        atom=connection.intern_atom('CLIPBOARD',only_if_exists=True)
        owner=connection.get_selection_owner(atom) if atom else None
        if not owner or not hasattr(owner,'id'):raise RuntimeError('owned nested clipboard has no owner')
        pid=owner.get_full_property(connection.intern_atom('_NET_WM_PID'),X.AnyPropertyType)
        metadata={'display':nested,'owner_window':owner.id,'owner_pid':int(pid.value[0]) if pid is not None and len(pid.value)==1 else None,
            'owner_class':owner.get_wm_class(),'monitor':monitor,'owned_guard_replaced':previous_owner is not None and owner.id!=previous_owner}
        if previous_owner is not None and owner.id==previous_owner:
            return {**metadata,'exact_owned_name':False,'value':None,'length':None,'sha256':None}
        target=connection.intern_atom('UTF8_STRING');prop=connection.intern_atom('TC442_OWNED_COPY')
        window=connection.screen().root.create_window(0,0,1,1,0,X.CopyFromParent,X.InputOnly,X.CopyFromParent)
        window.convert_selection(atom,target,prop,X.CurrentTime);connection.flush();deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if not connection.pending_events():
                select.select([connection.fileno()],[],[],min(.1,max(0,deadline-time.monotonic())));continue
            event=connection.next_event()
            if event.type!=X.SelectionNotify:continue
            if event.selection!=atom or event.target!=target or event.property!=prop:
                raise RuntimeError('nested clipboard UTF8 conversion differs')
            data=window.get_full_property(prop,X.AnyPropertyType,sizehint=1024)
            if data is None or data.format!=8 or data.property_type!=target or len(data.value)>4096:
                raise RuntimeError('nested clipboard text exceeds the bounded UTF8 contract')
            raw=bytes(data.value);current=connection.get_selection_owner(atom)
            if not hasattr(current,'id') or current.id!=owner.id:raise RuntimeError('nested clipboard owner changed during read')
            exact=raw.decode('utf-8') in expected
            metadata.update(exact_owned_name=exact,length=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                value=raw.decode('utf-8') if exact else None)
            return metadata
        raise RuntimeError('nested clipboard UTF8 conversion timed out')
    finally:
        if window is not None:window.destroy()
        connection.close()
