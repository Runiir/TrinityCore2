"""Compare identical legal questions with real, blank and absent game images."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from . import runtime, dig_decisions, decision_backend as backend
from .vision_benchmark import call


def run(output):
    if output.exists() or not output.resolve().is_relative_to(runtime.ROOT / 'evidence'):
        raise ValueError('ablation requires new public evidence')
    failure = json.loads((runtime.ROOT /
        'evidence/vision_201m_20261006_02/first_live_failure.json').read_text())
    original = failure['last_dig_steps'][-1]['request']
    captured = {}
    def shadow(state, instructions, options):
        captured.update(model=backend.VISION_MODEL, state=state, questions={'action': {
            'type': 'choice', 'instructions': instructions, 'criteria': options}})
        return 'observe', {}, {}
    # Build the real controller's updated question without permitting an input.
    with patch.object(dig_decisions.laya_ui, 'choose', shadow):
        dig_decisions.choose(original['state'])
    questions = {'original_dig_goal': original, 'clarified_dig_goal': captured}
    results = {name: call('/v1/diagnostic', question) for name, question in questions.items()}
    report = {'questions': questions, 'results': results, 'gameplay_inputs': 0,
        'note': 'Each question is compared on one fresh frame with real/blank/no image. '
                'The scene is current; the retained digging scenario is from the stopped trial. '
                'This is a prompt/image sensitivity diagnostic, not an exact original-frame replay.'}
    output.mkdir(parents=True)
    runtime.write(output / 'ablation.json', report)
    return {name: {mode: {'choice': response['answers']['action']['choice'],
        'probabilities': response['answers']['action']['probabilities'],
        'ms': round(response['elapsed_sec'] * 1000, 1)}
        for mode, response in result['cases'].items()} for name, result in results.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output)))
