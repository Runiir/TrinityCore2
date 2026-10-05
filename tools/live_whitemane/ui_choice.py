"""Unadapted pinned Laya choices over reviewed, visible UI candidates.

Perception annotations are supplied separately. Laya selects the input; this
controller verifies the owned viewport and unchanged candidate before sending it.
"""
import argparse
import hashlib
import json
import threading
import time
import urllib.request
from pathlib import Path

from tools.client_compatibility.archaeology_controller import MODEL, REVISION
from . import runtime

ENDPOINT = 'http://127.0.0.1:8005'


def validate_ui_request(payload, allowed_questions=('action',)):
    """Reject invalid choices before Laya's two-option confidence calculation."""
    if payload.get('model') != MODEL or not isinstance(payload.get('state'), dict):
        raise ValueError('invalid UI model or state')
    questions = payload.get('questions')
    if (not isinstance(questions, dict) or 'action' not in questions
            or set(questions) - set(allowed_questions)):
        raise ValueError('invalid UI questions')
    for name, definition in questions.items():
        if (not isinstance(definition, dict) or definition.get('type') != 'choice'
                or 'instructions' not in definition):
            raise ValueError(f'{name} must be a choice question with instructions')
        criteria = definition.get('criteria')
        if (not isinstance(criteria, (dict, list))
                or any(not isinstance(label, str) for label in criteria)):
            raise ValueError(f'{name} must have named choice candidates')
        # Laya converts list criteria to a dictionary, collapsing duplicate labels.
        if len(dict.fromkeys(criteria)) < 2:
            raise ValueError(f'{name} requires at least two distinct candidates')
    return questions


def token_budget(agent, state, questions):
    from laya.common import build_sequence, render_options, serialize_state
    receipts = {}
    encode = lambda value: agent.tok(value, add_special_tokens=False)['input_ids']
    for name, definition in questions.items():
        question = agent._to_internal(definition)
        instructions = encode('choice question: ' + question['ins'])
        options = [[agent.tok.mask_token_id] + encode(' ' + value)
                   for value in render_options(question)]
        expected = len(instructions) + sum(map(len, options)) + len(encode(serialize_state(state))) + 4
        sequence, markers = build_sequence(agent.tok, state, question,
                                           agent.cfg['max_len'], agent.cfg['head_max_len'])
        complete = (all(len(value) <= 49 for value in options)
                    and len(instructions) + sum(map(len, options)) <= agent.cfg['head_max_len']
                    and expected <= agent.cfg['max_len'] and len(sequence) == expected
                    and len(markers) == len(options))
        receipts[name] = {'input_tokens': len(sequence), 'expected_tokens': expected,
                          'truncated_fields': [] if complete else ['question_or_state']}
    return receipts


def serve():
    import torch
    import laya
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from huggingface_hub import snapshot_download
    torch.set_num_threads(4)
    snapshot = snapshot_download('convaiinnovations/laya', revision=REVISION,
                                 allow_patterns=['typed-decisions/*'])
    agent = laya.load(snapshot, subfolder='typed-decisions', device='cpu')
    lock = threading.Lock()
    app = FastAPI()

    @app.get('/health')
    def health():
        return {'status': 'ready', 'model': MODEL, 'revision': REVISION,
                'adapter': None, 'device': str(agent.device), 'action_authority': False}

    @app.post('/v1/systemone')
    def decide(payload: dict):
        try:
            questions = validate_ui_request(payload)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        with lock:
            budget = token_budget(agent, payload['state'], questions)
            if any(value['truncated_fields'] for value in budget.values()):
                raise HTTPException(422, {'error': 'truncation', 'token_budget': budget})
            started = time.perf_counter()
            result = agent.predict(payload['state'], questions)
        result.update(**health(), token_budget=budget, elapsed_sec=time.perf_counter() - started)
        return result

    uvicorn.run(app, host='127.0.0.1', port=8005, log_level='warning')


def step(annotation, output):
    from PIL import Image, ImageChops, ImageStat
    from .observe import observe
    from .inputs import execute
    annotation = annotation.resolve()
    output = output.resolve()
    if not annotation.is_relative_to(runtime.ROOT / 'evidence') or not output.is_relative_to(runtime.ROOT / 'evidence'):
        raise ValueError('UI evidence must stay within owned public evidence')
    if output.exists():
        raise ValueError('UI decision evidence is immutable')
    data = json.loads(annotation.read_text())
    candidates = data['candidates']
    question = {'type': 'choice', 'instructions': data.get('instructions',
                'Choose the next visible UI action to reach the requested destination. Inspect an unidentified control before clicking. Wait if unavailable.'),
                'criteria': {name: value['description'] for name, value in candidates.items()}}
    request = {'model': MODEL, 'state': data['state'], 'questions': {'action': question}}
    validate_ui_request(request)
    req = urllib.request.Request(ENDPOINT + '/v1/systemone', data=json.dumps(request).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        result = json.load(response)
    choice = result['answers']['action']['choice']
    if (result['model'] != MODEL or result['revision'] != REVISION or result.get('adapter') is not None
            or choice not in candidates or any(value['truncated_fields'] for value in result['token_budget'].values())):
        raise RuntimeError('Laya identity, candidate, or complete input check failed')
    record = {'annotation': str(annotation), 'annotation_sha256': hashlib.sha256(annotation.read_bytes()).hexdigest(),
              'request': request, 'response': result, 'choice': choice, 'executed': False,
              'perception_source': data['perception_source'], 'model_saw_pixels': False}
    runtime.write(output, record)
    selected = candidates[choice]
    if selected['action'] == 'wait':
        return record
    before = observe(output.with_name(output.stem + '_before.png'))
    record['before'] = before
    try:
        movement = before['movement']
        if (not movement['in_world'] or movement['map_id'] != data['map_id']
                or movement['in_combat'] or movement['dead'] or movement['on_taxi']
                or movement['speed'] != 0 or before['archaeology']['casting']):
            raise RuntimeError('public player state changed or is unavailable')
        with Image.open(data['frame']) as reference, Image.open(before['frame']) as fresh:
            difference = ImageStat.Stat(ImageChops.difference(reference.convert('RGB').crop(selected['bounds']),
                                                            fresh.convert('RGB').crop(selected['bounds'])))
            if max(difference.mean) > 15:
                raise RuntimeError('reviewed UI candidate changed before input')
        if selected['action'] == 'click' and not selected.get('label_confirmed'):
            raise RuntimeError('click candidate has no confirmed visible label')
        if selected.get('destination') and selected['destination'] != data.get('requested_destination'):
            raise RuntimeError('Laya selected a different destination from the user request')
        if selected['action'] not in ('click', 'hover'):
            raise RuntimeError('UI action is not a bounded click or hover')
        record['input'] = execute('World of Warcraft', selected['action'], selected['arguments'])
        record['executed'] = True
        record['after'] = observe(output.with_name(output.stem + '_after.png'))
    except BaseException as error:
        record['failure'] = str(error)
        raise
    finally:
        runtime.write(output, record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('serve')
    run = commands.add_parser('step')
    run.add_argument('--annotation', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'serve':
        serve()
    else:
        record = step(args.annotation, args.output)
        print(json.dumps({'choice': record['choice'], 'executed': record['executed'],
                          'answer': record['response']['answers']['action'], 'output': str(args.output)}))
