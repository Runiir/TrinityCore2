"""Compare explicitly selected WCL U estimates with pinned client effect rolls.

This is a compatibility check, not recovery of a server distribution or proof
that absent mitigation fields mean zero. Inputs preserve those distinctions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from statistics import mean


def compare(client: dict, observations: dict, difficulty_id: int) -> dict:
    rows = client['rows']['SpellEffect']
    samples = [dict(zip(observations['columns'], row, strict=True))
               for row in observations['samples']]
    results = []
    for spell in sorted({row['spell_id'] for row in samples}):
        candidates = [r for r in rows if int(r['SpellID']) == spell
                      and int(r['EffectIndex']) == 0
                      and int(r['DifficultyID']) == difficulty_id]
        if len(candidates) != 1:
            raise ValueError(f'{spell}: require one explicit difficulty/effect row')
        effect = candidates[0]
        if int(effect['Effect']) != 2 or float(effect['EffectBonusCoefficient']) != 0:
            raise ValueError(f'{spell}: unsupported damage formula')
        base, die = int(effect['EffectBasePoints']), int(effect['EffectDieSides'])
        if die < 1:
            raise ValueError(f'{spell}: no positive integer roll')
        amounts = [r['wcl_unmitigated_estimate'] for r in samples
                   if r['spell_id'] == spell and r['wcl_unmitigated_estimate'] is not None]
        if not amounts:
            raise ValueError(f'{spell}: no explicit WCL U estimates')
        results.append(dict(spell_id=spell, client_effect_row=int(effect['ID']),
                            client_roll_min=base+1, client_roll_max=base+die,
                            sample_count=len(amounts), observed_min=min(amounts),
                            observed_max=max(amounts), observed_mean=mean(amounts),
                            outside_client_roll=sum(not base+1 <= v <= base+die for v in amounts)))
    return dict(report=observations['report'], fight=observations['fight'],
                mode=observations['mode'], difficulty_id=difficulty_id, spells=results,
                conclusion='sample_compatibility_only',
                limitations=observations.get('limitations', []))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client', type=Path, required=True)
    p.add_argument('--observations', type=Path, required=True)
    p.add_argument('--difficulty-id', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = compare(json.loads(a.client.read_text()), json.loads(a.observations.read_text()), a.difficulty_id)
    a.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
