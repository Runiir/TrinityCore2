"""Input on an actor's private Gamescope display without changing host focus."""
import os
from pathlib import Path
import time
import fcntl
from contextlib import contextmanager
import threading
from . import lab_runtime as lab

INPUT_LOCKS={}
LOCK_REGISTRY=threading.Lock()
LEASE_STATE=threading.local()


@contextmanager
def lease(timeout=10):
    """Serialize one actor's primitives; different actor processes can overlap."""
    name=lab.actor_name()
    with LOCK_REGISTRY:lock=INPUT_LOCKS.setdefault(name,threading.RLock())
    with lock:
        # Public focus also takes the lease. Reuse this thread's existing flock.
        if (getattr(LEASE_STATE,'owner_pid',None)==os.getpid() and getattr(LEASE_STATE,'actor',None)==name
                and getattr(LEASE_STATE,'depth',0)):
            LEASE_STATE.depth+=1
            try:yield
            finally:LEASE_STATE.depth-=1
            return
        path=lab.ROOT/('run/client_input_'+name+'.lock');path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with path.open('a') as handle:
            os.chmod(path,0o600);deadline=time.monotonic()+timeout
            while True:
                try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>deadline:raise RuntimeError('owned input lease timed out')
                    time.sleep(.025)
            LEASE_STATE.owner_pid=os.getpid();LEASE_STATE.actor=name;LEASE_STATE.depth=1
            try:yield
            finally:
                LEASE_STATE.depth=0
                fcntl.flock(handle,fcntl.LOCK_UN)


class Inputs:
    def __init__(self):
        from tools.second_client import ctl
        ctl._launcher_env=lab.client_environment
        self.actor=lab.actor_name()
        self.runtime=lab.owned_process('client')
        from .native_input_adapter import Input
        self.raw=Input()
        self.initialization=self.raw.initialization
        self.pointer_prepared=False

    def validate(self):
        current=lab.owned_process('client')
        if (lab.actor_name()!=self.actor or not current or
                (current['pid'],current['start_ticks'])!=(self.runtime['pid'],self.runtime['start_ticks'])):
            raise RuntimeError('input adapter belongs to a different actor or client lifetime')

    def prepare(self):
        self.validate();monitor=focus()
        if not self.pointer_prepared:
            pointer=self.raw.display.screen().root.query_pointer()
            self.raw._send(self.raw.X.MotionNotify,x=pointer.root_x,y=pointer.root_y)
            time.sleep(.25)
            self.pointer_prepared=True
            self.initialization['neutral_pointer_displacement']=0
        return monitor

    def invoke(self,name,*args,**kwargs):
        with lease():
            self.prepare()
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
            self.prepare();pressed=[]
            try:
                for name in modifiers:
                    code=self.raw._keycode(self.raw.XK.string_to_keysym(self.raw.MODIFIERS[name]))[0]
                    self.raw._send(self.raw.X.KeyPress,code);pressed.append(code)
                time.sleep(.15);kwargs.setdefault('hold',.15);self.raw.click(*args,**kwargs)
            finally:
                for code in reversed(pressed):self.raw._send(self.raw.X.KeyRelease,code)
    def move(self,*args,**kwargs):return self.invoke('move',*args,**kwargs)
    def type(self,*args,**kwargs):return self.invoke('type',*args,**kwargs)

    @contextmanager
    def hold_modifier(self,name):
        """Keep one private modifier down for a bounded screenshot observation."""
        if name not in ['shift','ctrl','alt']:raise ValueError('unsupported held modifier')
        with lease():
            self.prepare();code=self.raw._keycode(self.raw.XK.string_to_keysym(self.raw.MODIFIERS[name]))[0]
            keys=self.raw.display.query_keymap()
            if keys[code//8]&(1<<(code%8)):raise RuntimeError('private modifier is already held')
            started=time.monotonic();self.raw._send(self.raw.X.KeyPress,code)
            try:
                time.sleep(.15);yield
            finally:self.raw._send(self.raw.X.KeyRelease,code)
            if time.monotonic()-started>20:raise RuntimeError('held modifier exceeded its bounded observation')

    def drag(self,start,end,button=1,duration=.5):
        if type(button) is not int or button not in [1,3] or type(duration) not in (int,float) or not .2<=duration<=2 or any(
            not 0<=x<1280 or not 0<=y<720 for x,y in [start,end]):
            raise ValueError('drag exceeds the owned client input bounds')
        with lease():
            if button==3 and not getattr(self.raw,'relative_pointer',False):
                raise RuntimeError('relative pointer capability is unavailable for right-button drag')
            self.prepare();self.raw.move(*start);time.sleep(.1)
            self.raw._send(self.raw.X.ButtonPress,button)
            try:
                if button==3:time.sleep(.15)
                previous=start
                for i in range(1,11):
                    current=[round(start[0]+(end[0]-start[0])*i/10),round(start[1]+(end[1]-start[1])*i/10)]
                    if button==3:self.raw.move_relative(current[0]-previous[0],current[1]-previous[1])
                    else:self.raw.move(*current)
                    previous=current
                    time.sleep(duration/10)
                if button==3:time.sleep(.15)
            finally:self.raw._send(self.raw.X.ButtonRelease,button)


def focus():
    with lease():return _focus()


def descendant(pid,owner):
    # Wine starts a new process group for the game. Bound ownership by its
    # parent chain to the verified Gamescope supervisor, not by that group.
    for _ in range(16):
        if pid==owner:return True
        if pid<=1:return False
        try:pid=int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[1])
        except (OSError,ValueError,IndexError):return False
    return False


def _focus():
    from Xlib import X, display
    from tools.second_client.place_window import place
    client=lab.owned_process('client')
    if not client:raise RuntimeError('owned game client is absent')
    # Read-only physical-monitor verification. Never reposition or activate the
    # host window during a task; launch-time placement remains separate.
    monitor=place(client['pid'],timeout=1,reposition=False)
    if monitor['monitor']['name']!='HDMI-1':raise RuntimeError('game is not on HDMI-1')
    environment=lab.client_environment();nested=environment.get('DISPLAY')
    if not nested or nested.split('.')[0]==os.environ.get('DISPLAY',':0').split('.')[0]:
        raise RuntimeError('input requires a private display, refusing the host desktop')
    screen=display.Display(nested)
    try:
        root=screen.screen().root;candidates=[]
        for window in root.query_tree().children:
            if window.get_attributes().map_state!=X.IsViewable or window.get_wm_name()!='World of Warcraft':continue
            pid=window.get_full_property(screen.intern_atom('_NET_WM_PID'),X.AnyPropertyType)
            if pid is None or len(pid.value)!=1:continue
            process_pid=int(pid.value[0])
            if descendant(process_pid,client['pid']):candidates.append((window,process_pid))
        if len(candidates)!=1:raise RuntimeError('private display lacks exactly one owned visible game window')
        window,process_pid=candidates[0];geometry=window.get_geometry()
        if (geometry.width,geometry.height)!=(1280,720):raise RuntimeError('private game window dimensions changed')
        current=screen.get_input_focus().focus
        if not hasattr(current,'id') or current.id!=window.id:
            window.set_input_focus(X.RevertToParent,X.CurrentTime);screen.sync();time.sleep(.15)
        current=screen.get_input_focus().focus
        if not hasattr(current,'id') or current.id!=window.id:raise RuntimeError('private game window did not acquire focus')
        monitor['input_isolation']={'actor':lab.actor_name(),'display':nested,'window_id':window.id,
            'game_pid':process_pid,'host_activation_sent':False,'actor_lock':lab.actor_name()}
        return monitor
    finally:screen.close()
