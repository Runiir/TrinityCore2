"""Offline, explicitly synthetic text contracts and strict visual admission.

No capture, live controller, service request, or gameplay input is performed.
Scenario-family holdouts test the contract on unseen synthetic contexts, not
navigation competence or independent real-world outcomes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from tools.client_compatibility import archaeology_policy, travel_policy
from . import guidance_policy

TASKS = {'archaeology': archaeology_policy, 'travel': travel_policy,
         'guidance': guidance_policy}
SCENES = ('coastal plain', 'wooded slope', 'desert basin', 'rocky plateau',
          'marsh edge', 'volcanic foothill')
ACTION_DESCRIPTIONS = {
    'observe': 'Wait while unavailable, casting, or in taxi transit.',
    'survey': 'Cast Survey to reveal the next buried find at this ready digsite position.',
    'inspect': 'Locate a discovered pending artifact whose position is unknown.',
    'loot': 'Collect the discovered artifact in confirmed interaction range.',
    'swim_up': 'Swim toward an artifact above the current depth.',
    'swim_down': 'Swim toward an artifact below the current depth.',
    'forward_short': 'Approach a located artifact outside interaction range.',
    'dismount': 'Dismount on destination ground before collection.',
    'camera_ground': 'Look toward the ground to locate a pending nearby artifact after failed tooltips.'}
ACTION_INSTRUCTIONS = ('Choose the next executable archaeology action from all observed facts. '
    'Wait when unavailable or casting. A buried find requires Survey; inspection and camera '
    'changes cannot reveal it. Collect a pending find before further Survey. Correct a measured '
    'swimming depth gap before horizontal approach. Dismount on destination ground. '
    'If a pending find is not located, inspect. If out of range, approach. '
    'If tooltips missed a pending nearby find with unknown range, look at the ground. '
    'Confirmed interaction range permits collection.')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def action_label(s):
    if not s['available'] or s['casting'] or s['on_taxi']:
        return 'observe'
    if not s['pickup']['uncollected']:
        return 'survey'
    gap = s['artifact_height_error_yards']
    if s['swimming'] and abs(gap) > .5:
        return 'swim_up' if gap > 0 else 'swim_down'
    if s['mounted'] and not s['flying']:
        return 'dismount'
    if not s['artifact_location_known']:
        return 'inspect'
    if s['pickup']['interaction_in_range'] is False:
        return 'forward_short'
    if s['pickup']['interaction_in_range'] is None:
        return 'camera_ground'
    return 'loot'


def action_state(action, family, variant):
    s = {'task': 'recover the next archaeology find', 'available': True,
         'casting': False, 'on_taxi': False, 'can_survey': True, 'survey_ready': True,
         'artifact_visible': True, 'artifact_location_known': True, 'mounted': False,
         'flying': False, 'swimming': False, 'guide_arrived': True,
         'artifact_height_error_yards': 0.,
         'pickup': {'uncollected': True, 'discovery_confirmed': True,
                    'interaction_in_range': True, 'tooltip_search_misses': 0}}
    if action == 'observe':
        s['casting' if variant else 'available'] = bool(variant)
    elif action == 'survey':
        s.update(artifact_visible=False, artifact_location_known=False)
        s['pickup'].update(uncollected=False, discovery_confirmed=False,
                           interaction_in_range=None)
    elif action == 'inspect':
        s.update(artifact_visible=False, artifact_location_known=False)
    elif action in ('swim_up', 'swim_down'):
        s['swimming'] = True
        s['artifact_height_error_yards'] = (1. if action == 'swim_up' else -1.) * (1. + family + variant / 2)
        s['pickup']['interaction_in_range'] = False
    elif action == 'forward_short':
        s['pickup']['interaction_in_range'] = False
        s['artifact_distance_yards'] = 5. + family * 2 + variant
    elif action == 'dismount':
        s['mounted'] = True
    elif action == 'camera_ground':
        s['pickup'].update(interaction_in_range=None, tooltip_search_misses=2 + variant)
    assert action_label(s) == action
    return s


def admit_visual(row, maximum_alignment_seconds=.25):
    """Require immutable, contemporaneous pre-action pixels and attributable label.

    Even an admitted visual supervised row is not an on-policy RLVR trajectory.
    Historical unknown assistance and benchmark captures fail these gates.
    """
    failures = []
    if row.get('source_kind') != 'verified_real_visual':
        failures.append('not_verified_real_visual')
    frame, observation = row.get('frame', {}), row.get('observation', {})
    if not frame.get('sha256') or not frame.get('immutable_member'):
        failures.append('missing_immutable_frame')
    identity = frame.get('runtime_identity')
    if not identity or identity != observation.get('runtime_identity'):
        failures.append('runtime_identity_mismatch')
    ft, ot, at = frame.get('timestamp'), observation.get('timestamp'), row.get('action_timestamp')
    if (not all(isinstance(t, (int, float)) for t in (ft, ot, at))
            or abs(ft - ot) > maximum_alignment_seconds or max(ft, ot) > at):
        failures.append('stale_or_post_action_input')
    if row.get('assistance') != {'ledger_complete': True, 'manual_interventions': 0}:
        failures.append('assistance_unknown_or_present')
    outcome = row.get('outcome', {})
    if not outcome.get('independently_verified') or not outcome.get('immutable_member'):
        failures.append('no_independent_outcome')
    if row.get('label') not in row.get('question', {}).get('criteria', {}):
        failures.append('label_not_original_candidate')
    if not row.get('group_id'):
        failures.append('missing_episode_site_client_group')
    if row.get('input_contains_after_action_facts') is not False:
        failures.append('after_action_fact_status_unknown')
    return {'admitted': not failures, 'failures': failures, 'rlvr_eligible': False}


def input_identity(row, include_scenario=True):
    state = dict(row['state'])
    if not include_scenario:
        state.pop('scenario', None)
    q = row['question']
    return digest({'task': row['task'], 'state': state, 'instructions': q['instructions'],
                   'criteria': q['criteria']})


def validate_splits(splits):
    seen, groups = {}, {}
    for split, rows in splits.items():
        for row in rows:
            if row.get('image') is not None or 'image' in row['state'] or 'images' in row['state']:
                raise ValueError('synthetic rows must never be paired with pixels')
            if row['source_kind'] != 'synthetic_text_only' or row.get('rlvr_eligible') is not False:
                raise ValueError('unexpected data attribution')
            identity = input_identity(row)
            if identity in seen:
                raise ValueError('duplicate original input across or within splits')
            seen[identity] = split
            group = row['group_id']
            if group in groups and groups[group] != split:
                raise ValueError('scenario family crosses split')
            groups[group] = split
            if row['label'] not in row['question']['criteria']:
                raise ValueError('label is not executable candidate')
    return True


def generate(config):
    splits = {name: [] for name in ('train', 'validation', 'test')}
    dedup = set()
    for family, terrain in enumerate(SCENES):
        split = 'train' if family < 4 else 'validation' if family == 4 else 'test'
        rng = random.Random(config['seed'] + family)
        for task, policy in TASKS.items():
            per = config['examples_per_action_per_family']
            source = policy.dataset({'seed': config['seed'] + family * 71,
                'train_per_action': per, 'validation_per_action': 0, 'test_per_action': 0,
                'physical_states_only': True})['train']
            for index, old in enumerate(source):
                state = dict(old['state'])
                # Retain every original fact, including travel physical flags.
                if 'observed_flags' in old:
                    state['observed_flags'] = old['observed_flags']
                state['scenario'] = {'terrain': terrain, 'route_length_yards': 180 + family * 113 + index,
                    'position_elevation_yards': 4 + family * 17 + index / 10}
                row = {'task': task, 'state': state, 'question': old['question'], 'label': old['label']}
                row.update(id=f'{task}-{family}-{index}', group_id=f'synthetic-scene-{family}',
                    source_kind='synthetic_text_only', source=old['source'], rlvr_eligible=False,
                    input_contains_after_action_facts=False)
                if input_identity(row) not in dedup:
                    dedup.add(input_identity(row)); splits[split].append(row)
        for action in ACTION_DESCRIPTIONS:
            for variant in range(config['examples_per_action_per_family']):
                state = action_state(action, family, variant)
                state['scenario'] = {'terrain': terrain, 'position_elevation_yards': family * 17 + variant}
                order = list(ACTION_DESCRIPTIONS); rng.shuffle(order)
                row = {'id': f'action-{family}-{action}-{variant}', 'group_id': f'synthetic-scene-{family}',
                    'task': 'action', 'state': state, 'label': action,
                    'question': {'type': 'choice', 'instructions': ACTION_INSTRUCTIONS,
                                 'criteria': {key: ACTION_DESCRIPTIONS[key] for key in order}},
                    'source_kind': 'synthetic_text_only', 'source': 'reviewable grounded action contract v1',
                    'rlvr_eligible': False, 'input_contains_after_action_facts': False}
                if input_identity(row) not in dedup:
                    dedup.add(input_identity(row)); splits[split].append(row)
    validate_splits(splits)
    core = {key: {input_identity(r, False) for r in rows} for key, rows in splits.items()}
    audit = {'counts': {key: len(rows) for key, rows in splits.items()},
        'by_task': {key: dict(Counter(r['task'] for r in rows)) for key, rows in splits.items()},
        'by_task_action': {key: dict(Counter(r['task'] + '/' + r['label'] for r in rows))
                          for key, rows in splits.items()},
        'groups': {key: sorted({r['group_id'] for r in rows}) for key, rows in splits.items()},
        'input_overlap_train_test': 0, 'group_overlap_train_test': 0,
        'contract_core_overlap_train_test': len(core['train'] & core['test']),
        'verified_visual_examples': 0, 'real_outcome_examples': 0, 'trusted_rlvr_trajectories': 0,
        'limitation': 'Unseen synthetic scene contexts, with shared policy templates and some identical core facts. This is not independent real-world generalization evidence.',
        'promotion_blockers': ['no aligned outcome-labeled visual data',
            'no held-out real visual/task scenarios', 'no unassisted autonomous outcome evaluation']}
    return {'schema': 'vision_task_synthetic_sft_dataset_v1', 'splits': splits, 'audit': audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = generate(json.loads(args.config.read_text()))
    write(args.output, data)
    print(json.dumps(data['audit']), flush=True)


if __name__ == '__main__':
    main()
