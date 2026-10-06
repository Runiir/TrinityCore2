"""CPU-only, frozen-feature scorer pilot: outcome-filtered SFT, never RLVR.

Run in the existing Laya Pixi environment. Metrics are written as JSON; the
repository's DVC/DVCLive environment checkpoints the complete offline experiment.
No live model endpoint or gameplay controller is imported or contacted.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import time

from .archeolog_dataset import REVISION, digest, write


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def load_parent(threads):
    """Initialize on meta, then assign mapped weights to avoid duplicate models."""
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
        raise ValueError('Run with CUDA_VISIBLE_DEVICES empty; offline pilot owns CPU only')
    import torch
    from huggingface_hub import snapshot_download
    from laya.agent import Agent
    from laya.common import build_model
    from safetensors.torch import load_file
    from transformers import AutoTokenizer
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    snapshot = Path(snapshot_download('convaiinnovations/laya', revision=REVISION,
                                     allow_patterns=['typed-decisions/*'], local_files_only=True))
    folder = snapshot / 'typed-decisions'
    agent = object.__new__(Agent)
    agent.cfg = json.loads((folder / 'rl_agent_config.json').read_text())
    agent.tok = AutoTokenizer.from_pretrained(folder / 'tokenizer', local_files_only=True)
    with torch.device('meta'):
        agent.model = build_model(agent.cfg, encoder_dir=str(folder / 'encoder'))
    weights = load_file(str(folder / 'model.safetensors'))
    agent.model.load_state_dict(weights, strict=True, assign=True)
    del weights
    # Rotary frequencies are deterministic, nonpersistent buffers and therefore
    # absent from the checkpoint. Recreate them on CPU after meta initialization.
    rotary_type = type(agent.model.encoder.rotary_emb)
    agent.model.encoder.rotary_emb = rotary_type(agent.model.encoder.config, device=torch.device('cpu'))
    agent.model.float().eval()
    if any(tensor.is_meta for tensor in (*agent.model.parameters(), *agent.model.buffers())):
        raise RuntimeError('unmaterialized meta tensor remains in the CPU parent')
    agent.model.encoder.config.reference_compile = False
    agent.device, agent.dtype = torch.device('cpu'), torch.float32
    agent.temperature = agent.cfg['temperature']
    agent.temperature_by_options = agent.cfg['temperature_by_options']
    for parameter in agent.model.parameters():
        parameter.requires_grad_(False)
    return agent, {'model_weights_sha256': sha256(folder / 'model.safetensors'),
                   'model_config_sha256': sha256(folder / 'rl_agent_config.json')}


def sequence(agent, state, question, max_len=None, head_max_len=None):
    from laya.common import build_sequence, render_options, serialize_state, QTYPES
    internal = agent._to_internal(question)
    max_len = agent.cfg['max_len'] if max_len is None else max_len
    head_max_len = agent.cfg['head_max_len'] if head_max_len is None else head_max_len
    encode = lambda value: agent.tok(value, add_special_tokens=False)['input_ids']
    instructions = encode('choice question: ' + internal['ins'])
    options = [[agent.tok.mask_token_id] + encode(' ' + value) for value in render_options(internal)]
    expected = len(instructions) + sum(map(len, options)) + len(encode(serialize_state(state))) + 4
    ids, markers = build_sequence(agent.tok, state, internal, max_len, head_max_len)
    complete = (all(len(value) <= 49 for value in options)
                and len(instructions) + sum(map(len, options)) <= head_max_len
                and expected <= max_len and len(ids) == expected
                and len(markers) == len(options))
    budget = {'input_tokens': len(ids), 'expected_tokens': expected,
              'truncated_fields': [] if complete else ['question_or_state']}
    return {'ids': ids, 'markers': markers, 'qtype': QTYPES['choice']}, budget


def features(agent, item):
    """Cache only candidate marker vectors after the frozen transformer head."""
    import torch
    from laya.common import collate_items
    batch = collate_items([[item]], agent.tok.pad_token_id)
    captured = []
    hook = agent.model.scorer.register_forward_pre_hook(lambda module, args: captured.append(args[0].detach().clone()))
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            logits, _ = agent.model(**{k: batch[k] for k in
                                      ('input_ids', 'attention_mask', 'marker_pos', 'marker_mask', 'qtype')})
    finally:
        hook.remove()
    # Clone outside inference_mode so the frozen features may be used by autograd
    # when fitting the scorer (the encoder itself never receives gradients).
    return captured[0].squeeze(0).clone(), logits.squeeze(0), time.perf_counter() - started


def temperature(agent, count):
    from laya.common import temp_bucket, QTYPES
    return float(agent.temperature_by_options.get(temp_bucket(QTYPES['choice'], count), agent.temperature[0]))


def metrics(rows):
    if not rows:
        return {'count': 0, 'accuracy': None, 'nll': None, 'brier': None, 'ece': None}
    bins = defaultdict(list)
    for row in rows:
        bins[min(9, int(row['confidence'] * 10))].append(row)
    ece = sum(len(values) / len(rows) * abs(statistics.mean(r['confidence'] for r in values)
              - statistics.mean(r['correct'] for r in values)) for values in bins.values())
    return {'count': len(rows), 'accuracy': statistics.mean(r['correct'] for r in rows),
            'nll': statistics.mean(r['nll'] for r in rows),
            'brier': statistics.mean(r['brier'] for r in rows), 'ece': ece,
            'by_action': {action: {'count': len(values), 'accuracy': statistics.mean(r['correct'] for r in values)}
                          for action in sorted({r['label'] for r in rows})
                          for values in [[r for r in rows if r['label'] == action]]},
            'by_task': {task: {'count': len(values), 'accuracy': statistics.mean(r['correct'] for r in values)}
                        for task in sorted({r['task'] for r in rows})
                        for values in [[r for r in rows if r['task'] == task]]}}


def evaluate(agent, scorer, cached, scale):
    import torch
    result = []
    scorer.eval()
    with torch.inference_mode():
        for row in cached:
            probabilities = torch.softmax(scorer(row['features']).squeeze(-1) / scale(row), -1)
            target = row['target']
            predicted = int(probabilities.argmax())
            desired = torch.nn.functional.one_hot(torch.tensor(target), probabilities.numel()).float()
            result.append({'id': row['id'], 'label': row['label'], 'task': row['outcome']['kind'],
                           'prediction': row['options'][predicted], 'correct': int(predicted == target),
                           'confidence': float(probabilities.max()),
                           'label_probability': float(probabilities[target]),
                           'nll': float(-probabilities[target].clamp_min(1e-12).log()),
                           'brier': float(((probabilities - desired) ** 2).sum())})
    return metrics(result), result


def main():
    import torch
    from safetensors.torch import save_file
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--context-pairs', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    random.seed(config['seed'])
    torch.manual_seed(config['seed'])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    agent, identity = load_parent(config['torch_threads'])
    agent.cfg.update(max_len=config['max_len'], head_max_len=config['head_max_len'])
    print(json.dumps({'stage': 'parent_loaded', 'device': 'cpu', 'rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}), flush=True)
    source = json.loads(args.dataset.read_text())['splits']
    cached = {key: [] for key in source}
    rejected, latency = [], []
    cache_bytes = 0
    for split, rows in source.items():
        for row in rows:
            item, budget = sequence(agent, row['state'], row['question'])
            if budget['truncated_fields']:
                rejected.append({'id': row['id'], 'split': split, 'reason': 'offline_token_budget', **budget})
                continue
            marker_vectors, logits, elapsed = features(agent, item)
            cache_bytes += marker_vectors.numel() * marker_vectors.element_size()
            if cache_bytes > config['feature_cache_max_bytes']:
                raise RuntimeError('bounded feature cache exceeded')
            options = list(row['question']['criteria'])
            cached[split].append({**row, 'features': marker_vectors,
                                  'target': options.index(row['label']), 'options': options})
            latency.append(elapsed)
        print(json.dumps({'stage': 'features', 'split': split, 'count': len(cached[split]),
                          'feature_cache_bytes': cache_bytes}), flush=True)
    parent_scale = lambda row: temperature(agent, len(row['options']))
    baseline, baseline_predictions = {}, {}
    for split, rows in cached.items():
        baseline[split], baseline_predictions[split] = evaluate(agent, agent.model.scorer, rows, parent_scale)
    scorer = copy.deepcopy(agent.model.scorer)
    for parameter in scorer.parameters():
        parameter.requires_grad_(True)
    optimizer = torch.optim.AdamW(scorer.parameters(), lr=config['learning_rate'], weight_decay=config['weight_decay'])
    best, best_weights, history = float('inf'), None, []
    if not cached['train']:
        raise RuntimeError('no admitted train examples after context-budget checks')
    for epoch in range(config['epochs']):
        scorer.train()
        rows = list(cached['train'])
        random.shuffle(rows)
        losses = []
        for row in rows:
            optimizer.zero_grad(set_to_none=True)
            logits = scorer(row['features']).squeeze(-1)
            loss = torch.nn.functional.cross_entropy(logits[None, :], torch.tensor([row['target']]))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(scorer.parameters(), 1.)
            optimizer.step()
            losses.append(float(loss.detach()))
        validation, _ = evaluate(agent, scorer, cached['validation'], lambda row: 1.)
        selection = validation['nll'] if validation['count'] else statistics.mean(losses)
        record = {'epoch': epoch, 'train_loss': statistics.mean(losses),
                  'validation_accuracy': validation['accuracy'], 'validation_nll': validation['nll']}
        history.append(record)
        if not cached['validation'] or selection < best:
            best, best_weights = selection, copy.deepcopy(scorer.state_dict())
        print(json.dumps(record), flush=True)
    scorer.load_state_dict(best_weights)
    tuned, tuned_predictions = {}, {}
    for split, rows in cached.items():
        tuned[split], tuned_predictions[split] = evaluate(agent, scorer, rows, lambda row: 1.)
    # A compatible adapter includes every decision parameter while replacing
    # only scorer.*. Encoder/head/type embeddings/act head are preserved.
    weights = {k: value.detach().half().contiguous() for k, value in agent.model.state_dict().items()
               if not k.startswith('encoder.')}
    weights.update({'scorer.' + k: v.detach().half().contiguous() for k, v in scorer.state_dict().items()})
    save_file(weights, str(output / 'adapter.safetensors'))
    context = None
    if args.context_pairs:
        from .archeolog_context import evaluate_pairs
        context = evaluate_pairs(agent, args.context_pairs)
        write(output / 'context_audit.json', context)
    latency.sort()
    receipt = {'schema': 'archeolog_cpu_sft_pilot_v1', 'model': config['model_id'],
               'training_kind': config['training_kind'], 'true_rlvr': False,
               'parent_model': config['parent_model'], 'parent_revision': REVISION, **identity,
               'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'dataset_sha256': sha256(args.dataset), 'config_sha256': sha256(args.config),
               'adapter_sha256': sha256(output / 'adapter.safetensors'),
               'device': 'cpu', 'torch_threads': config['torch_threads'],
               'context_budget': {'max_len': config['max_len'], 'head_max_len': config['head_max_len']},
               'checkpoint_selection': 'lowest_validation_nll' if cached['validation'] else 'fixed_final_epoch_no_independent_validation',
               'encoder_frozen': True, 'transformer_head_frozen': True,
               'trained_parameters': 'scorer.* only', 'synthetic_labels': False,
               'attribution': 'historical_interventions_unknown_provisional_sft_only',
               'group_split': 'whole_client_lifetime_chronological_global_exact_input_dedup',
               'baseline': baseline, 'candidate': tuned, 'history': history,
               'offline_token_budget_rejections': rejected, 'feature_cache_bytes': cache_bytes,
               'cpu_decision_latency_seconds': {'count': len(latency),
                   'median': statistics.median(latency) if latency else None,
                   'p95': latency[min(len(latency) - 1, math_ceil(.95 * len(latency)) - 1)] if latency else None},
               'maximum_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
               'elapsed_seconds': time.perf_counter() - started,
               'live_success_proven': False, 'promoted': False, 'served': False,
               'reliable_improvement_proven': False,
               'interpretation': 'Small nonrandom historical positive-outcome SFT pilot. Accuracy is agreement with successful observed actions, not counterfactual optimality or live success. Missing task coverage and intervention attribution prevent promotion.'}
    write(output / 'receipt.json', receipt)
    write(output / 'predictions.json', {'baseline': baseline_predictions, 'candidate': tuned_predictions})
    write(output / 'config.json', config)
    print(json.dumps(receipt, indent=2), flush=True)


def math_ceil(value):
    import math
    return math.ceil(value)


if __name__ == '__main__':
    main()
