"""Own one ready native libei sender while retaining read-only XKB lookup."""
import json,selectors,subprocess,time
from pathlib import Path
from tools.second_client import ctl
from . import lab_runtime as lab
from .native_input import control


class Input(ctl.Input):
    def __init__(self):
        self.sender=None;super().__init__()
        runtime=lab.owned_process('client')
        if not runtime:raise RuntimeError('owned input client is absent')
        environment=lab.client_environment();name=environment.get('LIBEI_SOCKET')
        if not name:raise RuntimeError('owned client lacks a private EI socket')
        path=Path(name)
        if not path.is_absolute():path=Path(environment['XDG_RUNTIME_DIR'])/path
        if not path.is_socket():raise RuntimeError('owned EI socket is absent')
        binary,receipt=control.verified()
        self.sender=subprocess.Popen([str(binary),str(path),str(runtime['pid']),runtime['start_ticks']],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        try:
            ready=self.reply(6)
            if ready.get('ready') is not True or ready.get('peer_pid')!=runtime['pid']:
                raise RuntimeError('native input sender did not verify its owned peer and readiness')
            self.initialization={'time':time.time(),'engine':'cpp_libei','peer_pid':ready['peer_pid'],
                'peer_start_ticks':runtime['start_ticks'],'display':environment['DISPLAY'],
                'device_ready':True,'gameplay_input_replayed':False,'build':receipt}
        except BaseException:self.close();raise

    def reply(self,seconds=3):
        with selectors.DefaultSelector() as selector:
            selector.register(self.sender.stdout,selectors.EVENT_READ)
            if not selector.select(seconds):raise RuntimeError('native private input reply timed out')
        line=self.sender.stdout.readline()
        if not line:raise RuntimeError('native private input sender stopped')
        row=json.loads(line)
        if row.get('error'):raise RuntimeError(row['error'])
        return row

    def _send(self,kind,detail=0,**position):
        if kind==self.X.MotionNotify:request={'kind':'move',**position}
        elif kind in [self.X.KeyPress,self.X.KeyRelease]:
            request={'kind':'key','code':detail,'pressed':kind==self.X.KeyPress}
        elif kind in [self.X.ButtonPress,self.X.ButtonRelease]:
            request={'kind':'button','code':detail,'pressed':kind==self.X.ButtonPress}
        else:raise ValueError('unsupported private native input event')
        self.sender.stdin.write(json.dumps(request)+'\n');self.sender.stdin.flush()
        if self.reply().get('ok') is not True:raise RuntimeError('native private input was not acknowledged')

    def type(self,text):
        # Background clients run at 15 FPS. Both the down interval and the gap
        # must span a client tick, including repeated letters and slash prefixes.
        for char in text:
            mapped=ctl.key_for_char(char)
            if mapped:
                code,_=self._keycode(self.XK.string_to_keysym(mapped[0]));shifted=mapped[1]
            else:code,shifted=self._keycode(ord(char))
            shift=[self._keycode(self.XK.string_to_keysym('Shift_L'))[0]] if shifted else []
            self._tap(shift+[code],.1);time.sleep(.07)

    def close(self):
        if self.sender is None:return
        try:
            self.sender.stdin.close();self.sender.wait(timeout=2)
        except (OSError,subprocess.TimeoutExpired):
            self.sender.terminate()
            try:self.sender.wait(timeout=1)
            except subprocess.TimeoutExpired:self.sender.kill();self.sender.wait(timeout=1)
        finally:self.sender=None

    def __del__(self):
        self.close()
        if hasattr(self,'display'):self.display.close()
