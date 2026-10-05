"""Read only the clipboard selection on the verified owned nested X display."""
import hashlib,select,time
from Xlib import X,display
from . import lab_runtime as lab,owned_input


def copied_name(t,expected):
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
            'owner_class':owner.get_wm_class(),'monitor':monitor}
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
