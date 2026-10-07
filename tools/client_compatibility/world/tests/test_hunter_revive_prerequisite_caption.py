"""Prerequisite captions must come from the exact actual Hunter entry and page."""
from copy import deepcopy
import pytest
from tools.client_compatibility.review_hunter_revive_prerequisites import public_revive


@pytest.fixture(params=['tame', 'revive'])
def observation(request):
    entry_ref = {'path': '/private/entry/episode.json', 'sha256': 'entry-sha256'}
    actor = {'guid': 6, 'character_name': 'Harnesshunt'}
    runtime = {'worldserver': {'pid': 1}, 'modern_world': {'pid': 2}, 'client': {'pid': 3}}
    fixture = {'path': '/private/preparation/episode.json', 'sha256': 'preparation-sha256'}
    entry = {'actor': actor, 'runtime': runtime, 'fixture_source': fixture,
        'native_session': 'owned-entry01', 'finished_at': 100}
    phase, key = ('await_owned_tame_cast_review', 'fixture_tame_line2') if request.param == 'tame' else (
        'await_owned_revive_cast_review', 'revive_page2_0')
    row = {'id': 982, 'known': True, 'name': 'Revive Pet', 'kind': 'SPELL', 'slot': 30, 'button': 'SpellButton5'}
    detail = {'input_sent': False, 'state': {'source': 'normal_addon_visible_ui_pixels',
        'player': 'Harnesshunt', 'level': 10, 'spellbook_probe': {'skill_line': 2,
            'rows': [{'id': 1515, 'known': True, 'name': 'Tame Beast', 'kind': 'SPELL'}, row]}}}
    recon = {'phase': phase, 'completed': True, 'failure': None, 'started_at': 110, 'finished_at': 120,
        'entry_source': entry_ref, 'native_session': entry['native_session'], 'actor': actor,
        'runtime': runtime, 'fixture_source': fixture, 'spellbook_details': {key: detail}}
    if request.param == 'revive': recon['revive_spell'] = deepcopy(row)
    return entry, recon, entry_ref, key, row


def test_both_closed_native_entry_caption_formats_are_supported(observation):
    entry, recon, ref, _, row = observation
    original = deepcopy(observation)
    assert public_revive(entry, recon, ref) == row
    assert observation == original


@pytest.mark.parametrize('key,value', [('completed', False), ('failure', 'failed'), ('finished_at', None),
    ('phase', 'owned_revive_cast_complete'), ('entry_source', {'path': '/other/entry', 'sha256': 'other'}),
    ('native_session', 'other-entry'), ('runtime', {}), ('actor', {'guid': 5}), ('fixture_source', {}),
    ('started_at', 99)])
def test_other_partial_or_failed_observation_cannot_authorize_prerequisite(observation, key, value):
    entry, recon, ref, _, _ = observation
    recon[key] = value
    with pytest.raises(RuntimeError): public_revive(entry, recon, ref)


@pytest.mark.parametrize('key,value', [('known', False), ('known', 1), ('name', 'Tame Beast'),
    ('kind', 'FUTURESPELL'), ('id', 1515)])
def test_actual_982_row_must_be_known_revive_spell(observation, key, value):
    entry, recon, ref, detail, _ = observation
    recon['spellbook_details'][detail]['state']['spellbook_probe']['rows'][1][key] = value
    with pytest.raises(RuntimeError): public_revive(entry, recon, ref)


@pytest.mark.parametrize('fault', ['missing_page', 'duplicate_row', 'other_player', 'other_level',
    'other_line', 'different_source', 'page_input'])
def test_caption_requires_the_recorded_stock_beast_mastery_page(observation, fault):
    entry, recon, ref, key, row = observation
    detail = recon['spellbook_details'][key]
    state = detail['state']
    if fault == 'missing_page': recon['spellbook_details'].clear()
    elif fault == 'duplicate_row': state['spellbook_probe']['rows'].append(deepcopy(row))
    elif fault == 'other_player': state['player'] = 'UserHunter'
    elif fault == 'other_level': state['level'] = 11
    elif fault == 'other_line': state['spellbook_probe']['skill_line'] = 1
    elif fault == 'different_source': state['source'] = 'synthetic'
    else: detail['input_sent'] = True
    with pytest.raises(RuntimeError): public_revive(entry, recon, ref)


def test_revive_recon_summary_must_equal_the_actual_captured_row():
    entry = {'native_session': 'entry', 'finished_at': 10}
    ref = {'path': '/entry', 'sha256': 'hash'}
    row = {'id': 982, 'known': True, 'kind': 'SPELL', 'name': 'Revive Pet'}
    recon = {'phase': 'await_owned_revive_cast_review', 'completed': True, 'failure': None,
        'started_at': 11, 'finished_at': 12, 'entry_source': ref, 'native_session': 'entry',
        'spellbook_details': {'revive_page2_0': {'input_sent': False, 'state': {
            'source': 'normal_addon_visible_ui_pixels', 'player': 'Harnesshunt', 'level': 10,
            'spellbook_probe': {'skill_line': 2, 'rows': [row]}}}}, 'revive_spell': {**row, 'slot': 30}}
    with pytest.raises(RuntimeError): public_revive(entry, recon, ref)
