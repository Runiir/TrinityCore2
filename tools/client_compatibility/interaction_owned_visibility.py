"""Temporarily restore an owned minimized scout without requesting host focus."""
from contextlib import contextmanager
import time
from Xlib import X,Xutil,Xatom,display,protocol
from . import lab_runtime as lab,owned_input


def recover_hints(t,source,original_user_time):
    import json
    from pathlib import Path
    path=source.resolve();failed=json.loads(path.read_text());old=failed.get('owned_window_visibility',{})
    if (not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink() or
        failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!="AttributeError: 'Window' object has no attribute 'iconify'" or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        old.get('before_state')!=[Xutil.IconicState,0] or old.get('restored') is not False or
        original_user_time!=462620438):
        raise RuntimeError('requires the exact closed visibility failure and observed original hint time')
    monitor=owned_input.focus();screen=display.Display(':0');root=screen.screen().root
    window=screen.create_resource_object('window',monitor['window_id'])
    values=lambda object,name:list(object.get_full_property(screen.intern_atom(name),X.AnyPropertyType).value)
    try:
        hints=dict(window.get_wm_hints()._data)
        before={'flags':hints['flags'],'input':hints['input'],'user_time':values(window,'_NET_WM_USER_TIME'),
            'state':values(window,'WM_STATE'),'active':values(root,'_NET_ACTIVE_WINDOW')}
        if (monitor!=old['before_monitor'] or before!={'flags':65,'input':0,'user_time':[0],
            'state':old['before_state'],'active':old['before_active']}):
            raise RuntimeError('failed visibility hints changed; refusing recovery')
        t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},before=before,
            original_hint_authority='Separate read-only host-window inspection before this visibility attempt; input1/flags65/time462620438.',
            input_sent=False,host_activation_sent=False);t.persist()
        window.set_wm_hints(**{**hints,'input':1})
        window.change_property(screen.intern_atom('_NET_WM_USER_TIME'),Xatom.CARDINAL,32,[original_user_time]);screen.sync()
        current=window.get_wm_hints()
        checks={'input_hint':current.input==1 and current.flags==65,
            'user_time':values(window,'_NET_WM_USER_TIME')==[original_user_time],
            'minimized':values(window,'WM_STATE')==old['before_state'],
            'host_focus':values(root,'_NET_ACTIVE_WINDOW')==old['before_active'],
            'monitor_geometry':owned_input.focus()==monitor}
        t.receipt.update(checks=checks,completed=all(checks.values()),phase='owned_visibility_hints_restored')
        if not all(checks.values()):raise RuntimeError('original window hints did not restore')
    finally:screen.close()


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


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    from .interaction_social import actor
    from .interaction_trial import Trial
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--original-user-time',type=int,required=True);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:recover_hints(t,a.source,a.original_user_time)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','checks')}),flush=True)
