"""Select/create a scenario in the existing atomic development state file."""
from __future__ import annotations

import copy
from pathlib import Path

from tools.raid_program import development_graph as graph
from tools.raid_program.scenario_catalog import discover, key, resolve


def make_state(root: Path, encounter: dict, inputs: dict) -> dict:
    scenario_id = key(encounter)
    requirements = {
        'encounter_research': {'status': 'open', 'description': 'Review requested-mode WCL, DBM, client/server values and unresolved contract claims'},
        'native_script': {'status': 'open', 'description': inputs['script']['task'], 'needs_raid': True},
        'roster_setup': {'status': 'open', 'description': 'Bind exact gear/talents/glyphs/consumes/pets and native actor identities for requested raid size'},
        'role_references': {'status': 'open', 'description': 'Match current simulator requests and tank/healer diagnostics to the selected roster'},
        'runtime_scenario': {'status': 'open', 'description': 'Prepare exact-mode route/profile/provisioning, native unlocks and isolated instance ownership', 'needs_raid': True},
        'assignments': {'status': 'open', 'description': 'Implement requested-mode raid assignments and persistent mechanic tasks', 'needs_raid': True},
    }
    for actor in inputs['roster']['actors']:
        actor_id = actor['actor_id']
        requirements['actor_' + actor_id] = {'status': 'open', 'actor_id': actor_id,
            'role': actor['role'], 'spec': actor['class_spec'],
            'description': f"{actor['slot']}: {actor['class_spec'] or 'roster selection required'} behavior and duty-adjusted performance",
            'needs_raid': True, 'needs_performance': True}
    requirements['encounter_performance'] = {'status': 'open', 'description': 'Matched encounter clear, every actor reviewed, performance accepted and evidence published',
        'needs_raid': True, 'needs_performance': True, 'needs_all_actors': True}
    if not inputs['script']['source_present']:
        edge, owner = 'missing_native_boss_script', 'raid-encounter-research'
    elif inputs['research']['fidelity_state'] != 'accepted' or not inputs['script']['audit_current']:
        edge, owner = 'requested_mode_encounter_baseline_unverified', 'raid-encounter-research'
    elif not inputs['roster']['source']:
        edge, owner = 'missing_exact_roster', 'raid-shard-architecture'
    else:
        edge, owner = 'requested_mode_runtime_and_behavior_unverified', 'raid-shard-architecture'
    action = ('Review the bound requested-mode contract and native script; identify the first unresolved dependency. '
              'Use the listed specialist skill and source references. Missing research, roster, simulator, native scripts '
              'or runtime assets are work to implement, not permission to borrow another difficulty. '
              'Keep every actor open; initialize no server or database from this descriptor.')
    unit_id = 'boss:' + scenario_id + ':initial_diagnosis'
    g = {'version': 1, 'revision': 0, 'coordinator_worktree': str(root.resolve()),
         'objective': f"Implement and validate lawful {encounter['boss']} {encounter['mode']} bots across every DPS, tank and healer against matched encounter evidence.",
         'encounter': encounter, 'stage': 'diagnose', 'actor_ids': [a['actor_id'] for a in inputs['roster']['actors']],
         'requirements': requirements, 'unit': {'id': unit_id, 'edge': edge, 'owner_skill': owner, 'requirements': ['encounter_research'], 'next_action': action},
         'completed_measurements': [], 'failures': {}, 'history': [], 'bootstrap_inputs': inputs}
    return {'schema': 'cata_raid_active_work_unit_v1', **encounter,
            'work_unit': unit_id, 'classification': 'scenario_initialization', 'owner_skill': owner,
            'next_action': action, 'ready_for_build': False, 'ready_for_live_verification': False,
            'validation_clock': {'policy': 'completion_watchdog', 'fixed_success_timer_seconds': None},
            'development_graph': g}


def select_state(root: Path, current: dict, encounter: dict) -> dict:
    """Exactly one active state; parked states are inactive, never copied baselines."""
    g = current['development_graph']
    graph.check_state(root, current)
    if Path(g['coordinator_worktree']).resolve() != root.resolve():
        raise graph.GraphError('use the canonical coordinator worktree')
    requested = key(encounter)
    active = key(g['encounter'])
    if requested == active:
        return current
    if g.get('claim') or g['stage'] in ('validate', 'assess', 'publish'):
        raise graph.GraphError('active scenario has an owned or unclosed operation; reconcile it before switching')
    parked = copy.deepcopy(current.get('parked_scenarios', {}))
    if active in parked:
        raise graph.GraphError('duplicate active scenario in parked state')
    previous = copy.deepcopy(current)
    previous.pop('parked_scenarios', None)
    parked[active] = previous
    if requested in parked:
        result = parked.pop(requested)
        graph.check_graph(result['development_graph'])
        if key(result['development_graph']['encounter']) != requested or result['development_graph'].get('claim'):
            raise graph.GraphError('invalid parked scenario identity/ownership')
        if Path(result['development_graph']['coordinator_worktree']).resolve() != root.resolve():
            raise graph.GraphError('parked scenario belongs to a different coordinator worktree')
    else:
        result = make_state(root, encounter, discover(root, encounter))
    result['parked_scenarios'] = parked
    return result


def start(root: Path, request: str, mode: str | None = None, raid: str | None = None,
          preview: bool = False, expected_sha256: str | None = None) -> dict:
    encounter = resolve(root, request, mode, raid)
    if preview:
        return {'requested_scenario': encounter, 'read_only': True, 'inputs': discover(root, encounter)}
    graph.update_state(root, lambda state: select_state(root, state, encounter), expected_sha256)
    return graph.resume(root)
