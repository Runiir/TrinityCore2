"""Local image-and-facts decision service; this process never issues game input."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import threading
import time
from . import decision_backend as backend


def capture():
    from . import runtime, telemetry_tiles
    started = time.time()
    image = telemetry_tiles.image_region(0, 0, runtime.WIDTH, runtime.HEIGHT)
    return image, {'captured_at': started, 'capture_seconds': time.time() - started,
        'runtime': runtime.owned_process(), 'monitor': 'HDMI-1',
        'width': image.width, 'height': image.height,
        'sha256': hashlib.sha256(image.tobytes()).hexdigest(),
        'source': 'owned_window_XGetImage', 'retention': 'metadata_only'}


def budget(agent, state, questions):
    from laya.vlm import build_vlm_inputs
    receipts = {}
    for name, definition in questions.items():
        row = build_vlm_inputs(agent.processor, state, agent._to_internal(definition),
            agent.cfg['max_len'], agent.cfg['head_max_len'], prep=agent.prep)
        cuts = row['truncation']
        fields = [key for key, value in cuts.items() if value]
        receipts[name] = {'input_tokens': len(row['ids']), 'truncated_fields': fields,
                          'truncation': cuts, 'images': row['n_images']}
    return receipts


def serve(args):
    import laya
    import torch
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from . import resources
    from .ui_choice import validate_ui_request
    from tools.client_compatibility import archaeology_policy, travel_policy
    from . import guidance_policy
    package = json.loads(importlib.metadata.distribution('laya').read_text('direct_url.json'))
    if package.get('vcs_info', {}).get('commit_id') != backend.VISION_CODE_REVISION:
        raise RuntimeError('vision SDK source revision changed')
    torch.set_num_threads(4)
    resources.register_model(os.getpid())
    # RTX 2070 has no native BF16. This SDK implements only FP32 and BF16.
    agent = laya.load_vlm(backend.VISION_MODEL, revision=backend.VISION_REVISION,
        device='cuda', dtype='fp32', max_len=args.context_tokens, head_max_len=args.question_tokens)
    if agent.source != {'id': backend.VISION_MODEL, 'revision': backend.VISION_REVISION}:
        raise RuntimeError('vision checkpoint identity changed')
    if args.context_tokens > agent.model.encoder.config.text_config.max_position_embeddings:
        raise ValueError('vision context exceeds backbone capacity')
    identity = {'kind': 'vision', 'model': backend.VISION_MODEL, 'revision': backend.VISION_REVISION,
        'code_revision': backend.VISION_CODE_REVISION, 'adapter': None}
    policies = {'archaeology': archaeology_policy, 'travel': travel_policy, 'guidance': guidance_policy}
    lock = threading.Lock()
    image, frame = capture()
    started = time.perf_counter()
    def precision():
        return (torch.autocast('cuda', dtype=torch.float16) if args.precision == 'amp-fp16'
                else contextlib.nullcontext())
    with precision():
        agent.predict({'image': image, 'warmup': True}, {'action': {'type': 'choice',
            'instructions': 'Wait during service warm-up.',
            'criteria': {'wait': 'Wait without input', 'continue': 'Continue'}}}, strict=True)
    torch.cuda.synchronize()
    warmup_seconds = time.perf_counter() - started
    app = FastAPI()

    def health_data():
        return {'status': 'ready', **identity, 'base_ui': identity,
            'heads': {name: {**identity, 'policy': name} for name in policies},
            'device': str(agent.device), 'weights_dtype': 'fp32', 'precision': args.precision, 'model_saw_pixels': True,
            'action_authority': False, 'warmup_seconds': warmup_seconds,
            'context_limit': args.context_tokens, 'question_token_limit': args.question_tokens,
            'image_size': agent.prep.image_size, 'allocated_vram_mib': torch.cuda.memory_allocated() / 2**20,
            'reserved_vram_mib': torch.cuda.memory_reserved() / 2**20}

    @app.get('/health')
    def health():
        return health_data()

    def infer(payload, questions, image_mode='real', diagnostic_frame=None):
        if payload.get('model') != backend.VISION_MODEL or not isinstance(payload.get('state'), dict):
            raise HTTPException(422, 'invalid vision model or state')
        started = time.perf_counter()
        with lock:
            image, frame = diagnostic_frame or capture()
            state = {'controller': payload['state']}
            if image_mode == 'real':state['image'] = image
            elif image_mode == 'blank':
                from PIL import Image
                state['image'] = Image.new('RGB', image.size, (0, 0, 0))
            try:
                tokens = budget(agent, state, questions)
                if any(value['truncated_fields'] for value in tokens.values()):
                    raise HTTPException(422, {'error': 'truncation', 'token_budget': tokens})
                with precision():
                    result = agent.predict(state, questions, n_permutations=1, strict=True)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            torch.cuda.synchronize()
        # The checkpoint's act-probability head is untrained; choices are never gated by it.
        result.update(**identity, device=str(agent.device), weights_dtype='fp32', precision=args.precision, action_authority=False,
            model_saw_pixels=image_mode == 'real', diagnostic_image_mode=image_mode,
            frame=frame, token_budget=tokens,
            context_limit=args.context_tokens, question_token_limit=args.question_tokens,
            elapsed_sec=time.perf_counter() - started)
        return result

    @app.post('/v1/ui')
    def ui(payload: dict):
        try:
            questions = validate_ui_request(payload, allowed_questions=('action', 'camera'),
                                            expected_model=backend.VISION_MODEL)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return infer(payload, questions)

    @app.post('/v1/systemone')
    def policy(payload: dict):
        name = payload.get('policy', 'archaeology')
        if name not in policies:
            raise HTTPException(422, 'unknown decision policy')
        result = infer(payload, {'action': policies[name].question()})
        result['policy'] = name
        return result

    @app.post('/v1/diagnostic')
    def diagnostic(payload: dict):
        from . import runtime
        if not (runtime.ROOT / 'run/stop_dig').exists():
            raise HTTPException(409, 'image ablation requires a paused gameplay actor')
        try:
            questions = validate_ui_request(payload, expected_model=backend.VISION_MODEL)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        frame = capture()
        return {'action_authority': False, 'cases': {mode: infer(payload, questions, mode, frame)
            for mode in ('real', 'blank', 'none')}}

    print(json.dumps({'status': 'ready', **identity, 'warmup_seconds': warmup_seconds}), flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8004)
    parser.add_argument('--context-tokens', type=int, default=4096)
    parser.add_argument('--question-tokens', type=int, default=1536)
    parser.add_argument('--precision', choices=('fp32', 'amp-fp16'), default='amp-fp16')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 768 <= args.question_tokens <= args.context_tokens:
        raise ValueError('invalid local service port or context limits')
    serve(args)


if __name__ == '__main__':
    main()
