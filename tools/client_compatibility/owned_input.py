"""Focus only this lab's verified game window before physical input."""
import os
import time
import fcntl
from contextlib import contextmanager
import threading
from . import lab_runtime as lab

INPUT_LOCK=threading.RLock()
LEASE_STATE=threading.local()


@contextmanager
def lease(timeout=10):
    """Serialize focus and one bounded physical primitive across actor processes."""
    with INPUT_LOCK:
        # Public focus also takes the lease. Reuse this thread's existing flock.
        if getattr(LEASE_STATE,'owner_pid',None)==os.getpid() and getattr(LEASE_STATE,'depth',0):
            LEASE_STATE.depth+=1
            try:yield
            finally:LEASE_STATE.depth-=1
            return
        path=lab.ROOT/'run/client_input.lock';path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with path.open('a') as handle:
            os.chmod(path,0o600);deadline=time.monotonic()+timeout
            while True:
                try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>deadline:raise RuntimeError('owned input lease timed out')
                    time.sleep(.025)
            LEASE_STATE.owner_pid=os.getpid();LEASE_STATE.depth=1
            try:yield
            finally:
                LEASE_STATE.depth=0
                fcntl.flock(handle,fcntl.LOCK_UN)


class Inputs:
    def __init__(self):
        from tools.second_client import ctl
        ctl._launcher_env=lab.client_environment
        self.raw=ctl.Input()

    def invoke(self,name,*args,**kwargs):
        with lease():
            focus()
            return getattr(self.raw,name)(*args,**kwargs)

    def key(self,*args,**kwargs):
        # Non-text keys must span more than one 15-FPS background-client tick.
        kwargs.setdefault('hold',.15)
        return self.invoke('key',*args,**kwargs)
    def click(self,*args,modifiers=(),**kwargs):
        # Match key timing: a 50 ms tap can fall between 15-FPS client ticks.
        kwargs.setdefault('hold',.15)
        if not modifiers:return self.invoke('click',*args,**kwargs)
        if len(modifiers)>3 or len(set(modifiers))!=len(modifiers) or any(m not in ['shift','ctrl','alt'] for m in modifiers):
            raise ValueError('unsupported mouse modifier')
        with lease():
            focus();pressed=[]
            try:
                for name in modifiers:
                    code=self.raw._keycode(self.raw.XK.string_to_keysym(self.raw.MODIFIERS[name]))[0]
                    self.raw._send(self.raw.X.KeyPress,code);pressed.append(code)
                time.sleep(.15);kwargs.setdefault('hold',.15);self.raw.click(*args,**kwargs)
            finally:
                for code in reversed(pressed):self.raw._send(self.raw.X.KeyRelease,code)
    def move(self,*args,**kwargs):return self.invoke('move',*args,**kwargs)
    def type(self,*args,**kwargs):return self.invoke('type',*args,**kwargs)

    def drag(self,start,end,button=1,duration=.5):
        if button not in [1,3] or not .2<=duration<=2 or any(
            not 0<=x<1280 or not 0<=y<720 for x,y in [start,end]):
            raise ValueError('drag exceeds the owned client input bounds')
        with lease():
            focus();self.raw.move(*start);time.sleep(.1)
            self.raw._send(self.raw.X.ButtonPress,button)
            try:
                for i in range(1,11):
                    self.raw.move(round(start[0]+(end[0]-start[0])*i/10),round(start[1]+(end[1]-start[1])*i/10))
                    time.sleep(duration/10)
            finally:self.raw._send(self.raw.X.ButtonRelease,button)


def focus():
    with lease():return _focus()


def _focus():
    from Xlib import X, display
    from Xlib.protocol import event
    from tools.second_client.place_window import place
    client=lab.owned_process('client')
    if not client:raise RuntimeError('owned game client is absent')
    monitor=place(client['pid'])
    if monitor['monitor']['name']!='HDMI-1':raise RuntimeError('game is not on HDMI-1')
    screen=display.Display(os.environ.get('DISPLAY',':0'))
    try:
        root=screen.screen().root;window=screen.create_resource_object('window',monitor['window_id'])
        atom=screen.intern_atom('_NET_ACTIVE_WINDOW')
        active=root.get_full_property(atom,X.AnyPropertyType)
        if active is not None and len(active.value) and int(active.value[0])==window.id:
            return monitor
        root.send_event(event.ClientMessage(window=window,client_type=atom,
            data=(32,[2,X.CurrentTime,0,0,0])),
            event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
        screen.flush()
        for _ in range(20):
            active=root.get_full_property(atom,X.AnyPropertyType)
            if active is not None and len(active.value) and int(active.value[0])==window.id:
                time.sleep(.15) # Let the nested SDL/Wine focus event settle before keys.
                return monitor
            time.sleep(.05)
        raise RuntimeError('owned game window did not acquire focus')
    finally:screen.close()
