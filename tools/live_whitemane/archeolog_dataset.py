"""Read immutable public DVC evidence and admit measured action outcomes offline.

No live controller imports, gameplay, service requests, or capture extraction.
Archived actions with unknown human intervention remain provisional SFT data;
they never become on-policy RLVR trajectories merely by passing an outcome check.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile


REVISION = 'c5d78730f3493e4fe16d61507ef4b78eef7318cf'
PINNED_QUESTION_SHA = 'de3304da797dcd388191fae5fba67c9c7ed3310cf3156f97d65a819a288edc17'
SCHEMA = 'archeolog_outcome_admission_v1'
OBS_KEYS = ('observed_at', 'runtime', 'movement', 'archaeology', 'channel_ages', 'source')
MOVE_ACTIONS = {'forward_short', 'forward_long', 'flight'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def slim_observation(row):
    """Keep independent measurements, never pixels, packets, or private files."""
    if not isinstance(row, dict):
        return None
    result = {k: row[k] for k in OBS_KEYS if k in row}
    if not result.get('movement') or not result.get('archaeology'):
        return None
    result['archaeology'] = {k: row['archaeology'][k] for k in (
        'sequence', 'client_uptime_ms', 'world', 'site_id', 'successful_surveys',
        'last_survey_uptime_ms', 'looted_finds', 'races', 'casting', 'mounted',
        'flying', 'falling', 'can_survey') if k in row['archaeology']}
    return result


def slim_step(step):
    keys = ('index', 'started_at', 'finished_at', 'action', 'phase', 'choice',
            'request', 'response', 'model', 'decision', 'guide', 'target',
            'completed', 'executed', 'failure', 'local_failure', 'outcome',
            'confirmed_looted_find', 'gathering_cast_started', 'code_commit',
            'assisted', 'manual_input', 'supervisor_input', 'interventions', 'state')
    row = {k: step[k] for k in keys if k in step}
    row['before'] = slim_observation(step.get('before'))
    row['after'] = slim_observation(step.get('after'))
    # Retain that an input actually happened, without retaining input geometry.
    row['input_evidence'] = bool(step.get('inputs') or step.get('input')
                                 or step.get('gathering_cast_started'))
    if isinstance(row.get('decision'), dict):
        row['decision'] = {k: row['decision'][k] for k in
                           ('request', 'response', 'choice', 'state', 'observed_state')
                           if k in row['decision']}
    return row


def public_question(step, request):
    question = (request.get('questions') or {}).get('action')
    if question:
        return question, 'recorded_original_question'
    # Old navigation service omitted the question in the request. Reconstruct
    # it only when its immutable hash proves the exact candidate schema.
    if request.get('policy') == 'archaeology' and (
            (step.get('model') or {}).get('question_sha256') == PINNED_QUESTION_SHA):
        from tools.client_compatibility.archaeology_policy import question as original
        question = original()
        if hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest() != PINNED_QUESTION_SHA:
            raise ValueError('recorded original question no longer matches pinned hash')
        return question, 'hash_verified_original_navigation_question'
    return None, 'missing_original_candidates'


def distance(a, b):
    if not a or not b or a.get('instance') != b.get('instance'):
        return math.inf
    return math.hypot(a['north'] - b['north'], a['west'] - b['west'])


def bearing_error(observation, target):
    world = observation['archaeology']['world']
    if distance(world, target) == math.inf:
        return math.inf
    angle = math.atan2(target['west'] - world['west'], target['north'] - world['north'])
    return abs((angle - observation['movement']['facing_radians'] + math.pi) % math.tau - math.pi)


def fragments(observation):
    return {r['index']: r['fragments'] for r in observation['archaeology'].get('races', [])}


def verifier(step, action):
    """Return measured reward evidence. Completion booleans alone never suffice."""
    if step.get('failure') or step.get('local_failure'):
        return None, 'runtime_or_action_failure'
    if any(step.get(k) for k in ('assisted', 'manual_input', 'supervisor_input', 'interventions')):
        return None, 'known_intervention'
    before, after = step.get('before'), step.get('after')
    if not before or not after:
        return None, 'missing_before_or_after_observation'
    if before.get('runtime') != after.get('runtime') or not before.get('runtime'):
        return None, 'client_lifetime_changed_or_missing'
    start = step.get('started_at', before['observed_at'])
    finish = step.get('finished_at', after['observed_at'])
    if (not 0 <= start - before['observed_at'] <= 2.5
            or after['observed_at'] <= before['observed_at']
            or after['observed_at'] > finish + 2.5):
        return None, 'stale_or_nonmonotonic_observations'
    for row in (before, after):
        ages = row.get('channel_ages') or {}
        if any(isinstance(v, (int, float)) and v > 2.5 for v in ages.values()):
            return None, 'stale_public_channel'
        if not row['movement'].get('in_world') or row['movement'].get('dead'):
            return None, 'unavailable_client'
    for channel in ('movement', 'archaeology'):
        if after[channel].get('client_uptime_ms', 0) <= before[channel].get('client_uptime_ms', 0):
            return None, 'unchanged_or_missing_public_frame'
    b, a = before['archaeology'], after['archaeology']
    if action in ('loot', 'mouseover_interact', 'interact', 'loot_all', 'take_all'):
        delta = {k: v - fragments(before).get(k, v) for k, v in fragments(after).items()}
        if (sum(max(0, v) for v in delta.values()) > 0
                and a.get('looted_finds', 0) > b.get('looted_finds', 0)
                and step.get('input_evidence')):
            return {'kind': 'interaction_fragment_increase', 'reward': 1.,
                    'fragment_deltas': delta, 'find_delta': a['looted_finds'] - b['looted_finds']}, None
        return None, 'pickup_not_independently_attributed'
    if action == 'survey':
        if (b.get('site_id') == a.get('site_id')
                and a.get('successful_surveys', 0) > b.get('successful_surveys', 0)
                and b.get('last_survey_uptime_ms', 0) < a.get('last_survey_uptime_ms', 0)
                and before['movement'].get('client_uptime_ms', math.inf) - 1000
                <= a['last_survey_uptime_ms'] <= after['movement']['client_uptime_ms'] + 1000
                and step.get('input_evidence')):
            return {'kind': 'fresh_successful_survey', 'reward': .2,
                    'survey_delta': a['successful_surveys'] - b['successful_surveys']}, None
        return None, 'survey_not_fresh_or_not_successful'
    target = (step.get('guide') or {}).get('world')
    if action == 'flight':
        target = step.get('target') or target
    if action in MOVE_ACTIONS or action in ('turn_left', 'turn_right'):
        if not isinstance(target, dict) or not all(k in target for k in ('instance', 'north', 'west')):
            return None, 'missing_retained_destination'
        # The target is fixed from the chosen pre-action guide. Never substitute
        # the post-action next marker or choose whichever endpoint improved.
        if b.get('site_id') != a.get('site_id') and action != 'flight':
            return None, 'site_changed_during_local_approach'
        if action in MOVE_ACTIONS:
            d0, d1 = distance(b.get('world'), target), distance(a.get('world'), target)
            if math.isfinite(d0) and math.isfinite(d1) and d0 - d1 > .5:
                return {'kind': 'retained_destination_approach', 'reward': min(.2, (d0 - d1) / 100),
                        'before_yards': d0, 'after_yards': d1, 'destination': target}, None
            return None, 'no_measured_approach'
        e0, e1 = bearing_error(before, target), bearing_error(after, target)
        if math.isfinite(e0) and math.isfinite(e1) and e0 - e1 > .10:
            return {'kind': 'retained_destination_bearing', 'reward': min(.1, (e0 - e1) / math.pi),
                    'before_radians': e0, 'after_radians': e1, 'destination': target}, None
        return None, 'no_measured_bearing_improvement'
    if action.startswith('portal') or action == 'taxi':
        target = step.get('target')
        endpoint = None
        name = None
        if isinstance(target, dict):
            endpoint, name = target.get('to'), target.get('destination')
        if isinstance(target, list) and len(target) == 2:
            endpoint, name = target[1].get('point'), target[1].get('name')
        if (endpoint and name and distance(b.get('world'), endpoint) > 100
                and distance(a.get('world'), endpoint) < 35
                and step.get('completed')):
            return {'kind': 'named_transport_arrival', 'reward': .5,
                    'destination_name': name, 'destination': endpoint}, None
        return None, 'named_transport_not_confirmed'
    return None, 'no_reviewed_outcome_verifier'


def candidate(step, source):
    decision = step.get('decision') or step
    request = decision.get('request') or {}
    action = decision.get('choice') or step.get('action') or step.get('choice')
    question, question_source = public_question(step, request)
    uid = digest({'request': request, 'action': action,
                  'started_at': step.get('started_at'),
                  'before_at': (step.get('before') or {}).get('observed_at')})
    result = {'id': uid, 'source': source, 'action': action}
    if not request.get('state') or not question or question.get('type') != 'choice':
        return result, question_source if not question else 'missing_original_state'
    criteria = question.get('criteria')
    if not isinstance(criteria, dict) or len(criteria) < 2 or action not in criteria:
        return result, 'invalid_original_candidates'
    full = decision.get('observed_state') or step.get('state') or decision.get('state') or {}
    state = request['state']
    missing_pickup = (bool(full.get('pending_pickup') or (full.get('pickup') or {}).get('uncollected'))
                      and not (state.get('pending_pickup') or state.get('artifact_visible')
                               or (state.get('pickup') or {}).get('uncollected')))
    if missing_pickup and (action in ('flight', 'taxi', 'survey') or str(action).startswith('portal')):
        return result, 'omitted_pending_pickup_fact'
    response = decision.get('response') or {}
    if any(x.get('truncated_fields') for x in (response.get('token_budget') or {}).values()):
        return result, 'recorded_truncated_context'
    measured, rejection = verifier(step, action)
    if rejection:
        return result, rejection
    before = step['before']
    lifetime = digest(before['runtime'])[:16]
    site = before['archaeology'].get('site_id')
    episode = str(PurePosixPath(source['member']).parent)
    # A whole client lifetime is held out together. Episode/site identities are
    # retained for reporting; no adjacent-action random split is permitted.
    result.update(state=request['state'], question=question, label=action,
                  input_sha256=digest({'state': request['state'], 'question': question}),
                  question_source=question_source, outcome=measured,
                  client_lifetime=lifetime, site_id=site, episode=episode,
                  started_at=step.get('started_at', before['observed_at']),
                  recorded_model=decision.get('model') or step.get('model') or request.get('model'),
                  omitted_context_keys=sorted(set(full) - set(state)),
                  attribution='unknown_interventions_in_historical_archive',
                  admission='provisional_measured_outcome_sft', rlvr_eligible=False,
                  synthetic=False)
    return result, None


def rlvr_admission(trajectory):
    """Fail closed on future rollout records; historical SFT rows cannot pass.

    This admits a measured transition for RL experimentation, not an automatic
    model update. Runtime errors/stale telemetry are quarantined instead of
    becoming a reward that teaches the policy to exploit an observer failure.
    """
    attribution = trajectory.get('intervention_ledger') or {}
    if attribution.get('complete') is not True or attribution.get('events') != []:
        return None, 'rlvr_intervention_ledger_incomplete_or_assisted'
    policy = trajectory.get('policy') or {}
    if not all(isinstance(policy.get(key), str) and len(policy[key]) == 64
               and all(char in '0123456789abcdef' for char in policy[key])
               for key in ('weights_sha256', 'config_sha256')):
        return None, 'rlvr_policy_identity_missing'
    if (trajectory.get('transition_gap_free') is not True or trajectory.get('terminal_state')
            not in ('progress', 'clear', 'no_progress', 'death', 'interrupted')):
        return None, 'rlvr_trajectory_gap_or_terminal_state_missing'
    probability = trajectory.get('selected_action_probability')
    if not isinstance(probability, (int, float)) or not math.isfinite(probability) or not 0 < probability <= 1:
        return None, 'rlvr_original_action_probability_missing'
    step = trajectory.get('transition') or {}
    request = step.get('request') or {}
    question = (request.get('questions') or {}).get('action') or {}
    options = question.get('criteria') or {}
    action = step.get('action')
    if not isinstance(options, dict) or len(options) < 2 or action not in options or not request.get('state'):
        return None, 'rlvr_original_complete_input_missing'
    distribution = trajectory.get('behavior_policy_probabilities') or {}
    if (trajectory.get('rollout_source') != 'on_policy' or set(distribution) != set(options)
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
                   for v in distribution.values())
            or abs(sum(distribution.values()) - 1.) > .0001
            or abs(distribution.get(action, -1.) - probability) > .000001):
        return None, 'rlvr_on_policy_distribution_missing_or_inconsistent'
    if trajectory.get('input_sha256') != digest({'state': request['state'], 'question': question}):
        return None, 'rlvr_input_identity_mismatch'
    if not step.get('input_evidence'):
        return None, 'rlvr_executed_input_evidence_missing'
    reward, reason = verifier(step, action)
    if reason in ('no_measured_approach', 'no_measured_bearing_improvement'):
        reward = {'kind': 'valid_executed_no_progress', 'reward': 0.}
        reason = None
    if reason:
        return None, reason
    return {'schema': 'archeolog_rlvr_verified_transition_v1', 'input_sha256': trajectory['input_sha256'],
            'policy': policy, 'action': action, 'selected_action_log_probability': math.log(probability),
            'outcome': reward, 'terminal_state': trajectory['terminal_state'],
            'assistance': 'complete_ledger_no_interventions'}, None


def archive_rows(path, repo, limits):
    import dvc.api
    observations, steps = {}, []
    stats = Counter()
    with dvc.api.open(path, repo=str(repo), mode='rb') as stream:
        with tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for member in archive:
                stats['members'] += 1
                if not member.isfile() or not member.name.endswith('.json'):
                    continue
                if member.size > limits['maximum_json_bytes']:
                    stats['oversized_json_skipped'] += 1
                    continue
                stats['json_members'] += 1
                data = json.load(archive.extractfile(member))
                if not isinstance(data, dict):
                    stats['nonobject_json_skipped'] += 1
                    continue
                name = PurePosixPath(member.name)
                if name.name in ('before.json', 'after.json', 'precheck.json'):
                    row = slim_observation(data)
                    if row:
                        observations[str(name)] = row
                if isinstance(data.get('steps'), list):
                    for step in data['steps']:
                        if isinstance(step, dict) and (step.get('request') or step.get('decision')):
                            steps.append((slim_step(step), member.name))
                if name.name == 'decision.json' and (data.get('request') or data.get('decision')):
                    steps.append((slim_step(data), member.name))
    for step, member in steps:
        parent = PurePosixPath(member).parent
        step['before'] = step.get('before') or observations.get(str(parent / 'before.json'))
        step['after'] = step.get('after') or observations.get(str(parent / 'after.json'))
        if step.get('before') and not step.get('started_at'):
            step['started_at'] = step['before']['observed_at']
        yield step, member, stats


def group_splits(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['client_lifetime']].append(row)
    ordered = sorted(groups, key=lambda group: min(r['started_at'] for r in groups[group]))
    splits = {'train': [], 'validation': [], 'test': []}
    for index, group in enumerate(ordered):
        split = ('test' if len(ordered) >= 2 and index == len(ordered) - 1 else
                 'validation' if len(ordered) >= 3 and index == len(ordered) - 2 else 'train')
        splits[split].extend(groups[group])
    # Do not let the same named digsite appear on both sides merely because
    # the client was restarted. Purge overlapping known sites from training.
    held_sites = {r['site_id'] for name in ('validation', 'test') for r in splits[name]
                  if r['site_id'] is not None}
    purged = [r for r in splits['train'] if r['site_id'] in held_sites]
    splits['train'] = [r for r in splits['train'] if r['site_id'] not in held_sites]
    return splits, groups, purged


def split_summary(splits, groups, purged):
    return {'client_lifetimes': len(groups),
            'split_counts': {k: len(v) for k, v in splits.items()},
            'split_groups': {k: sorted({r['client_lifetime'] for r in v}) for k, v in splits.items()},
            'split_actions': {k: dict(Counter(r['label'] for r in v)) for k, v in splits.items()},
            'split_known_sites': {k: sorted({r['site_id'] for r in v if r['site_id'] is not None}) for k, v in splits.items()},
            'site_overlap_train_purged_count': len(purged),
            'site_overlap_train_purged_ids': [r['id'] for r in purged],
            'missing_site_ids_by_split': {k: sum(r['site_id'] is None for r in v) for k, v in splits.items()},
            'split_rule': 'Whole client lifetimes, chronological test; validation only with at least three lifetimes. Purge training rows at known held-out sites. Unknown site IDs remain explicitly unknown.'}


def resplit(output):
    dataset = json.loads((output / 'dataset.json').read_text())
    rows = [row for values in dataset['splits'].values() for row in values]
    splits, groups, purged = group_splits(rows)
    dataset['splits'] = splits
    audit = json.loads((output / 'audit.json').read_text())
    audit.update(split_summary(splits, groups, purged))
    write(output / 'dataset.json', dataset)
    write(output / 'audit.json', audit)
    print(json.dumps(split_summary(splits, groups, purged), indent=2))


def build(args):
    import yaml
    config = json.loads(args.config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = sorted(args.repo.glob('artifacts/client_harness/whitemane_live_*.tar.gz.dvc'))
    accepted, quarantine, inventory = {}, {}, []
    total_seen = 0
    for pointer in paths:
        metadata = yaml.safe_load(pointer.read_text())['outs'][0]
        path = str(pointer.with_suffix('').relative_to(args.repo))
        source = {'archive': path, 'archive_md5': metadata['md5']}
        local = Counter()
        stats = Counter()
        for step, member, stats in archive_rows(path, args.repo, config):
            total_seen += 1
            row, rejected = candidate(step, {**source, 'member': member})
            local['candidates'] += 1
            if rejected:
                quarantine.setdefault(row['id'], {**row, 'reason': rejected})
                local['quarantined'] += 1
            else:
                accepted.setdefault(row['id'], row)
                local['admitted'] += 1
        inventory.append({**source, 'bytes': metadata['size'], **stats, **local})
        print(json.dumps({'archive': path, **local, 'unique_admitted_so_far': len(accepted)}), flush=True)
    # Dedup identical pre-action inputs globally. Repeated snapshots are not
    # independent examples and cannot cross the lifetime split boundary.
    inputs = defaultdict(list)
    for row in accepted.values():
        inputs[row['input_sha256']].append(row)
    rows = []
    conflicts = 0
    for values in inputs.values():
        if len({r['label'] for r in values}) > 1:
            conflicts += len(values)
            for row in values:
                quarantine[row['id']] = {k: row[k] for k in ('id', 'source', 'action')}
                quarantine[row['id']]['reason'] = 'conflicting_success_actions_same_input'
        else:
            rows.append(min(values, key=lambda r: (r['started_at'], r['id'])))
    splits, groups, purged = group_splits(rows)
    summary = {'schema': SCHEMA, 'archives': len(inventory), 'archive_inventory': inventory,
               'candidate_occurrences': total_seen,
               'unique_measured_outcome_actions': len(accepted),
               'deduplicated_inputs': len(rows), 'conflicting_success_actions': conflicts,
               'quarantine_unique': len(set(quarantine) - set(accepted)),
               'quarantine_reasons': dict(Counter(r['reason'] for uid, r in quarantine.items() if uid not in accepted)),
               'actions': dict(Counter(r['label'] for r in rows)),
               'verifiers': dict(Counter(r['outcome']['kind'] for r in rows)),
               'sites': sorted({r['site_id'] for r in rows if r['site_id'] is not None}),
               **split_summary(splits, groups, purged),
               'trusted_unassisted_rlvr_trajectories': 0,
               'training_kind': 'outcome_filtered_supervised_warm_start',
               'attribution_limit': 'Historical intervention coverage is incomplete; every admitted row is provisional SFT only.',
               'metric_limit': 'Approach and bearing are local progress, not proof of find recovery or optimal action.',
               'snapshot_dedup_rule': 'Globally dedup exact original state/question; quarantine conflicting observed success labels.'}
    write(output / 'dataset.json', {'schema': SCHEMA, 'splits': splits})
    write(output / 'audit.json', summary)
    with (output / 'quarantine.jsonl').open('w') as handle:
        for uid, row in sorted(quarantine.items()):
            if uid not in accepted:
                handle.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'archive_inventory'}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/client_harness/archeolog_v0.json'))
    parser.add_argument('--resplit-existing', action='store_true')
    args = parser.parse_args()
    resplit(args.output) if args.resplit_existing else build(args)


if __name__ == '__main__':
    main()
