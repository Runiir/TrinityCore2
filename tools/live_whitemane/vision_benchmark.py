"""Read-only benchmark of full retained actor questions on owned game frames."""
import argparse
import copy
import json
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request
from . import runtime, decision_backend as backend
from .vision_model import capture


def call(path, payload=None):
    request = 'http://127.0.0.1:8004' + path
    if payload is not None:
        request = urllib.request.Request(request, data=json.dumps(payload).encode(),
                                        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def run(output, samples):
    if not (runtime.ROOT / 'run/stop_dig').exists():
        raise RuntimeError('benchmark requires a paused gameplay actor')
    if output.exists() or not output.resolve().is_relative_to(runtime.ROOT / 'evidence'):
        raise ValueError('benchmark must use new owned public evidence')
    loop = json.loads((runtime.ROOT / 'evidence/farm_graph_01/loop.json').read_text())
    if loop['status'] != 'supervisor_stopped':
        raise RuntimeError('gameplay actor has not finished pausing')
    output.mkdir(parents=True)
    image, frame = capture()
    image.save(output / 'benchmark_frame.png')
    cases = {}
    for step in reversed(loop['steps']):
        request = (step.get('decision') or {}).get('request')
        if request and 'questions' in request:
            cases['farm'] = copy.deepcopy(request)
            break
    if loop.get('dig_output'):
        path = Path(loop['dig_output']) / 'session.json'
        if path.exists():
            dig = json.loads(path.read_text())
            for step in reversed(dig['steps']):
                request = step.get('request')
                if request and 'questions' in request:
                    cases['dig'] = copy.deepcopy(request)
                    break
    if not cases:
        raise RuntimeError('no attributed actor questions available')
    report = {'backend': call('/health'), 'captured_frame': frame,
        'actor_status': loop['status'], 'gameplay_inputs': 0, 'cases': {},
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'source_note': 'Full retained actor state/questions; each sample captures current owned pixels. '
                       'This checks execution and latency, not gameplay success.'}
    for name, request in cases.items():
        request['model'] = backend.VISION_MODEL
        results = []
        for _ in range(samples):
            started = time.perf_counter()
            response = call('/v1/ui', request)
            results.append({'wall_seconds': time.perf_counter() - started, 'response': response})
        timings = [value['wall_seconds'] for value in results]
        report['cases'][name] = {'request': request, 'samples': results,
            'median_ms': statistics.median(timings) * 1000,
            'max_ms': max(timings) * 1000,
            'choices': [value['response']['answers']['action']['choice'] for value in results]}
    report['final_health'] = call('/health')
    runtime.write(output / 'benchmark.json', report)
    return {key: {field: case[field] for field in ('median_ms', 'max_ms', 'choices')}
            for key, case in report['cases'].items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.samples <= 50:
        raise ValueError('samples must be between 1 and 50')
    print(json.dumps(run(args.output, args.samples)))
