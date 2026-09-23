"""Measure optional model picks between the top-2 ranked damage gaps.

Jev and Laya are advisory and never required. Laya shadows Jev on the same
packet; record both picks (null when a model was not run or was offline) and
the scoreboard delta after the measurement, so each model's usefulness can be
compared with the coordinator's choices:

    pixi run python -m tools.raid_program.jev_outcomes append --unit U \
      --candidate gapA --candidate gapB --jev-pick gapA --laya-pick gapB --chosen gapA \
      --label-before L0 --label-after L1 --party-delta 812.5 --actor-delta 403.0
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
FIELDS = ('unit', 'candidates', 'jev_pick', 'laya_pick', 'chosen', 'label_before', 'label_after',
          'party_delta', 'actor_delta')
MODELS = ('jev', 'laya')


def _number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate(record: dict) -> dict:
    if not isinstance(record, dict) or set(record) != set(FIELDS):
        raise ValueError('record needs exactly: ' + ', '.join(FIELDS))
    for key in ('unit', 'chosen', 'label_before', 'label_after'):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(key + ' must be a non-empty string')
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
    if not _number(record['party_delta']):
        raise ValueError('party_delta must be a finite number')
    actor = record['actor_delta']
    if not (_number(actor) or (isinstance(actor, dict) and actor and all(_number(v) for v in actor.values()))):
        raise ValueError('actor_delta must be a finite number or {actor_id: number}')
    return record


def append(root: Path, record: dict) -> dict:
    row = dict(validate(record), recorded_at=datetime.now(timezone.utc).isoformat())
    path = root / PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def _mean(rows: list[dict]) -> float | None:
    return sum(r['party_delta'] for r in rows) / len(rows) if rows else None


def summary(root: Path) -> dict:
    """Per model: party delta when its pick was followed versus overridden."""
    path = root / PATH
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []
    result = {'records': len(rows)}
    for model in MODELS:
        picked = [r for r in rows if r.get(model + '_pick') is not None]
        followed = [r for r in picked if r['chosen'] == r[model + '_pick']]
        overridden = [r for r in picked if r['chosen'] != r[model + '_pick']]
        result[model] = {'n': len(picked),
                         'followed': {'n': len(followed), 'mean_party_delta': _mean(followed)},
                         'overridden': {'n': len(overridden), 'mean_party_delta': _mean(overridden)}}
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
    add.add_argument('--party-delta', type=float, required=True)
    add.add_argument('--actor-delta', required=True, help='Number, or JSON object {actor_id: number}')
    commands.add_parser('summary', help='Compare outcomes when each model pick was followed or overridden')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'summary':
            result = summary(root)
        else:
            result = append(root, {'unit': args.unit, 'candidates': args.candidates, 'jev_pick': args.jev_pick,
                                   'laya_pick': args.laya_pick, 'chosen': args.chosen,
                                   'label_before': args.label_before, 'label_after': args.label_after,
                                   'party_delta': args.party_delta, 'actor_delta': json.loads(args.actor_delta)})
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
