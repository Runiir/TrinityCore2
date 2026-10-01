"""Focus only this lab's verified game window before physical input."""
import os
import time
from . import lab_runtime as lab


def focus():
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
        root.send_event(event.ClientMessage(window=window,client_type=atom,
            data=(32,[2,X.CurrentTime,0,0,0])),
            event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
        screen.flush()
        for _ in range(20):
            active=root.get_full_property(atom,X.AnyPropertyType)
            if active is not None and len(active.value) and int(active.value[0])==window.id:return monitor
            time.sleep(.05)
        raise RuntimeError('owned game window did not acquire focus')
    finally:screen.close()
