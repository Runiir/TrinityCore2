"""Read only local addon telemetry tiles from the exact owned HDMI-1 window."""
import json
import os
import time
from PIL import Image
from Xlib import display,X
from . import runtime,snapshot,farm_ui,addon_relay
from tools.client_compatibility.observation.telemetry import decode_image,PACKET

_screen=None
_owner=None
_window=None
_verified_at=0
_clock=None
_clock_owner=None
_last_capture=0


class GenerationClock:
    """Fresh displayed generations, independent of Wine's pausing game clock."""
    def __init__(self,generations):
        self.generations=dict(generations);self.seen={key:None for key in generations}

    def update(self,generations,now):
        for key,value in generations.items():
            if value!=self.generations[key]:self.seen[key]=now
        self.generations=dict(generations)

    def ages(self,now):
        if any(value is None for value in self.seen.values()):return None
        # Sampling/render allowance is conservative; static frames still age.
        return {key:now-value+.075 for key,value in self.seen.items()}


def calibrate(extension):
    global _clock
    _clock=None
    row=observation(extension)
    return {'runtime':row['runtime'],'ages':row['channel_ages'],
        'freshness':'new displayed M, A and UI generations','calibrated_at':time.time()}


def surface():
    global _screen,_owner,_window,_verified_at
    owner=runtime.owned_process()
    if owner is None:raise RuntimeError('owned tile client is absent')
    if owner!=_owner or time.monotonic()-_verified_at>5:
        placed=runtime.monitor()
        if _screen:_screen.close()
        _screen=display.Display(os.environ.get('DISPLAY',':0'))
        _window=_screen.create_resource_object('window',placed['window_id'])
        _owner=owner;_verified_at=time.monotonic()
    pid=_window.get_full_property(_screen.intern_atom('_NET_WM_PID'),X.AnyPropertyType)
    geometry=_window.get_geometry()
    if (pid is None or list(pid.value)!=[owner['pid']]
        or _window.get_attributes().map_state!=X.IsViewable
        or (geometry.width,geometry.height)!=(runtime.WIDTH,runtime.HEIGHT)):
        raise RuntimeError('owned local telemetry window changed or is obscured')
    return _window,owner


def image_region(x,y,width,height):
    window,_=surface()
    if x<0 or y<0 or x+width>runtime.WIDTH or y+height>runtime.HEIGHT:
        raise ValueError('tile read is outside the owned viewport')
    raw=window.get_image(x,y,width,height,X.ZPixmap,0xffffffff)
    if len(raw.data)!=width*height*4:raise ValueError('owned tile pixel layout changed')
    return Image.frombytes('RGB',(width,height),raw.data,'raw','BGRX')


def movement(image,calibration,extension):
    if not extension:return decode_image(image,**{k:calibration[k] for k in ('x','y','cell_size')})
    x,y,cell=(calibration[k] for k in ('x','y','cell_size'))
    bits=[]
    for i in range((PACKET.size+addon_relay.LIVE.size)*8):
        color=image.getpixel((int(x+(i%28+.5)*cell),int(y+(i//28+.5)*cell)))
        if max(color)-min(color)>30 or 40<color[0]<215:raise ValueError('partial movement tile')
        bits.append(int(color[0]>=215))
    data=bytes(sum(bits[start+b]<<(7-b) for b in range(8)) for start in range(0,len(bits),8))
    return addon_relay.movement_packet(data)


def observation(extension=True):
    global _clock,_clock_owner,_last_capture
    _,owner=surface()
    cal=json.loads((runtime.ROOT/'run/observer_calibration.json').read_text())
    if owner!=_clock_owner or time.monotonic()-_last_capture>1:
        _clock=None;_clock_owner=owner
    deadline=time.monotonic()+3
    while True:
        started=time.time();pixels=image_region(0,0,900,260)
        m=movement(pixels,cal,extension)
        a=snapshot.decode_image(pixels,x=cal['archaeology_x'],y=cal['archaeology_y'],cell_size=cal['archaeology_cell_size'])
        ui=farm_ui.decode_image(pixels,**cal['farm_ui'])
        now=time.monotonic();_last_capture=now
        generations={'M':m['sequence'],'A':a['sequence'],'F':ui['sequence']}
        if _clock is None:_clock=GenerationClock(generations)
        else:_clock.update(generations,now)
        ages=_clock.ages(now)
        if ages is not None:break
        if now>deadline:raise ValueError('local tiles did not produce fresh M, A and UI generations')
        time.sleep(.025)
    for key,limit in [('M',.75),('A',2),('F',2)]:
        if not 0<=ages[key]<=limit:raise ValueError('stale local '+key+' tile')
    if extension:a.update(m.pop('live_archaeology'))
    source='normal_public_addon_api_local_telemetry_tiles';m['source']=source
    return {'observed_at':started,'runtime':owner,'movement':m,'archaeology':a,'farm_ui':ui,
        'farm_ui_error':None,'source':source,'frame':None,'channel_ages':ages,'owned_pose':None,
        'server':'Whitemane live realm','telemetry_server_messages':0,'local_pixel_bytes':900*260*4}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true');parser.add_argument('--setup',action='store_true')
    args=parser.parse_args()
    if args.activate:calibrate(extension=not args.setup)
    row=observation(extension=not args.setup)
    if args.activate:
        runtime.write(runtime.ROOT/'run/observation_mode.json',{'transport':'local_tiles',
            'extension':not args.setup,'runtime':row['runtime'],'activated_at':time.time()})
    print(json.dumps({'activated':args.activate,'ages':row['channel_ages'],'source':row['source'],
        'telemetry_server_messages':0,'screenshot_files':0}))
