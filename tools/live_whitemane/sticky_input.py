"""Persistent owned input with an independent lease and calculated pulse ends."""
import threading
import time


class StickyInput:
    def __init__(self,sender,*,lease=.35,clock=time.monotonic,threaded=True):
        self.sender=sender;self.lease=lease;self.clock=clock;self.held={}
        self.deadline=clock()+lease;self.interrupted=None;self.lock=threading.RLock()
        self.stop=threading.Event();self.worker=None
        if threaded:
            self.worker=threading.Thread(target=self.pump,daemon=True);self.worker.start()

    def send(self,name,on):
        code,_=self.sender._keycode(self.sender.XK.string_to_keysym(name))
        self.sender._send(self.sender.X.KeyPress if on else self.sender.X.KeyRelease,code)

    def renew(self):
        with self.lock:
            if self.interrupted:raise RuntimeError(self.interrupted)
            self.deadline=self.clock()+self.lease

    def hold(self,name,on,seconds=None):
        with self.lock:
            if on and self.interrupted:raise RuntimeError(self.interrupted)
            if on and name not in self.held:
                self.send(name,True);self.held[name]=None if seconds is None else self.clock()+seconds
            elif on and seconds is not None:
                deadline=self.clock()+seconds
                if self.held[name] is None or deadline<self.held[name]:self.held[name]=deadline
            elif not on and name in self.held:
                self.send(name,False);del self.held[name]

    def tick(self):
        with self.lock:
            now=self.clock()
            if now>=self.deadline:
                self.interrupted='movement decision lease expired'
                for name in list(self.held):self.hold(name,False)
            else:
                for name,deadline in list(self.held.items()):
                    if deadline is not None and now>=deadline:self.hold(name,False)

    def pump(self):
        while not self.stop.wait(.005):
            try:self.tick()
            except Exception as error:
                self.interrupted='owned input watchdog failed: '+str(error);break

    def close(self):
        self.stop.set()
        if self.worker:self.worker.join(timeout=1)
        try:
            with self.lock:
                for name in list(self.held):self.hold(name,False)
        finally:self.sender.close()
