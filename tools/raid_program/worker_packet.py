"""Assemble one small implementation packet from the admitted plan and source."""
import json
import textwrap
from pathlib import Path

from tools.raid_program import development_graph as graph


def validate_context(root: Path, context: dict) -> dict:
    if not isinstance(context, dict) or context.get('kind') not in ('implementation', 'observation'):
        raise graph.GraphError('worker_context needs kind implementation or observation')
    for key in ('question', 'decision', 'counterexample'):
        if not isinstance(context.get(key), str) or not context[key].strip():
            raise graph.GraphError('worker_context missing ' + key)
    sources = context.get('native_behavior')
    if not isinstance(sources, list) or not sources:
        raise graph.GraphError('worker_context needs exact native behavior excerpts')
    excerpts = []
    for ref in sources:
        path = graph.file_ref(root, ref)
        start, end = ref.get('start_line'), ref.get('end_line')
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise graph.GraphError('native behavior excerpt requires a valid line range')
        lines = path.read_text().splitlines()
        if end > len(lines) or end - start >= 80:
            raise graph.GraphError('native behavior excerpt is missing or too broad; select the relevant function')
        excerpts.append(dict(ref, text=textwrap.dedent('\n'.join(lines[start-1:end]))))
    fixture = context.get('fixture')
    if not isinstance(fixture, dict):
        raise graph.GraphError('worker_context needs an existing deterministic fixture reference')
    graph.file_ref(root, fixture)
    if context['kind'] == 'observation':
        observation = context.get('observation_decision')
        if not isinstance(observation, dict) or any(not isinstance(observation.get(k), str)
                or not observation[k].strip() for k in ('signal', 'if_confirmed', 'if_refuted', 'live_check')):
            raise graph.GraphError('observation patch must name signal, if_confirmed, if_refuted and live_check')
    result = dict(context, native_behavior=excerpts)
    if len(json.dumps(result).encode()) > 6000:
        raise graph.GraphError('worker context exceeds 6000 bytes; narrow excerpts without dropping constraints')
    return result


def packet(root: Path) -> dict:
    state = graph.read(root / graph.STATE_PATH)
    graph.check_state(root, state)
    g = state['development_graph']
    if g['stage'] != 'implement' or not g.get('assignment'):
        raise graph.GraphError('worker packet requires an admitted implementation plan')
    assignment = g['assignment']
    source = graph.source_binding(root, assignment)
    context = assignment.get('worker_context')
    if context is None:
        raise graph.GraphError('plan lacks worker_context: bind question, decision, native_behavior line/hash refs, '
                               'counterexample and fixture before dispatch; observation work also needs observation_decision')
    context = validate_context(root, context)
    result = {'schema': 'raid_worker_packet_v1', 'unit_id': g['unit']['id'],
              'parent_objective': g['objective'], 'encounter': g['encounter'],
              'open_requirements': [k for k, v in g['requirements'].items() if v['status'] == 'open'],
              'source_commit': source, 'base_commit': assignment['base_commit'],
              'validation_identity': assignment['validation_identity'],
              'plan_receipt': g.get('receipts', {}).get('plan'),
              'coordinator_worktree': str(root.resolve()),
              'first_broken_edge': g['unit']['edge'], 'hypothesis': assignment['hypothesis'],
              'owned_files': assignment['owned_files'],
              'forbidden_changes': assignment['forbidden_changes'],
              'required_test_commands': assignment['required_test_commands'],
              'acceptance_conditions': assignment['acceptance_conditions'],
              'context': context,
              'return': 'Freeze files; report changes, tests and unknowns. Ask the coordinator to amend-tests '
                        'for needed fixture dependencies. Preserve those edits. No nested workers.',
              'behavioral_validation': 'Execute the counterexample and valid neighbor. Repeat state updates '
                        'without changing identity. Text assertions alone are insufficient.',
              'evidence_rule': 'Use compact comparisons. Each deeper read must change a named decision. '
                               'Excerpt indentation is normalized; file hashes bind original bytes.'}
    if len(json.dumps(result).encode()) > 10000:
        raise graph.GraphError('worker packet exceeds 10000 bytes; narrow the unit, do not truncate')
    return result
