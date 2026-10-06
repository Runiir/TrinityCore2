"""CPU-only SFT of the pinned vision checkpoint's frozen-encoder task head.

This is supervised text-contract training, not pixel training or RLVR. No live
endpoint, actor module, screenshot capture, or input controller is imported.
Adapters must overlay the exact full parent checkpoint; SDK head-only reload
would instead fetch a different pretrained encoder and is deliberately avoided.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import time

from .vision_dataset import input_identity, validate_splits, write

MODEL = 'thaitea/laya-vision'
REVISION = 'f2fe3c12cb6d04c59d8a190250bf3fb40fc828dc'
SDK_REVISION = '9e1e2419d855ad3e1a2af4d4bd1ef6be5418842c'


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def load_parent(config):
    import torch
    import laya
    from huggingface_hub import snapshot_download
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '' or config['device'] != 'cpu':
        raise ValueError('Offline training requires CUDA_VISIBLE_DEVICES empty and CPU config')
    if not 1 <= config['torch_threads'] <= 2:
        raise ValueError('Offline CPU pilot is limited to two threads')
    torch.set_num_threads(config['torch_threads'])
    torch.set_num_interop_threads(1)
    distribution = importlib.metadata.distribution('laya')
    direct = json.loads(distribution.read_text('direct_url.json'))
    if direct.get('vcs_info', {}).get('commit_id') != SDK_REVISION:
        raise ValueError('Pinned vision SDK identity mismatch')
    if (config['parent_model'], config['parent_revision'], config['sdk_revision']) != (MODEL, REVISION, SDK_REVISION):
        raise ValueError('Pinned parent provenance mismatch')
    folder = Path(snapshot_download(MODEL, revision=REVISION, local_files_only=True))
    agent = laya.load_vlm(str(folder), device='cpu', dtype='fp32',
                         max_len=config['context_tokens'], head_max_len=config['question_tokens'])
    # Loading an already pinned local snapshot makes no Hub/service calls.
    agent.source = {'id': MODEL, 'revision': REVISION}
    agent.model.eval()
    freeze_head(agent.model)
    sdk_folder = Path(distribution.locate_file('laya'))
    identity = {'parent_model': MODEL, 'parent_revision': REVISION,
        'parent_weights_sha256': sha256(folder / 'model.safetensors'),
        'parent_config_sha256': sha256(folder / 'vlm_agent_config.json'),
        'sdk_revision': SDK_REVISION,
        'sdk_files_sha256': {name: sha256(sdk_folder / name)
                             for name in ('vlm.py', 'vlm_train.py', 'preprocess.py')},
        'pixi_lock_sha256': sha256(Path(__file__).parent / 'vision/pixi.lock'),
        'versions': {name: importlib.metadata.version(name)
                     for name in ('laya', 'torch', 'transformers', 'torchvision')},
        'parent_total_parameters': sum(p.numel() for p in agent.model.parameters()),
        'trainable_parameters': sum(p.numel() for p in agent.model.parameters() if p.requires_grad)}
    return agent, identity


def freeze_head(model):
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith(('head.', 'type_emb.', 'scorer.')))
    model.encoder.eval()


def encode(agent, row, order=None):
    from laya.common import QTYPES
    from laya.vlm import build_vlm_inputs, input_ids_sha256
    options = list(row['question']['criteria'])
    order = list(range(len(options))) if order is None else order
    if sorted(order) != list(range(len(options))):
        raise ValueError('option_order must preserve every original choice exactly once')
    item = build_vlm_inputs(agent.processor, {'controller': row['state']},
        agent._to_internal(row['question']), agent.cfg['max_len'], agent.cfg['head_max_len'],
        option_order=order, prep=agent.prep)
    if any(item['truncation'].values()):
        raise ValueError('incomplete structured state/question/options cannot enter training')
    if item['n_images'] or item['pixel_values'] is not None or item.get('raw_images') is not None:
        raise ValueError('synthetic dataset unexpectedly contains pixels')
    item.update(qtype=QTYPES['choice'], label=order.index(options.index(row['label'])))
    return item, {'input_tokens': len(item['ids']), 'input_ids_sha256': input_ids_sha256([item['ids']]),
                  'options': [options[i] for i in order], 'truncation': item['truncation']}


def cache_row(agent, row, order=None):
    import torch
    from laya.vlm import collate_vlm
    item, budget = encode(agent, row, order)
    batch = collate_vlm([item], agent.processor.tokenizer.pad_token_id)
    captured = []
    hook = agent.model.encoder.register_forward_hook(
        lambda module, args, output: captured.append(output.last_hidden_state.detach().half()))
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            logits, _ = agent.model(**{key: batch[key] for key in
                ('input_ids', 'attention_mask', 'marker_pos', 'marker_mask', 'qtype', 'option_span')})
    finally:
        hook.remove()
    # Clone outside inference_mode for later head autograd; half storage only.
    feature = captured[0].squeeze(0).clone()
    return {**row, 'feature': feature, 'item': item, 'budget': budget,
            'baseline_logits': logits.squeeze(0).float().clone()}, time.perf_counter() - started


def readout(model, rows, pad_id):
    import torch
    from laya.vlm import collate_vlm
    batch = collate_vlm([row['item'] for row in rows], pad_id)
    hidden = torch.zeros((len(rows), batch['input_ids'].shape[1], rows[0]['feature'].shape[-1]))
    for index, row in enumerate(rows):
        hidden[index, :row['feature'].shape[0]] = row['feature'].float()
    logits, _ = model._readout(hidden, batch['attention_mask'], batch['marker_pos'],
                               batch['marker_mask'], batch['qtype'])
    return logits, batch['label']


def summarize(records):
    if not records:
        return {'count': 0, 'accuracy': None, 'macro_task_accuracy': None}
    tasks, actions, bins = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in records:
        tasks[row['task']].append(row)
        actions[row['task'] + '/' + row['label']].append(row)
        bins[min(9, int(row['confidence'] * 10))].append(row)
    basic = lambda rows: {'count': len(rows), 'accuracy': statistics.mean(r['correct'] for r in rows),
        'nll': statistics.mean(r['nll'] for r in rows), 'brier': statistics.mean(r['brier'] for r in rows)}
    return {**basic(records), 'macro_task_accuracy': statistics.mean(basic(v)['accuracy'] for v in tasks.values()),
        'ece': sum(len(v) / len(records) * abs(statistics.mean(r['confidence'] for r in v)
                    - statistics.mean(r['correct'] for r in v)) for v in bins.values()),
        'by_task': {key: basic(rows) for key, rows in sorted(tasks.items())},
        'by_task_action': {key: basic(rows) for key, rows in sorted(actions.items())}}


def records_from(cached, logits, scale):
    import torch
    records = []
    for row, values in zip(cached, logits):
        probabilities = torch.softmax(values.float() / scale(row), -1)
        label = row['item']['label']
        prediction = int(probabilities.argmax())
        target = torch.nn.functional.one_hot(torch.tensor(label), probabilities.numel()).float()
        records.append({'id': row['id'], 'group_id': row['group_id'], 'task': row['task'],
            'label': row['label'], 'prediction': row['budget']['options'][prediction],
            'correct': int(prediction == label), 'confidence': float(probabilities.max()),
            'label_probability': float(probabilities[label]),
            'nll': float(-probabilities[label].clamp_min(1e-12).log()),
            'brier': float(((probabilities - target) ** 2).sum())})
    return records


def collect_head(model, rows, pad_id, batch_size):
    import torch
    model.eval()
    result = []
    with torch.inference_mode():
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            logits, _ = readout(model, batch, pad_id)
            result.extend(value[:len(row['item']['markers'])].clone()
                          for value, row in zip(logits, batch))
    return result


def fit_temperature(rows, logits):
    """Small deterministic validation-only search; never examine test labels."""
    grid = [math.exp(i / 10) for i in range(-20, 21)]
    return min(grid, key=lambda t: summarize(records_from(rows, logits, lambda row: t))['nll'])


def balanced_batches(rows, rng, batch_size):
    """Equal task weight and within-task label weight, with replacement."""
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[row['task']][row['label']].append(row)
    tasks = sorted(groups)
    sampled = []
    for index in range(math.ceil(len(rows) / len(tasks)) * len(tasks)):
        task = tasks[index % len(tasks)]
        action = rng.choice(sorted(groups[task]))
        sampled.append(rng.choice(groups[task][action]))
    rng.shuffle(sampled)
    return [sampled[start:start + batch_size] for start in range(0, len(sampled), batch_size)]


def save_adapter(agent, output, receipt):
    from safetensors.torch import save_file
    weights = {key: value.detach().cpu().contiguous() for key, value in agent.model.state_dict().items()
               if not key.startswith('encoder.')}
    save_file(weights, str(output / 'adapter.safetensors'))
    receipt['adapter_sha256'] = sha256(output / 'adapter.safetensors')
    receipt['adapter_loading_contract'] = 'Load exact full pinned parent model, then overlay every non-encoder tensor. Do not use SDK head-only checkpoint loading.'
    write(output / 'receipt.json', receipt)


def load_adapter(agent, path):
    """Read-only compatible overlay; does not connect to or promote a service."""
    from safetensors.torch import load_file
    receipt = json.loads((path / 'receipt.json').read_text())
    if (receipt['parent_model'], receipt['parent_revision'], receipt['sdk_revision']) != (MODEL, REVISION, SDK_REVISION):
        raise ValueError('This is not an adapter for the pinned vision checkpoint')
    if agent.source != {'id': MODEL, 'revision': REVISION}:
        raise ValueError('Adapter requires exact full parent checkpoint')
    if sha256(path / 'adapter.safetensors') != receipt['adapter_sha256']:
        raise ValueError('Adapter content hash mismatch')
    weights = load_file(str(path / 'adapter.safetensors'))
    expected = {key for key in agent.model.state_dict() if not key.startswith('encoder.')}
    if set(weights) != expected:
        raise ValueError('Adapter must contain all and only the pinned decision-head tensors')
    settings = receipt['inference_config']
    if (settings['readout'] != agent.model.readout
            or settings['option_attention'] != agent.model.option_attention
            or settings['preprocess'] != agent.prep.to_config()):
        raise ValueError('Adapter prompt/image preprocessing differs from its pinned parent')
    if settings['max_len'] > agent.model.encoder.config.text_config.max_position_embeddings:
        raise ValueError('Adapter context exceeds backbone capacity')
    agent.cfg.update({key: settings[key] for key in ('max_len', 'head_max_len')})
    agent.processor.laya_max_len = settings['max_len']
    result = agent.model.load_state_dict(weights, strict=False)
    if result.unexpected_keys or any(not key.startswith('encoder.') for key in result.missing_keys):
        raise ValueError('Incomplete or incompatible adapter')
    agent.temperature = [receipt['candidate_temperature'], 1., 1.]
    agent.temperature_by_options = {}
    return receipt


def main():
    import torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    config = json.loads(args.config.read_text())
    data = json.loads(args.dataset.read_text())
    validate_splits(data['splits'])
    if any(not rows for rows in data['splits'].values()):
        raise ValueError('Training, validation, and untouched test sets are all required')
    args.output.mkdir(parents=True, exist_ok=False)
    random.seed(config['seed']); torch.manual_seed(config['seed'])
    started = time.perf_counter()
    agent, identity = load_parent(config)
    print(json.dumps({'stage': 'parent_loaded', **identity,
        'rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}), flush=True)
    cached, cache_bytes, latency = {}, 0, []
    for split, rows in data['splits'].items():
        cached[split] = []
        for index, row in enumerate(rows):
            value, elapsed = cache_row(agent, row)
            cache_bytes += value['feature'].numel() * value['feature'].element_size()
            if cache_bytes > config['feature_cache_max_bytes']:
                raise RuntimeError('Frozen-feature cache exceeded explicit 256 MiB bound')
            cached[split].append(value); latency.append(elapsed)
            if index == 3:
                print(json.dumps({'stage': 'measured_cost', 'split': split,
                    'mean_forward_seconds': statistics.mean(latency),
                    'estimated_remaining_forward_seconds': statistics.mean(latency)
                       * (sum(len(v) for v in data['splits'].values()) - len(latency))}), flush=True)
        print(json.dumps({'stage': 'frozen_features', 'split': split, 'count': len(rows),
                          'cache_bytes': cache_bytes}), flush=True)
    pad_id = agent.processor.tokenizer.pad_token_id
    baseline_logits = {key: collect_head(agent.model, rows, pad_id, config['batch_size'])
                       for key, rows in cached.items()}
    storage_drift = {'maximum_absolute_logit_difference': max(
        float((values - row['baseline_logits']).abs().max())
        for key, rows in cached.items() for row, values in zip(rows, baseline_logits[key])),
        'argmax_disagreements': sum(int(values.argmax() != row['baseline_logits'].argmax())
        for key, rows in cached.items() for row, values in zip(rows, baseline_logits[key]))}
    from laya.common import temp_bucket, QTYPES
    parent_scale = lambda row: agent.temperature_by_options.get(
        temp_bucket(QTYPES['choice'], len(row['item']['markers'])), agent.temperature[0])
    baseline_temperature = fit_temperature(cached['validation'], baseline_logits['validation'])
    baseline, baseline_predictions = {}, {}
    for name, rows in cached.items():
        records = records_from(rows, baseline_logits[name], parent_scale)
        baseline[name] = summarize(records); baseline_predictions[name] = records
    parameters = [p for p in agent.model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=config['learning_rate'], weight_decay=config['weight_decay'])
    best, best_weights, history = float('inf'), None, []
    rng = random.Random(config['seed'])
    for epoch in range(config['epochs']):
        agent.model.train(); agent.model.encoder.eval()
        losses = []
        epoch_started = time.perf_counter()
        for rows in balanced_batches(cached['train'], rng, config['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            logits, labels = readout(agent.model, rows, pad_id)
            loss = torch.nn.functional.cross_entropy(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite supervised loss')
            loss.backward(); torch.nn.utils.clip_grad_norm_(parameters, 1.)
            optimizer.step(); losses.append(float(loss.detach()))
        validation_logits = collect_head(agent.model, cached['validation'], pad_id, config['batch_size'])
        validation = summarize(records_from(cached['validation'], validation_logits, lambda row: 1.))
        record = {'epoch': epoch, 'train_loss': statistics.mean(losses),
            'validation_accuracy': validation['accuracy'], 'validation_nll': validation['nll'],
            'epoch_seconds': time.perf_counter() - epoch_started}
        history.append(record)
        if validation['nll'] < best:
            best = validation['nll']
            best_weights = {key: value.detach().clone() for key, value in agent.model.state_dict().items()
                            if not key.startswith('encoder.')}
        print(json.dumps(record), flush=True)
    agent.model.load_state_dict(best_weights, strict=False)
    candidate_logits = {key: collect_head(agent.model, rows, pad_id, config['batch_size'])
                        for key, rows in cached.items()}
    candidate_temperature = fit_temperature(cached['validation'], candidate_logits['validation'])
    candidate, candidate_predictions, calibrated_baseline = {}, {}, {}
    for name, rows in cached.items():
        records = records_from(rows, candidate_logits[name], lambda row: candidate_temperature)
        candidate[name] = summarize(records); candidate_predictions[name] = records
        calibrated_baseline[name] = summarize(records_from(rows, baseline_logits[name],
                                                          lambda row: baseline_temperature))
    training_core = {input_identity(row, False) for row in cached['train']}
    test_core_subsets = {}
    for label, novel in (('novel_core', True), ('recurring_core', False)):
        indices = [i for i, row in enumerate(cached['test'])
                   if (input_identity(row, False) not in training_core) == novel]
        present = {cached['test'][i]['task'] + '/' + cached['test'][i]['label'] for i in indices}
        all_classes = {row['task'] + '/' + row['label'] for row in cached['test']}
        test_core_subsets[label] = {
            'baseline': summarize([baseline_predictions['test'][i] for i in indices]),
            'candidate': summarize([candidate_predictions['test'][i] for i in indices]),
            'missing_task_action_classes': sorted(all_classes - present)}
    # Repeat test with reversed candidate order, independently encoding full
    # context once. It is diagnostic only and never affects selection/calibration.
    permutation_baseline, permutation_candidate = [], []
    for row in data['splits']['test']:
        value, _ = cache_row(agent, row, list(reversed(range(len(row['question']['criteria'])))))
        permutation_candidate += records_from([value], [value['baseline_logits']], lambda row: candidate_temperature)
    # Temporarily overlay the parent head, retaining the exact frozen encoder.
    from huggingface_hub import snapshot_download
    from safetensors import safe_open
    folder = Path(snapshot_download(MODEL, revision=REVISION, local_files_only=True))
    with safe_open(str(folder / 'model.safetensors'), framework='pt') as handle:
        parent_head = {key: handle.get_tensor(key) for key in handle.keys() if not key.startswith('encoder.')}
        state = agent.model.state_dict()
        if any(not torch.equal(state[key], handle.get_tensor(key))
               for key in handle.keys() if key.startswith('encoder.')):
            raise RuntimeError('Frozen encoder weights changed during task training')
    agent.model.load_state_dict(parent_head, strict=False)
    for row in data['splits']['test']:
        value, _ = cache_row(agent, row, list(reversed(range(len(row['question']['criteria'])))))
        permutation_baseline += records_from([value], [value['baseline_logits']], parent_scale)
    agent.model.load_state_dict(best_weights, strict=False)
    # A held-out encoder output is stored in FP16 for bounded cache; verify
    # baseline comparison drift on the same cache and require unchanged argmax.
    drift_logits = collect_head(agent.model, cached['test'], pad_id, config['batch_size'])
    write(args.output / 'predictions.json', {'baseline': baseline_predictions,
        'candidate': candidate_predictions, 'reversed_order_baseline': permutation_baseline,
        'reversed_order_candidate': permutation_candidate})
    receipt = {'schema': 'vision_frozen_head_text_sft_v1', 'model': config['model_id'], **identity,
        'training_kind': config['training_kind'], 'true_rlvr': False, 'visual_training': False,
        'encoder_frozen': True, 'trained_modules': ['head', 'type_emb', 'scorer'],
        'encoder_weights_identical_to_parent': True,
        'code_commit': start_commit,
        'completion_code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'inference_config': {'max_len': agent.cfg['max_len'], 'head_max_len': agent.cfg['head_max_len'],
            'readout': agent.model.readout, 'option_attention': agent.model.option_attention,
            'preprocess': agent.prep.to_config()},
        'config_sha256': sha256(args.config), 'dataset_sha256': sha256(args.dataset),
        'baseline': baseline, 'candidate': candidate, 'baseline_validation_recalibrated': calibrated_baseline,
        'baseline_temperature': baseline_temperature, 'candidate_temperature': candidate_temperature,
        'reversed_order_test': {'baseline': summarize(permutation_baseline),
                                'candidate': summarize(permutation_candidate)},
        'test_core_subsets': test_core_subsets,
        'history': history, 'selected_epoch': min(history, key=lambda r: r['validation_nll'])['epoch'],
        'dataset_audit': data['audit'], 'feature_cache_bytes': cache_bytes,
        'frozen_features_dtype': 'fp16 storage, fp32 head compute',
        'baseline_full_forward_vs_cache': storage_drift,
        'maximum_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        'training_seconds': time.perf_counter() - started,
        'full_cpu_forward_seconds': {'median': statistics.median(latency),
             'p95': sorted(latency)[int(.95 * (len(latency) - 1))]},
        'input_tokens': {'min': min(r['budget']['input_tokens'] for v in cached.values() for r in v),
                         'max': max(r['budget']['input_tokens'] for v in cached.values() for r in v)},
        'promoted': False, 'served': False, 'visual_success_proven': False,
        'autonomous_improvement_proven': False,
        'interpretation': 'Synthetic contract accuracy only. No pixel training, real navigation evidence, or RLVR. Shared templates/core facts limit held-out generalization claims.'}
    save_adapter(agent, args.output, receipt)
    # The adapter must actually reload on the exact full parent with no encoder replacement.
    load_adapter(agent, args.output)
    replay_logits = collect_head(agent.model, cached['test'], pad_id, config['batch_size'])
    if any(not torch.equal(a, b) for a, b in zip(drift_logits, replay_logits)):
        raise RuntimeError('Saved adapter does not reproduce candidate logits')
    receipt['adapter_reload_logits_identical'] = True
    write(args.output / 'receipt.json', receipt)
    print(json.dumps({'stage': 'complete', 'model': receipt['model'],
        'baseline_test': baseline['test'], 'candidate_test': candidate['test'],
        'adapter_sha256': receipt['adapter_sha256'], 'training_seconds': receipt['training_seconds'],
        'maximum_rss_mib': receipt['maximum_rss_mib']}), flush=True)


if __name__ == '__main__':
    main()
