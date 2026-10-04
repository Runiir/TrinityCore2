"""Keep both owned presenters partly visible on HDMI-1 without changing focus."""
import argparse,json,os,time
from pathlib import Path
from Xlib import X,display
from Xlib.protocol import event
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from . import actors
from tools.second_client.place_window import place,second_monitor


def arrange():
    monitor=second_monitor()
    if monitor['name']!='HDMI-1':raise RuntimeError('requires the verified HDMI-1 monitor')
    screen=display.Display(os.environ.get('DISPLAY',':0'));root=screen.screen().root
    focused=screen.get_input_focus().focus;focus_id=getattr(focused,'id',focused)
    before={};windows={};bounds={};targets={}
    try:
        for name in ['primary','scout']:
            with actor(name):before[name]=place(lab.owned_process('client')['pid'],timeout=1,reposition=False)
            window=screen.create_resource_object('window',before[name]['window_id']);windows[name]=window
            ext=window.get_full_property(screen.intern_atom('_NET_FRAME_EXTENTS'),X.AnyPropertyType)
            borders=list(ext.value) if ext is not None else [0,0,0,0]
            if len(borders)!=4 or any(not 0<=n<=100 for n in borders):raise RuntimeError('owned frame extents differ')
            left,right,top,bottom=borders;geo=before[name]['window']
            if (geo['width'],geo['height'])!=(1280,720):raise RuntimeError('owned viewport dimensions differ')
            x=monitor['x']+1 if name=='primary' else monitor['x']+monitor['width']-1280-left-right-1
            y=monitor['y']+1 if name=='primary' else monitor['y']+monitor['height']-720-top-bottom-1
            targets[name]={'x':x,'y':y,'frame_extents':borders}
            message=event.ClientMessage(window=window.id,client_type=screen.intern_atom('_NET_MOVERESIZE_WINDOW'),
                data=(32,[(1<<8)|(1<<9)|(2<<12),x,y,0,0]))
            root.send_event(message,event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
            window.configure(stack_mode=X.Above)
        screen.sync();time.sleep(2)
        current=screen.get_input_focus().focus
        if getattr(current,'id',current)!=focus_id:raise RuntimeError('host focus changed during owned-window layout')
        for name in ['primary','scout']:
            with actor(name):bounds[name]=place(lab.owned_process('client')['pid'],timeout=1,reposition=False)
            g=bounds[name]['window']
            if not (monitor['x']<=g['x'] and g['x']+g['width']<=monitor['x']+monitor['width'] and
                monitor['y']<=g['y'] and g['y']+g['height']<=monitor['y']+monitor['height']):
                raise RuntimeError('owned viewport is not fully within HDMI-1')
        return {'before':before,'after':bounds,'targets':targets,'host_focus_unchanged':True,
            'viewport_unchanged':True,'gameplay_input_sent':False}
    finally:screen.close()


def probe(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700);trials={};original={};oracles={};native=identity('worldserver')
    report={'schema':'client442_owned_window_layout_v1','started_at':time.time(),'completed':False}
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name,controller='code');state,frame=t.observe('layout_before')
                oracle=oracles[name]=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
                original[name]=resources(oracle);t.receipt['layout_before']={'state':state,'frame':frame};t.persist()
        report['layout']=arrange();lab.private_write(out/'layout.json',json.dumps(report,indent=2)+'\n')
        time.sleep(12)
        for name,t in trials.items():
            with actor(name):
                state,frame=t.observe('layout_after');t.receipt['layout_after']={'state':state,'frame':frame}
                t.receipt['native_resources_preserved']=resources(oracles[name])==original[name]
                if not t.receipt['native_resources_preserved']:raise RuntimeError('window layout changed native resources')
                report.setdefault('framerate',{})[name]={'before':t.receipt['layout_before']['state'].get('framerate'),
                    'after':state.get('framerate')};t.persist()
        if identity('worldserver')!=native:raise RuntimeError('native server lifetime changed')
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        for t in trials.values():
            t.receipt.update(completed=report['completed'],failure=report.get('failure'),finished_at=time.time());t.persist()
        report['finished_at']=time.time();lab.private_write(out/'layout.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['completed','failure','framerate']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);probe(p.parse_args().output)
