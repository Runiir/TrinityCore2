"""Bounded physical input to the owned live launcher's private EI socket."""
import argparse
import fcntl
import json
import math
import time

from Xlib import X, display
from . import runtime


def key_hold(row,minimum=.15):
    """Keep a selected key down across two measured client frames."""
    fps=(row.get('farm_ui') or {}).get('frame_rate')
    if not isinstance(fps,(int,float)) or not math.isfinite(fps) or fps<=0:return minimum
    return min(2,max(minimum,2/fps))


def focus(title):
    runtime.monitor()
    owner = runtime.owned_process()
    rows = [row for row in runtime.windows() if row['title'] == title]
    if len(rows) != 1:
        raise RuntimeError('private display lacks exactly one owned ' + title + ' window')
    screen = display.Display(runtime.client_environment()['DISPLAY'])
    try:
        window = screen.create_resource_object('window', rows[0]['id'])
        window.set_input_focus(X.RevertToParent, X.CurrentTime)
        screen.sync()
        current = screen.get_input_focus().focus
        if not hasattr(current, 'id') or current.id != window.id:
            raise RuntimeError('owned private window did not acquire focus')
        return {'supervisor_pid': owner['pid'], 'supervisor_start_ticks': owner['start_ticks'],
                'window': rows[0], 'host_activation_sent': False}
    finally:
        screen.close()


def execute(title, action, arguments):
    # Reject before focus, sender creation, or any key event. This also covers
    # old helpers retained by a running controller during a source update.
    if action in ('command','type','edit_text'):
        raise RuntimeError('text-box input is disabled; use an existing action-bar macro')
    from .resources import check,append_action
    check()
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    from . import native_control
    # These module bindings are private to this command process. The rewrite
    # lab modules, running controllers, and their runtime records are unchanged.
    ctl._launcher_env = runtime.client_environment
    native_input_adapter.lab = runtime
    native_input_adapter.control = native_control
    with (runtime.ROOT / 'run/input.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = focus(title)
        sender = native_input_adapter.Input()
        receipt = {'started_at': time.time(), 'identity': identity, 'action': action,
                   'arguments': arguments, 'input': sender.initialization, 'completed': False}
        try:
            if action == 'click':
                x, y = arguments['x'], arguments['y']
                if not 0 <= x < runtime.WIDTH or not 0 <= y < runtime.HEIGHT:
                    raise ValueError('click is outside the private viewport')
                sender.move(x,y)
                time.sleep(.35)
                sender._send(sender.X.ButtonPress,arguments['button'])
                try: time.sleep(.15)
                finally: sender._send(sender.X.ButtonRelease,arguments['button'])
                time.sleep(.15)
            elif action == 'hover':
                x,y=arguments['x'],arguments['y']
                if not 0<=x<runtime.WIDTH or not 0<=y<runtime.HEIGHT:
                    raise ValueError('hover is outside the private viewport')
                sender.move(x,y)
                time.sleep(.5)
            elif action == 'button':
                button=arguments['button']
                if button not in (1,3,8,9):raise ValueError('unsupported owned mouse button')
                if 'x' in arguments or 'y' in arguments:
                    x,y=arguments['x'],arguments['y']
                    period=arguments.get('frame_period_seconds',1/30)
                    if not 0<=x<runtime.WIDTH or not 0<=y<runtime.HEIGHT or not 0<period<=2:
                        raise ValueError('button positioning is outside the owned viewport or frame period')
                    sender.move(x,y);time.sleep(period)
                sender._send(sender.X.ButtonPress,button)
                try:time.sleep(.15)
                finally:sender._send(sender.X.ButtonRelease,button)
            elif action == 'key':
                if not .05 <= arguments['hold'] <= 2:
                    raise ValueError('key hold is outside its bounded interval')
                try:sender.key(arguments['key'], hold=arguments['hold'])
                except SystemExit as error:
                    raise RuntimeError('selected client binding is unavailable: '+str(error)) from error
            elif action == 'scroll':
                steps=arguments['steps'];period=arguments.get('frame_period_seconds',1/30)
                if type(steps) is not int or not 1<=abs(steps)<=8 or not 0<period<=2:
                    raise ValueError('camera wheel input exceeds its bounded interval')
                # Place the cursor over the world, rather than a scrollable UI.
                sender.move(runtime.WIDTH//2,runtime.HEIGHT//6);time.sleep(period)
                button=5 if steps>0 else 4
                for _ in range(abs(steps)):
                    sender._send(sender.X.ButtonPress,button)
                    sender._send(sender.X.ButtonRelease,button)
                    time.sleep(period)
                time.sleep(max(.15,2*period))
            elif action == 'drag':
                origin,destination=arguments['from'],arguments['to']
                period=arguments.get('frame_period_seconds',1/30)
                if (len(origin)!=2 or len(destination)!=2 or not 0<period<=2
                        or any(type(p[0]) is not int or type(p[1]) is not int
                            or not 0<=p[0]<runtime.WIDTH or not 0<=p[1]<runtime.HEIGHT
                            for p in (origin,destination))):
                    raise ValueError('macro drag is outside the owned viewport')
                sender.move(*origin);time.sleep(period)
                sender._send(sender.X.ButtonPress,1)
                try:
                    time.sleep(max(.15,period))
                    for step in range(1,7):
                        fraction=step/6
                        sender.move(*(round(a+(b-a)*fraction) for a,b in zip(origin,destination)))
                        time.sleep(period)
                finally:sender._send(sender.X.ButtonRelease,1)
                time.sleep(max(.15,period))
            else:
                raise ValueError('unknown input action')
            receipt['completed'] = True
        finally:
            sender.close()
            receipt['finished_at'] = time.time()
            append_action(receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--title', choices=('Whitemane', 'World of Warcraft'), required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    click = commands.add_parser('click')
    click.add_argument('x', type=int)
    click.add_argument('y', type=int)
    click.add_argument('--button', type=int, choices=(1, 3, 8, 9), default=1)
    key = commands.add_parser('key')
    key.add_argument('key')
    key.add_argument('--hold', type=float, default=.15)
    scroll = commands.add_parser('scroll')
    scroll.add_argument('steps',type=int)
    args = vars(parser.parse_args())
    title, action = args.pop('title'), args.pop('action')
    print(json.dumps(execute(title, action, args)))


if __name__ == '__main__':
    main()
