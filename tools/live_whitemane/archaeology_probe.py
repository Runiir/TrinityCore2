"""One attributable Laya archaeology decision over supervised visual observations.

Telescope perception is supplied as an explicit human/Codex visual annotation.
This is a bounded live probe, not autonomous visual perception or a farming loop.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.request
from . import runtime, inputs
from .observe import observe
from tools.client_compatibility import archaeology_policy as policy

ENDPOINT = 'http://127.0.0.1:8004'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ready(row):
    state = row['movement']
    return (state['in_world'] and state['position_available'] and state['health_percent'] >= 90
            and state['speed'] == 0 and not any(state[k] for k in ('dead', 'in_combat', 'on_taxi')))


def command(text,*,frame_period_seconds=.1):
    return [inputs.execute('World of Warcraft','command',
        {'text':text,'frame_period_seconds':frame_period_seconds})]


def run(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    before = observe(out / 'before.png')
    state = {'task': 'recover an archaeology find', 'available': ready(before),
             'casting': False, 'artifact_visible': False, 'instrument_current': args.color != 'none',
             'telescope': None if args.color == 'none' else
                 {'color': args.color, 'heading_relative_to_player': args.direction}}
    receipt = {'schema': 'whitemane_live_laya_archaeology_probe_v1', 'started_at': time.time(),
               'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runtime.REPO, text=True).strip(),
               'probe_code_sha256': sha256(__file__), 'before': before, 'before_frame_sha256': sha256(out / 'before.png'),
               'state': state, 'annotation': {'source': 'supervised_Codex_visual_annotation',
                    'color': args.color, 'direction': args.direction,
                    'Laya_received_screenshot_pixels': False}, 'completed': False}
    failure = None
    try:
        with urllib.request.urlopen(ENDPOINT + '/health', timeout=5) as response:
            identity = json.load(response)
        request = {'model': identity['model'], 'state': state}
        req = urllib.request.Request(ENDPOINT + '/v1/systemone', data=json.dumps(request).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.load(response)
        receipt.update(model=identity, request=request, response=result)
        action = result['answers']['action']['choice']
        receipt['action'] = action
        if result['revision'] != identity['revision'] or action not in policy.ACTIONS:
            raise RuntimeError('Laya model identity or action changed')
        if any(v['truncated_fields'] for v in result['token_budget'].values()):
            raise RuntimeError('Laya input was truncated')
        if action != policy.label(state):
            raise RuntimeError('Laya choice disagrees with the declared bounded policy')
        fresh = observe(out / 'execution_precheck.png')
        receipt['precheck'] = fresh
        if not ready(fresh) or before['runtime'] != fresh['runtime']:
            raise RuntimeError('character became unavailable or client lifetime changed')
        a, b = before['movement'], fresh['movement']
        if a['sequence'] == b['sequence'] or a['map_id'] != b['map_id'] or a['position'] != b['position']:
            raise RuntimeError('stale observation or character moved before input')
        error = (a['facing_radians'] - b['facing_radians'] + math.pi) % math.tau - math.pi
        if abs(error) > .02:
            raise RuntimeError('character turned before input')
        runtime.write(out / 'episode.json', receipt)
        if action == 'survey':
            receipt['inputs'] = command('/cast Survey')
            time.sleep(3.5)
        elif action in ('turn_left', 'turn_right'):
            receipt['inputs'] = [inputs.execute('World of Warcraft', 'key',
                    {'key': 'Left' if action == 'turn_left' else 'Right', 'hold': .15})]
            time.sleep(.5)
        elif action == 'observe':
            receipt['inputs'] = []
        else:
            raise RuntimeError('forward movement and looting require the next live observation qualification')
        after = observe(out / 'after.png')
        receipt['after'] = after
        receipt['after_frame_sha256'] = sha256(out / 'after.png')
        if a['map_id'] != after['movement']['map_id'] or a['position'] != after['movement']['position']:
            raise RuntimeError('bounded stationary probe unexpectedly changed position')
        if action in ('turn_left', 'turn_right'):
            delta = (after['movement']['facing_radians'] - a['facing_radians'] + math.pi) % math.tau - math.pi
            receipt['facing_delta_radians'] = delta
            if abs(delta) < .05 or (delta > 0) != (action == 'turn_left'):
                raise RuntimeError('physical turn did not match the selected direction')
        receipt['completed'] = True
    except Exception as error:
        failure = f'{type(error).__name__}: {error}'
    receipt.update(finished_at=time.time(), failure=failure)
    runtime.write(out / 'episode.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--color', choices=('none', 'red', 'yellow', 'green'), default='none')
    parser.add_argument('--direction', choices=('left', 'right', 'aligned'))
    args = parser.parse_args()
    if args.color != 'none' and args.direction is None:
        parser.error('a real visible telescope requires its annotated relative direction')
    row = run(args)
    print(json.dumps({k: row.get(k) for k in ('completed', 'action', 'failure', 'facing_delta_radians')}))


if __name__ == '__main__':
    main()
