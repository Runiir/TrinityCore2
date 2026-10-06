"""Paired full/focused travel questions, same recorded candidates, CPU only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from .archeolog_dataset import archive_rows, digest, public_question, slim_step, verifier, write


FOCUS_KEYS = ('task', 'activity', 'route', 'route_instruction', 'addon_next_destination',
    'addon_digsite_name', 'next_waypoint_is_flight_master', 'route_distances_yards',
    'portal_distance_yards', 'health', 'combat', 'mounted', 'flying', 'swimming',
    'grounded', 'casting', 'falling', 'named_object', 'pending_pickup', 'minimap_clear',
    'completed_site_pending_minimap_check', 'teleport_shortcut_pending', 'route_fare_copper',
    'route_fare_source', 'recent_actions', 'last_failure', 'consecutive_actions_without_progress')


def capture(args):
    config = json.loads(args.config.read_text())
    pairs, inventory = {}, []

    def admit(step, source):
        decision = step.get('decision') or {}
        request = decision.get('request') or {}
        full = decision.get('observed_state') or decision.get('state') or request.get('state') or {}
        if (full.get('route') not in ('portal', 'taxi', 'shortcut', 'site')
                or full.get('at_digsite') is not False or full.get('pending_pickup')
                or (full.get('pickup') or {}).get('uncollected')):
            return
        question, origin = public_question(step, request)
        if not question or not isinstance(question.get('criteria'), dict):
            return
        focused = {key: full[key] for key in FOCUS_KEYS if key in full}
        if any(key.startswith('solve_') for key in question['criteria']) and 'fragments' in full:
            focused['fragments'] = full['fragments']
        identifier = digest({'full': full, 'question': question})
        action = decision.get('choice')
        outcome, rejection = verifier(step, action or '')
        pairs.setdefault(identifier, {'id': identifier, 'source': source, 'full': full,
            'focused': focused, 'question': question, 'recorded_choice': action,
            'measured_recorded_action_outcome': outcome,
            'recorded_action_outcome_rejection': rejection, 'question_origin': origin,
            'omitted_keys': sorted(set(full) - set(focused)),
            'known_at_digsite': False, 'known_pending_pickup': False,
            'intervention_attribution': 'unknown'})

    names = ['whitemane_live_20261006_stable_loop_04.tar.gz',
             'whitemane_live_20261006_stable_loop_03.tar.gz',
             'whitemane_live_20261006_background30_02.tar.gz']
    recent = sorted(args.repo.glob('artifacts/client_harness/whitemane_live_auto_*.tar.gz.dvc'))[-5:]
    names.extend(p.with_suffix('').name for p in recent)
    for name in names:
        path = 'artifacts/client_harness/' + name
        for step, member, _ in archive_rows(path, args.repo, config):
            admit(step, {'archive': path, 'member': member})
        inventory.append(path)
    if args.loop_snapshot:
        # The live loop is read atomically into our immutable offline snapshot;
        # no controller file or service is changed. Its SHA is part of evidence.
        blob = args.loop_snapshot.read_bytes()
        data = json.loads(blob)
        snapshot = args.output.with_name('context_loop_snapshot.json')
        snapshot.write_bytes(blob)
        source = {'offline_snapshot': snapshot.name, 'sha256': hashlib.sha256(blob).hexdigest()}
        for step in data.get('steps', []):
            admit(slim_step(step), source)
    values = sorted(pairs.values(), key=lambda row: row['id'])[:args.maximum_pairs]
    write(args.output, {'schema': 'archeolog_paired_context_v1', 'created_at': time.time(),
        'source_inventory': inventory, 'available_pair_count': len(pairs), 'sample_count': len(values),
        'sampling': 'deterministic_sha_sorted_bounded_sample',
        'state_view': 'exact recorded pre-action full facts and current focused travel keys',
        'candidates_identical': True, 'pairs': values})
    print(json.dumps({'context_pairs_available': len(pairs), 'sample_count': len(values)}), flush=True)


def evaluate_pairs(agent, path):
    import torch
    from .archeolog_train import features, sequence, temperature
    data = json.loads(path.read_text())
    rows = []
    for pair in data['pairs']:
        options = list(pair['question']['criteria'])
        result = {k: pair[k] for k in ('id', 'source', 'recorded_choice', 'omitted_keys',
                   'measured_recorded_action_outcome', 'recorded_action_outcome_rejection')}
        for name, view, maximum, head_maximum in (
                ('full_1024', 'full', 1024, 256), ('focused_1024', 'focused', 1024, 256),
                ('full_2048', 'full', 2048, 512)):
            item, budget = sequence(agent, pair[view], pair['question'], maximum, head_maximum)
            result[name] = {'token_budget': budget}
            if budget['truncated_fields']:
                result[name]['status'] = 'unscorable_without_truncation'
                continue
            _, logits, latency = features(agent, item)
            probabilities = torch.softmax(logits / temperature(agent, len(options)), -1)
            result[name].update(status='scored', choice=options[int(probabilities.argmax())],
                probabilities={k: float(v) for k, v in zip(options, probabilities)},
                latency_seconds=latency)
        if all(result[name]['status'] == 'scored' for name in ('full_1024', 'focused_1024')):
            result['disagreement'] = result['full_1024']['choice'] != result['focused_1024']['choice']
        else:
            result['disagreement'] = None
        result['regression_proven'] = False
        rows.append(result)
    paired = [row for row in rows if row['disagreement'] is not None]
    return {'schema': 'archeolog_paired_context_audit_v1', 'pair_file_sha256': digest(data),
            'count': len(rows), 'both_fit_count': len(paired),
            'disagreements': sum(bool(row['disagreement']) for row in paired),
            'coverage': {name: dict(Counter(row[name]['status'] for row in rows)) for name in ('full_1024', 'focused_1024', 'full_2048')},
            'rows': rows, 'live_actions_sent': 0, 'service_requests_sent': 0,
            'interpretation': 'Identical-candidate CPU parent-model comparison. Only the recorded action has an observed transition; disagreement alone does not establish a regression, and no alternate-action counterfactual outcome exists.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/client_harness/archeolog_v0.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--loop-snapshot', type=Path)
    parser.add_argument('--maximum-pairs', type=int, default=12)
    capture(parser.parse_args())


if __name__ == '__main__':
    main()
