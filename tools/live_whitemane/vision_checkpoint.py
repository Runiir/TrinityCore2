"""Track, push, verify, and offload one closed offline vision-head experiment."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from .vision_dataset import write
from .vision_train import sha256
from .archeolog_checkpoint import verify_remote_object


def command(*args):
    return subprocess.check_output(list(args), text=True).strip()


def main():
    from dvclive import Live
    import yaml
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--label', default='vision_task_head_sft_v0_20261006')
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    if experiment.parent != Path('/tmp') or not experiment.name.startswith('vision-task-sft-'):
        raise ValueError('Only this explicitly owned temporary experiment can be offloaded')
    receipt = json.loads((experiment / 'model/receipt.json').read_text())
    if receipt.get('promoted') or receipt.get('served') or receipt.get('visual_training'):
        raise ValueError('This checkpoint owns an offline text-only pilot')
    with Live(dir=str(experiment / 'dvclive'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        live.log_params({key: receipt[key] for key in ('model', 'training_kind', 'parent_model',
            'parent_revision', 'sdk_revision', 'config_sha256', 'dataset_sha256', 'code_commit')})
        for row in receipt['history']:
            for name in ('train_loss', 'validation_accuracy', 'validation_nll', 'epoch_seconds'):
                live.log_metric('train/' + name, row[name])
            live.next_step()
        for label in ('baseline', 'candidate'):
            for name in ('accuracy', 'macro_task_accuracy', 'nll', 'brier', 'ece'):
                live.log_metric(label + '/test_' + name, receipt[label]['test'][name])
        live.log_metric('resources/maximum_rss_mib', receipt['maximum_rss_mib'])
        live.log_metric('resources/feature_cache_bytes', receipt['feature_cache_bytes'])
        live.log_metric('data/visual_examples', 0)
        live.log_metric('data/rlvr_trajectories', 0)
    archive = Path('artifacts/client_harness') / (args.label + '.tar.gz')
    pointer = archive.with_suffix(archive.suffix + '.dvc')
    if archive.exists() or pointer.exists():
        raise ValueError('Closed immutable experiment already exists')
    with tarfile.open(archive, 'w:gz') as handle:
        for path in sorted(experiment.rglob('*')):
            if path.is_file():
                handle.add(path, arcname=str(path.relative_to(experiment)), recursive=False)
    archive_sha = sha256(archive)
    command('dvc', 'add', str(archive))
    command('dvc', 'status', str(pointer), '--json')
    command('dvc', 'push', str(pointer))
    cloud = json.loads(command('dvc', 'status', str(pointer), '--cloud', '--json'))
    local = json.loads(command('dvc', 'status', str(pointer), '--json'))
    if cloud != {} or local != {}:
        raise RuntimeError('DVC checkpoint not synchronized; retain local evidence')
    remote = verify_remote_object(pointer)
    metadata = yaml.safe_load(pointer.read_text())['outs'][0]
    summary = {**receipt, 'dvc_pointer': str(pointer), 'archive_sha256': archive_sha,
        'archive_bytes': metadata['size'], 'remote_md5': metadata['md5'],
        'cloud_status_before_offload': cloud, 'local_status_before_offload': local,
        'remote_object_verified': remote, 'model_member': 'model/adapter.safetensors',
        'dataset_member': 'dataset.json'}
    summary_path = Path('experiments/results/client_harness') / (args.label + '.json')
    write(summary_path, summary)
    cache = Path(command('dvc', 'cache', 'dir')) / 'files/md5' / metadata['md5'][:2] / metadata['md5'][2:]
    archive.unlink()
    if cache.is_file():
        cache.unlink()
    shutil.rmtree(experiment)
    summary.update(local_experiment_pruned=True,
        local_status_after_offload=json.loads(command('dvc', 'status', str(pointer), '--json')),
        remote_object_verified_after_offload=verify_remote_object(pointer),
        offload_status_interpretation='Expected local not-in-cache after scoped offload. Remote exact hash/size/ETag is verified; cloud status was empty before local pruning.')
    write(summary_path, summary)
    print(json.dumps({'summary': str(summary_path), 'pointer': str(pointer),
                      'remote_verified': True, 'local_experiment_pruned': True}), flush=True)


if __name__ == '__main__':
    main()
