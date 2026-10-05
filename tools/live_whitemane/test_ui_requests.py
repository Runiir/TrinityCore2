import pytest

from .ui_choice import MODEL, validate_ui_request


def request(criteria):
    return {'model': MODEL, 'state': {}, 'questions': {'action': {
        'type': 'choice', 'instructions': 'Choose a legal action.', 'criteria': criteria}}}


@pytest.mark.parametrize('criteria', [{}, [], {'wait': 'Wait'}, ['wait'], ['wait', 'wait']])
def test_rejects_choices_with_fewer_than_two_distinct_candidates(criteria):
    with pytest.raises(ValueError, match='at least two distinct candidates'):
        validate_ui_request(request(criteria))


@pytest.mark.parametrize('criteria', [{'wait': 'Wait', 'continue': 'Continue'}, ['wait', 'continue']])
def test_accepts_supported_choice_formats_without_changing_options(criteria):
    payload = request(criteria)
    assert validate_ui_request(payload) is payload['questions']
    assert payload['questions']['action']['criteria'] is criteria


def test_validates_every_question_in_a_parallel_ui_request():
    payload = request({'wait': 'Wait', 'continue': 'Continue'})
    payload['questions']['camera'] = request(['left'])['questions']['action']
    with pytest.raises(ValueError, match='camera requires at least two distinct candidates'):
        validate_ui_request(payload, allowed_questions=('action', 'camera'))


@pytest.mark.parametrize('change', [{'state': None}, {'questions': None}, {'model': 'other'},
    {'questions': {'action': {'type': 'score', 'instructions': 'Rate it.', 'criteria': [0, 1]}}}])
def test_rejects_malformed_ui_payloads(change):
    payload = request(['wait', 'continue'])
    payload.update(change)
    with pytest.raises(ValueError):
        validate_ui_request(payload)
