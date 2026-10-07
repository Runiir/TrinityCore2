"""Temporarily restore an owned minimized scout without requesting host focus."""
from contextlib import contextmanager
import time
from Xlib import X,Xutil,Xatom,display,protocol
from . import lab_runtime as lab,owned_input


@contextmanager
def visible_scout(t):
    if lab.actor_name()!='scout':raise RuntimeError('visibility scope is restricted to the owned scout')
    mem={k:int(v.split()[0])*1024 for k,v in
        (line.split(':',1) for line in __import__('pathlib').Path('/proc/meminfo').read_text().splitlines())}
    if mem['MemAvailable']<6*1024**3:raise RuntimeError('insufficient memory for restoring the existing scout window')
    monitor=owned_input.focus();screen=display.Display(':0');root=screen.screen().root
    window=screen.create_resource_object('window',monitor['window_id'])
    prop=lambda object,name:object.get_full_property(screen.intern_atom(name),X.AnyPropertyType)
    values=lambda object,name:list(prop(object,name).value) if prop(object,name) is not None else None
    active=values(root,'_NET_ACTIVE_WINDOW');state=values(window,'WM_STATE')
    user=values(window,'_NET_WM_USER_TIME');hints=window.get_wm_hints()
    pid=values(window,'_NET_WM_PID');runtime=lab.owned_process('client')
    if (pid!=[runtime['pid']] or not hints or state!=[Xutil.IconicState,0] or
        not monitor.get('second_monitor_verified') or monitor['monitor']['name']!='HDMI-1'):
        screen.close();raise RuntimeError('requires the verified owned minimized scout on HDMI-1')
    previous=dict(hints._data);row={'before_monitor':monitor,'before_state':state,'before_active':active,
        'before_input_hint':previous['input'],'before_hint_flags':previous['flags'],'before_user_time':user,
        'memory_available_before':mem['MemAvailable'],'host_activation_sent':False,'host_input_sent':False,
        'client_restarted':False,'restored':False}
    t.receipt['owned_window_visibility']=row;t.persist()
    def wait_state(expected):
        deadline=time.monotonic()+4
        while values(window,'WM_STATE')!=expected:
            if time.monotonic()>=deadline:raise RuntimeError('owned window visibility transition did not settle')
            time.sleep(.1)
    try:
        # ICCCM InputHint and zero user time decline focus on mapping. No
        # _NET_ACTIVE_WINDOW request or host input is sent at any point.
        window.set_wm_hints(**{**previous,'flags':previous['flags']|Xutil.InputHint,'input':0})
        window.change_property(screen.intern_atom('_NET_WM_USER_TIME'),Xatom.CARDINAL,32,[0])
        window.map();screen.sync();wait_state([Xutil.NormalState,0])
        row.update(visible_monitor=owned_input.focus(),visible_active=values(root,'_NET_ACTIVE_WINDOW'))
        if row['visible_active']!=active:raise RuntimeError('desktop focus changed; refusing game input')
        if row['visible_monitor']['window']!=monitor['window']:
            raise RuntimeError('owned scout window geometry changed; refusing game input')
        t.persist();yield
    finally:
        try:
            if values(window,'WM_STATE')!=state:
                root.send_event(protocol.event.ClientMessage(window=window.id,
                    client_type=screen.intern_atom('WM_CHANGE_STATE'),data=(32,[Xutil.IconicState,0,0,0,0])),
                    event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
                screen.sync()
            wait_state(state)
            row.update(after_state=values(window,'WM_STATE'),after_active=values(root,'_NET_ACTIVE_WINDOW'),
                after_monitor=owned_input.focus())
            row['restored']=(row['after_state']==state and row['after_active']==active and
                row['after_monitor']['window']==monitor['window'] and
                lab.owned_process('client')['start_ticks']==runtime['start_ticks'])
        finally:
            window.set_wm_hints(**previous)
            if user is None:window.delete_property(screen.intern_atom('_NET_WM_USER_TIME'))
            else:window.change_property(screen.intern_atom('_NET_WM_USER_TIME'),Xatom.CARDINAL,32,user)
            screen.sync();screen.close();t.persist()
        if not row['restored']:raise RuntimeError('owned scout visibility or desktop focus did not restore')
