"""Rank observed component differences, without calling unmatched DPS recoverable.

Inputs are an existing bot timeline and a reviewed, normalized WCL comparison.
No capture, simulator generation, or live-server access is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def interval_seconds(intervals, start, end):
    """Union observed duty intervals; overlapping assignments cost time only once."""
    spans = sorted((max(start, x[0]), min(end, x[1])) for x in intervals)
    total, through = 0, start
    for lo, hi in spans:
        if hi > max(lo, through):
            total += hi - max(lo, through)
        through = max(through, hi)
    return total / 1000


def matches(event, component):
    return (event.get('source_is_pet', False) == component.get('owned', False)
            and (component.get('spell_ids') is None
                 or event['spell_id'] in component['spell_ids']))


def compare(timeline, references):
    if any(a.get('duties') for a in references['actors'].values()):
        if references.get('native_identity') != timeline['identity']:
            raise ValueError('Duty annotations must bind to the exact timeline identity')
    window = timeline['window']
    if not window.get('complete'):
        raise ValueError('Requires a closed native damage window')
    lo, hi = window['first_hostile_at_ms'], window['native_boss_death_at_ms']
    elapsed = (hi - lo) / 1000
    if elapsed <= 0:
        raise ValueError('Invalid native elapsed interval')
    summary = timeline['summary']
    actors = []
    for aid, actor in summary['actors'].items():
        reference = references['actors'].get(str(aid))
        rows = [e for e in timeline['events'] if e.get('actor_guid') == int(aid)
                and e['kind'] == 'landed' and lo <= e['at_ms'] <= hi
                and e.get('amount', 0) > 0]
        damage = actor['damage']['hostile_originated']
        if sum(e['amount'] for e in rows) != damage:
            raise ValueError(f'{aid}: landed damage does not reconcile with summary')
        result = dict(actor_guid=int(aid), spec=actor['class_spec'],
                      native_dps=damage / elapsed, native_hps=actor['effective_hps'],
                      status='unmatched' if reference is None else 'comparison_only',
                      recoverable_damage=None, components=[])
        if reference:
            result.update(reference_url=reference['url'],
                          reference_dps=reference['dps'],
                          apparent_dps_gap=reference['dps'] - damage / elapsed,
                          limitations=reference['limitations'],
                          next_check=reference['next_check'],
                          duties=reference.get('duties', []))
            observed = [d['interval_ms'] for d in result['duties']
                        if d.get('provenance') == 'observed' and d.get('interval_ms')]
            result['observed_duty_union_seconds'] = interval_seconds(observed, lo, hi) if observed else None
            result['duty_coverage'] = 'partial' if observed else 'unavailable'
            # Duty duration does not prove casting was impossible throughout it.
            # Never divide total damage (including DoTs/pets) by duty-free time.
            claimed = set()
            for component in reference['components']:
                selected = [i for i, e in enumerate(rows) if matches(e, component)]
                if claimed.intersection(selected):
                    raise ValueError(f'{aid}: overlapping component selectors')
                claimed.update(selected)
                amount = sum(rows[i]['amount'] for i in selected)
                result['components'].append(dict(
                    name=component['name'], native_damage=amount,
                    native_landed_events=len(selected), native_dps=amount / elapsed,
                    reference_dps=component['dps'],
                    apparent_dps_gap=component['dps'] - amount / elapsed,
                    reference_observation=component.get('observation'),
                    recoverable_damage=None))
            result['components'].sort(key=lambda x: -x['apparent_dps_gap'])
        actors.append(result)
    actors.sort(key=lambda x: (-x.get('apparent_dps_gap', float('-inf')), x['actor_guid']))
    return dict(schema='raid_damage_gap_comparison_v1', identity=timeline['identity'],
                window=window, actors=actors, references=references.get('sources', []),
                interpretation='Apparent gaps rank investigation, not fixes or recoverable damage. '
                'Positive components can be offset by stronger components; do not sum as a gain.')


def markdown(report):
    text = ['# Ranked damage comparison', '', report['interpretation'], '',
            '| Actor | Native DPS | WCL DPS | Apparent gap | Observed duty union |',
            '|---|---:|---:|---:|---:|']
    for a in report['actors']:
        ref = f"{a['reference_dps']:,.1f}" if 'reference_dps' in a else 'unmatched'
        gap = f"{a['apparent_dps_gap']:,.1f}" if 'apparent_dps_gap' in a else 'unknown'
        duty = (f"{a['observed_duty_union_seconds']:.3f}s (partial)"
                if a.get('observed_duty_union_seconds') is not None else 'unknown')
        text.append(f"| {a['actor_guid']} {a['spec']} | {a['native_dps']:,.1f} | {ref} | {gap} | {duty} |")
    for a in report['actors']:
        if 'reference_url' not in a:
            continue
        text += ['', f"## {a['actor_guid']} {a['spec']}", '',
                 f"[WCL reference]({a['reference_url']})", '',
                 'Limitations: ' + a['limitations'], '', 'Next check: ' + a['next_check'], '',
                 '| Component | Native DPS | WCL DPS | Apparent gap |',
                 '|---|---:|---:|---:|']
        for c in a['components']:
            text.append(f"| {c['name']} | {c['native_dps']:,.1f} | {c['reference_dps']:,.1f} | {c['apparent_dps_gap']:,.1f} |")
    return '\n'.join(text) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = compare(json.loads(args.timeline.read_text()), json.loads(args.references.read_text()))
    data['inputs'] = {name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                      for name, path in [('timeline', args.timeline), ('references', args.references)]}
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    args.output.with_suffix('.md').write_text(markdown(data))


if __name__ == '__main__':
    main()
