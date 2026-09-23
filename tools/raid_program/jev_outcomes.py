"""Measure optional model picks between the top-2 ranked damage gaps.

Jev and Laya are advisory and never required. Laya shadows Jev on the same
packet; record both picks (omit a model that was not run or was offline). The
party and per-actor deltas and their noise verdicts are computed from the
scoreboard (`compare_labels(label_after vs label_before)`), never typed in:

    pixi run python -m tools.raid_program.jev_outcomes append --unit U \
      --candidate gapA --candidate gapB --jev-pick gapA --laya-pick gapB --chosen gapA \
      --label-before L0 --label-after L1
    pixi run python -m tools.raid_program.jev_outcomes summary
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = Path('artifacts/cata_raid_program/jev_pick_outcomes.jsonl')
INPUTS = ('unit', 'candidates', 'jev_pick', 'laya_pick', 'chosen', 'label_before', 'label_after')
MODELS = ('jev', 'laya')


def _number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate(record: dict) -> dict:
    if not isinstance(record, dict) or not set(INPUTS) <= set(record) <= {*INPUTS, 'scenario'}:
        raise ValueError('record needs exactly: ' + ', '.join(INPUTS) + ' (optional scenario)')
    for key in ('unit', 'chosen', 'label_before', 'label_after'):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(key + ' must be a non-empty string')
    if record['label_before'] == record['label_after']:
        raise ValueError('label_before and label_after must differ')
    candidates = record['candidates']
    if (not isinstance(candidates, list) or len(candidates) != 2 or len(set(candidates)) != 2
            or not all(isinstance(c, str) and c for c in candidates)):
        raise ValueError('candidates must be the two distinct top-ranked damage gaps')
    if record['chosen'] not in candidates:
        raise ValueError('chosen must be one of the candidates')
    picks = [record[model + '_pick'] for model in MODELS]
    if all(pick is None for pick in picks):
        raise ValueError('record at least one model pick (jev_pick or laya_pick)')
    if any(pick is not None and pick not in candidates for pick in picks):
        raise ValueError('each model pick must be null or one of the candidates')
    return record


def active_scenario(root: Path) -> str:
    from tools.raid_program import development_graph as graph
    from tools.raid_program.graph_acceptance import target_pointer
    return target_pointer(graph.read(root / graph.STATE_PATH)['development_graph'])['scenario']


def measured_deltas(root: Path, scenario: str, label_before: str, label_after: str) -> dict:
    """Party and per-actor deltas with noise verdicts, straight from the scoreboard."""
    from tools.raid_program.scoreboard import compare_labels
    comparison = compare_labels(root, scenario, label_after, label_before)
    party = comparison.get('party') or {}
    actors = comparison.get('actors') or {}
    if not _number(party.get('delta')) or not isinstance(party.get('verdict'), str):
        raise ValueError('compare_labels returned no party delta/verdict (need kills on both labels)')
    return {'party_delta': party['delta'], 'party_noise': party['verdict'],
            'actor_delta': {a: row.get('delta') for a, row in actors.items()},
            'actor_noise': {a: row.get('verdict') for a, row in actors.items()}}


def append(root: Path, record: dict) -> dict:
    record = validate(dict(record))
    scenario = record.pop('scenario', None) or active_scenario(root)
    row = {**record, 'scenario': scenario,
           **measured_deltas(root, scenario, record['label_before'], record['label_after']),
           'recorded_at': datetime.now(timezone.utc).isoformat()}
    path = root / PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def _group(rows: list[dict]) -> dict:
    deltas = [r['party_delta'] for r in rows if _number(r.get('party_delta'))]
    return {'n': len(rows), 'mean_party_delta': sum(deltas) / len(deltas) if deltas else None,
            'party_improved': sum(r.get('party_noise') == 'improved' for r in rows),
            'party_regressed': sum(r.get('party_noise') == 'regressed' for r in rows)}


def summary(root: Path) -> dict:
    """Per model: scoreboard outcome when its pick was followed versus overridden."""
    path = root / PATH
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []
    result = {'records': len(rows)}
    for model in MODELS:
        picked = [r for r in rows if r.get(model + '_pick') is not None]
        result[model] = {'n': len(picked),
                         'followed': _group([r for r in picked if r['chosen'] == r[model + '_pick']]),
                         'overridden': _group([r for r in picked if r['chosen'] != r[model + '_pick']])}
    both = [r for r in rows if r.get('jev_pick') is not None and r.get('laya_pick') is not None]
    result['jev_laya_agreement'] = {'n': len(both), 'agree': sum(r['jev_pick'] == r['laya_pick'] for r in both)}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('append', help='Record one measured model pick')
    add.add_argument('--unit', required=True)
    add.add_argument('--candidate', action='append', required=True, dest='candidates')
    add.add_argument('--jev-pick', help='Omit when Jev was not run or was offline')
    add.add_argument('--laya-pick', help='Omit when Laya was not run or was offline')
    add.add_argument('--chosen', required=True)
    add.add_argument('--label-before', required=True)
    add.add_argument('--label-after', required=True)
    add.add_argument('--scenario', help='Default: the active graph scenario')
    commands.add_parser('summary', help='Compare outcomes when each model pick was followed or overridden')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'summary':
            result = summary(root)
        else:
            record = {'unit': args.unit, 'candidates': args.candidates, 'jev_pick': args.jev_pick,
                      'laya_pick': args.laya_pick, 'chosen': args.chosen,
                      'label_before': args.label_before, 'label_after': args.label_after}
            if args.scenario:
                record['scenario'] = args.scenario
            result = append(root, record)
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
