"""Bounded physical input to the owned live launcher's private EI socket."""
import argparse
import fcntl
import json
import time

from Xlib import X, display
from . import runtime


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
                sender._send(sender.X.ButtonPress,button)
                try:time.sleep(.15)
                finally:sender._send(sender.X.ButtonRelease,button)
            elif action == 'key':
                if not .05 <= arguments['hold'] <= 2:
                    raise ValueError('key hold is outside its bounded interval')
                sender.key(arguments['key'], hold=arguments['hold'])
            elif action == 'type':
                if not arguments['text'].startswith('/') or len(arguments['text']) > 500:
                    raise ValueError('only bounded ordinary in-game slash commands are supported')
                sender.type(arguments['text'])
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
    text = commands.add_parser('type')
    text.add_argument('text')
    args = vars(parser.parse_args())
    title, action = args.pop('title'), args.pop('action')
    print(json.dumps(execute(title, action, args)))


if __name__ == '__main__':
    main()
