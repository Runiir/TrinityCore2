import json
import pytest
from . import decision_backend as backend, runtime, dig_decisions


def enable(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    (tmp_path / 'run').mkdir()
    value = {'kind': 'vision', 'model': backend.VISION_MODEL, 'revision': backend.VISION_REVISION,
             'code_revision': backend.VISION_CODE_REVISION, 'adapter': None}
    (tmp_path / 'run/decision_backend.json').write_text(json.dumps(value))
    return value


@pytest.mark.parametrize('change', [{'revision': 'different'}, {'code_revision': 'different'},
                                 {'model_saw_pixels': False}])
def test_vision_rejects_changed_weights_code_or_missing_pixels(tmp_path, monkeypatch, change):
    expected = enable(tmp_path, monkeypatch)
    response = {**expected, 'model_saw_pixels': True}
    backend.validate(response, expected)
    with pytest.raises(RuntimeError):
        backend.validate({**response, **change}, expected)


def test_vision_dig_receives_full_state_without_legacy_navigation_projection(tmp_path, monkeypatch):
    enable(tmp_path, monkeypatch)
    state = {'task': 'dig', 'available': True, 'casting': False, 'artifact_visible': False,
        'instrument_current': True, 'survey_ready': True, 'can_survey': True,
        'telescope': {'color': 'green', 'heading_relative_to_player': 'aligned'},
        'grounded': True, 'swimming': False, 'guide_arrived': False,
        'extra_observed_facts': {'height_error_yards': 15}}
    monkeypatch.setattr(dig_decisions.decisions, 'choose',
        lambda *_: pytest.fail('vision cannot use the old narrow trained schema'))
    def choose(context, instructions, options):
        assert context == state
        assert {'forward_short', 'forward_long', 'camera_forward', 'observe'} <= options.keys()
        return 'forward_short', {}, {**backend.selected(), 'model_saw_pixels': True}
    monkeypatch.setattr(dig_decisions.laya_ui, 'choose', choose)
    result = dig_decisions.choose(state)
    assert result[0] == 'forward_short' and result[1]['model'] == backend.VISION_MODEL
