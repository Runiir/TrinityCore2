"""Shadow-test Laya's action selection separately from the guided live harness.

All requests go to the pinned local model. No game inputs or server mutations
are performed. Labels are scored against the explicit telescope control policy,
not against private archaeology target coordinates.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request
from dvclive import Live

from . import lab_runtime as lab
from .archaeology_controller import MODEL, REVISION, ENDPOINT, DESCRIPTIONS

CONFIG = lab.REPO / 'experiments/configs/client_harness/laya_archaeology_eval_v1.json'


def state_from_step(steps, index):
    step = steps[index]
    tcp, observation = step['tcp'], step['observation']
    prior = [s for s in steps[:index] if s.get('tcp', {}).get('session') == tcp['session']]
    last_survey = next((s for s in reversed(prior) if s['executed'] == 'survey'), None)
    after = prior[prior.index(last_survey) + 1:] if last_survey else prior
    walked = any(s['executed'].startswith('forward_') for s in after)
    tool = tcp['tool']
    current = bool(last_survey and tool and tool['seen_at'] >= last_survey['started_at'] and not walked)
    return {'task': 'Find an archaeology artifact in the current digsite.',
        'available': observation['in_world'] and not observation['dead'] and not observation['in_combat'] and not observation['on_taxi'],
        'casting': False, 'player_facing_radians': observation['facing_radians'],
        'instrument_current': current,
        'telescope': {k: tool[k] for k in ['color', 'heading_radians', 'turn_error_radians']} if tool else None,
        'last_actions': [s['executed'] for s in prior[-3:]]}


def expected(state, threshold=.1):
    if not state['available'] or state['casting']: return 'observe', ['observe']
    tool = state['telescope']
    if not state['instrument_current'] or not tool: return 'survey', ['survey']
    error = tool['turn_error_radians']
    if abs(error) > threshold:
        action = 'turn_left' if error > 0 else 'turn_right'
        return action, [action]
    preferred = 'forward_short' if tool['color'] == 'green' else 'forward_long'
    # Both bounded walking distances make progress when aligned. Report distance
    # preference separately instead of treating every shorter walk as a failure.
    return preferred, ['forward_short', 'forward_long']


def fact_summary(state, threshold=.1):
    summarized = {k: v for k, v in state.items() if k not in ['player_facing_radians', 'telescope']}
    tool = state['telescope']
    if tool:
        error = tool['turn_error_radians']
        summarized['telescope'] = {'color': tool['color'], 'heading_relative_to_player':
            'aligned' if abs(error) <= threshold else 'left_of_player' if error > 0 else 'right_of_player'}
    else: summarized['telescope'] = None
    return summarized


def cases(episode, config):
    begin, end = config['navigation_steps']
    result = [{'id': f'live_{index:02}', 'origin': 'recorded_navigation',
               'step_index': index, 'state': state_from_step(episode['steps'], index)} for index in range(begin, end)]
    for color in config['counterfactual_colors']:
        for error in config['counterfactual_errors']:
            for stale in [False, True]:
                state = {'task': 'Find an archaeology artifact in the current digsite.', 'available': True,
                    'casting': False, 'player_facing_radians': 1.5, 'instrument_current': not stale,
                    'telescope': {'color': color, 'heading_radians': (1.5 + error) % math.tau, 'turn_error_radians': error},
                    'last_actions': ['survey', 'forward_short'] if stale else ['survey']}
                result.append({'id': f'counterfactual_{color}_{error}_{stale}', 'origin': 'counterfactual', 'state': state})
    for mode in ['missing_instrument', 'casting', 'unavailable']:
        state = {'task': 'Find an archaeology artifact in the current digsite.', 'available': mode != 'unavailable',
            'casting': mode == 'casting', 'player_facing_radians': 1.5, 'instrument_current': mode != 'missing_instrument',
            'telescope': None if mode == 'missing_instrument' else {'color': 'green', 'heading_radians': 1.5, 'turn_error_radians': 0},
            'last_actions': ['survey']}
        result.append({'id': mode, 'origin': 'counterfactual', 'state': state})
    for case in result:
        case['expected'], case['progress_actions'] = expected(case['state'], config['alignment_threshold_radians'])
    return result


def request(case, variant, episode, config):
    if variant == 'guided_replay':
        return copy.deepcopy(episode['steps'][case['step_index']]['request'])
    state = case['state'] if variant == 'raw_observations' else fact_summary(case['state'], config['alignment_threshold_radians'])
    instructions = config['instructions'] if variant == 'raw_observations' else config['fact_instructions']
    return {'model': MODEL, 'state': state, 'questions': {'action': {'type': 'choice',
        'instructions': instructions, 'criteria': {key: DESCRIPTIONS[key] for key in config['decision_options']}}}}


def ask(payload):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    started = time.perf_counter()
    with opener.open(req, timeout=15) as response: result = json.load(response)
    duration = time.perf_counter() - started
    if result.get('model') != MODEL or result.get('revision') != REVISION: raise ValueError('unexpected model identity')
    if any(r.get('truncated_fields') for r in result['token_budget'].values()): raise ValueError('truncated model input')
    answer = result['answers']['action']
    if answer['choice'] not in payload['questions']['action']['criteria']: raise ValueError('foreign action')
    return result, duration


def aggregate(rows):
    return {'cases': len(rows), 'preferred_action_accuracy': sum(r['preferred_match'] for r in rows) / len(rows),
        'progress_action_accuracy': sum(r['progress_match'] for r in rows) / len(rows),
        'median_reported_confidence': statistics.median(r['response']['answers']['action']['confidence'] for r in rows),
        'median_request_seconds': statistics.median(r['request_seconds'] for r in rows),
        'failures': [r['case']['id'] for r in rows if not r['progress_match']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    source = lab.ROOT / 'evidence' / config['source_episode']
    episode = json.loads(source.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dataset = cases(episode, config)
    (out / 'cases.json').write_text(json.dumps(dataset, indent=2) + '\n')
    (out / 'source_episode.json').write_text(json.dumps(episode, indent=2) + '\n')
    rows = []
    with (out / 'decisions.jsonl').open('w') as log:
        for variant in config['variants']:
            for case in dataset:
                if variant == 'guided_replay' and case['origin'] != 'recorded_navigation': continue
                payload = request(case, variant, episode, config)
                response, duration = ask(payload)
                choice = response['answers']['action']['choice']
                row = {'variant': variant, 'case': case, 'request': payload, 'response': response,
                    'request_seconds': duration, 'preferred_match': choice == case['expected'],
                    'progress_match': choice in case['progress_actions']}
                rows.append(row); log.write(json.dumps(row) + '\n'); log.flush()
    metrics = {}
    for variant in config['variants']:
        selected = [r for r in rows if r['variant'] == variant]
        metrics[variant] = {'all': aggregate(selected)}
        for origin in ['recorded_navigation', 'counterfactual']:
            subset = [r for r in selected if r['case']['origin'] == origin]
            if subset: metrics[variant][origin] = aggregate(subset)
        unsafe = [r for r in selected if r['case']['expected'] == 'observe']
        metrics[variant]['unsafe_wait_accuracy'] = sum(r['preferred_match'] for r in unsafe) / len(unsafe) if unsafe else None
    with Live(dir=str(out / 'dvclive'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        for variant, groups in metrics.items():
            for group, values in groups.items():
                if isinstance(values, dict):
                    for key in ['cases', 'preferred_action_accuracy', 'progress_action_accuracy', 'median_reported_confidence', 'median_request_seconds']:
                        live.log_metric(f'{variant}/{group}/{key}', values[key])
                elif values is not None: live.log_metric(f'{variant}/{group}', values)
        live.next_step()
    result = {'schema': 'client442_laya_archaeology_shadow_eval_v1', 'model': MODEL, 'revision': REVISION,
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
        'source_episode_sha256': lab.sha256(source), 'config_sha256': lab.sha256(CONFIG),
        'evaluator_sha256': lab.sha256(Path(__file__)), 'game_inputs_performed': False,
        'weights_fine_tuned': False, 'cases_are_independent_live_finds': False, 'live_promotion_performed': False,
        'labels': 'Explicit telescope control policy, no private target coordinates', 'metrics': metrics,
        'original_live_find': {'navigation_actions': 23, 'surveys': 8, 'turns': 8, 'walks': 7,
            'navigation_seconds': episode['steps'][25]['time'] - episode['steps'][3]['started_at'],
            'fragment_quantity': episode['completion']['quantity'], 'loot_coordinates_teacher_supplied': True}}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
