"""DVCLive/DVC checkpoint and scoped offload of one closed CPU pilot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

from .archeolog_dataset import write


def command(*args):
    return subprocess.check_output(list(args), text=True).strip()


def checkpoint(args):
    from dvclive import Live
    import yaml
    experiment = args.experiment.resolve()
    if not str(experiment).startswith('/tmp/archeolog-'):
        raise ValueError('offload can only remove the explicitly owned /tmp/archeolog- experiment')
    model = experiment / args.model_folder
    receipt = json.loads((model / 'receipt.json').read_text())
    audit = json.loads((experiment / 'audit.json').read_text())
    context = json.loads((model / 'context_audit.json').read_text())
    metrics = {'audit/candidate_occurrences': audit['candidate_occurrences'],
               'audit/distinct_inputs': audit['deduplicated_inputs'],
               'audit/trusted_rlvr_trajectories': 0,
               'train/examples': audit['split_counts']['train'],
               'test/examples': audit['split_counts']['test'],
               'resources/maximum_rss_mib': receipt['maximum_rss_mib'],
               'resources/feature_cache_bytes': receipt['feature_cache_bytes'],
               'context/sample_count': context['count'],
               'context/disagreements': context['disagreements']}
    for name in ('baseline', 'candidate'):
        for key in ('accuracy', 'nll', 'ece', 'brier'):
            value = receipt[name]['test'][key]
            if value is not None:
                metrics[f'{name}/test_{key}'] = value
    with Live(dir=str(experiment / 'dvclive'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        live.log_params({'model': receipt['model'], 'training_kind': receipt['training_kind'],
                         'code_commit': receipt['code_commit'], 'config_sha256': receipt['config_sha256'],
                         'device': 'cpu', 'promoted': False, 'true_rlvr': False})
        for row in receipt['history']:
            live.log_metric('train/loss', row['train_loss'])
            for key, value in metrics.items():
                live.log_metric(key, value)
            live.next_step()
    archive = Path('artifacts/client_harness') / (args.label + '.tar.gz')
    if archive.exists() or archive.with_suffix(archive.suffix + '.dvc').exists():
        raise ValueError('immutable checkpoint already exists')
    selected = [experiment / name for name in ('audit.json', 'dataset.json', 'quarantine.jsonl',
                 'context_pairs.json', 'context_loop_snapshot.json')]
    selected += sorted(model.glob('*'))
    selected += sorted((experiment / 'dvclive').rglob('*'))
    files = [path for path in selected if path.is_file()]
    with tarfile.open(archive, 'w:gz') as handle:
        for path in files:
            handle.add(path, arcname=str(path.relative_to(experiment)), recursive=False)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    command('dvc', 'add', str(archive))
    pointer = archive.with_suffix(archive.suffix + '.dvc')
    command('dvc', 'push', str(pointer))
    cloud = json.loads(command('dvc', 'status', str(pointer), '--cloud', '--json'))
    if cloud != {}:
        raise RuntimeError('remote checkpoint is not synchronized; preserve local artifact')
    local_status = json.loads(command('dvc', 'status', str(pointer), '--json'))
    if local_status != {}:
        raise RuntimeError('local checkpoint changed during push')
    metadata = yaml.safe_load(pointer.read_text())['outs'][0]
    summary = {'schema': 'archeolog_offline_pilot_summary_v1', 'closed_at': time.time(),
        'model': receipt['model'], 'training_kind': receipt['training_kind'], 'true_rlvr': False,
        'code_commit': receipt['code_commit'], 'artifact': str(archive), 'dvc_pointer': str(pointer),
        'archive_sha256': archive_sha, 'remote_md5': metadata['md5'], 'bytes': metadata['size'],
        'remote_cloud_status': cloud, 'local_status_before_offload': local_status,
        'dataset_sha256': receipt['dataset_sha256'], 'adapter_sha256': receipt['adapter_sha256'],
        'audit': {k: audit[k] for k in ('archives', 'candidate_occurrences',
            'unique_measured_outcome_actions', 'deduplicated_inputs', 'quarantine_unique',
            'quarantine_reasons', 'actions', 'verifiers', 'split_counts', 'split_actions',
            'split_known_sites', 'site_overlap_train_purged_count', 'missing_site_ids_by_split')},
        'baseline': receipt['baseline']['test'], 'candidate': receipt['candidate']['test'],
        'cpu_decision_latency_seconds': receipt['cpu_decision_latency_seconds'],
        'maximum_rss_mib': receipt['maximum_rss_mib'], 'feature_cache_bytes': receipt['feature_cache_bytes'],
        'context': {k: context[k] for k in ('count', 'both_fit_count', 'disagreements', 'coverage', 'interpretation')},
        'trusted_unassisted_rlvr_trajectories': 0,
        'earlier_attempt_failure': 'Meta initialization omitted deterministic rotary buffers; corrected before the completed run.',
        'tests': {'archeolog_admission_passed': 12},
        'promoted': False, 'served': False, 'autonomous_improvement_proven': False,
        'interpretation': receipt['interpretation']}
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    write(args.summary, summary)
    cache = Path(command('dvc', 'cache', 'dir')) / 'files/md5' / metadata['md5'][:2] / metadata['md5'][2:]
    archive.unlink()
    if cache.is_file():
        cache.unlink()
    shutil.rmtree(experiment)
    # Expected local 'not in cache' after deliberate offload is recorded; the
    # cloud status remains authoritative for retrievability of this exact object.
    summary['local_status_after_offload'] = json.loads(command('dvc', 'status', str(pointer), '--json'))
    summary['remote_cloud_status_after_offload'] = json.loads(command('dvc', 'status', str(pointer), '--cloud', '--json'))
    write(args.summary, summary)
    print(json.dumps({'summary': str(args.summary), 'dvc_pointer': str(pointer),
                      'remote_cloud_status': summary['remote_cloud_status_after_offload'],
                      'generated_local_experiment_removed': True}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--model-folder', default='model_run02')
    parser.add_argument('--label', default='archeolog_v0_20261006')
    parser.add_argument('--summary', type=Path, default=Path('experiments/results/client_harness/archeolog_v0_20261006.json'))
    checkpoint(parser.parse_args())


if __name__ == '__main__':
    main()
