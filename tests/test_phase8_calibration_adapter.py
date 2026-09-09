"""Read-only gear identity projection; no native actor materialization."""
import copy
import json
from pathlib import Path

import pytest

from tools.bot_ml import phase8_calibration_adapter as adapter
from tools.bot_ml import build_validation_provisioning as provisioning
from tools.bot_ml.phase8_fixture_contract import load_materialized_fixture_contract


@pytest.fixture(autouse=True)
def clear_manifest_cache():
    adapter._expected_gear_manifest_json.cache_clear()
    yield
    adapter._expected_gear_manifest_json.cache_clear()


def test_pure_manifest_bytes_match_native_materializer_for_all_sixteen_targets():
    # One oracle materialization, before any no-DBC tests.
    native = provisioning.load_gear_profiles(adapter.DEFAULT_GEAR_PROFILES)
    contract, _ = load_materialized_fixture_contract()
    for target in contract['materialization']['live_target_catalog']['selected_rows'].values():
        profile_id = target['gear_profile_id']
        rows = adapter.canonical_gear_manifest(native[profile_id]['equipment'], label=profile_id)
        expected = json.dumps(rows, sort_keys=True, separators=(',', ':'))
        assert adapter._expected_gear_manifest_json(profile_id) == expected
        assert adapter.canonical_sha256(adapter.expected_gear_manifest(profile_id)) == adapter.canonical_sha256(rows)


def test_closed_hunter_excerpt_normalizes_and_evaluates_without_native_data(monkeypatch):
    from tools.bot_ml import wowsims_gear_binding as binding
    from tools.bot_ml import phase8_reference_conditions as conditions
    frozen, _ = load_materialized_fixture_contract()
    glyphs = frozen["materialization"]["glyph_translation_authority"]
    glyphs = {**glyphs, "item_to_property": {int(k): v for k, v in glyphs["item_to_property"].items()},
              "property_to_aura": {int(k): v for k, v in glyphs["property_to_aura"].items()}}
    monkeypatch.setattr(conditions, "glyph_translation_authority", lambda: glyphs)
    def forbidden(*args, **kwargs):
        pytest.fail('read-only normalization attempted native materialization or DBC access')
    for name in ('load_gear_profiles', 'gem_item_enchant_map', 'item_socket_metadata'):
        monkeypatch.setattr(provisioning, name, forbidden)
    # Reference validation may read committed talent-source snapshots; forbid
    # runtime data files, not those hash-bound reference inputs.
    for name in ('load_wdbc_values', 'load_wdb2_values'):
        original = getattr(provisioning, name)
        def read_snapshot(path, *args, original=original, **kwargs):
            assert 'wowsims_cata_p4_talent_sources' in Path(path).parts
            return original(path, *args, **kwargs)
        monkeypatch.setattr(provisioning, name, read_snapshot)
    monkeypatch.setattr(binding, 'native_socket_authority', forbidden)
    monkeypatch.setattr(binding, 'load_wdbc', forbidden)
    payload = json.loads((Path(__file__).parent / 'fixtures/hunter_gear_normalization_excerpt.json').read_text())
    monkeypatch.setattr(adapter, 'load_reference_request_binding',
                        lambda spec: copy.deepcopy(payload['reference_binding']))
    monkeypatch.setattr(adapter, 'load_fixture_contract_binding',
                        lambda spec: copy.deepcopy(payload['fixture_binding']))
    calibration = payload['calibration']
    record, result = adapter.evaluate_runtime_calibration(calibration,
        target_spec='marksmanship_hunter', mode='single_target_300')
    assert record['metrics']['elapsed_dps'] == pytest.approx(23506.896666666667)
    assert record['window']['scored_duration_seconds'] == 300
    assert len(record['identity']['gear_manifest_sha256']) == 64
    assert result['reference_ratio'] > 0
    assert isinstance(result['failure_reasons'], list)
    drift = copy.deepcopy(calibration)
    drift['previous_window']['bots'][0]['gear_profile_observation']['items'][0]['item_id'] += 1
    with pytest.raises(adapter.Phase8CalibrationNormalizationError, match='runtime_gear_manifest_mismatch'):
        adapter.evaluate_runtime_calibration(drift, target_spec='marksmanship_hunter', mode='single_target_300')


@pytest.mark.parametrize('damage', ['unknown', 'incomplete', 'duplicate', 'invalid'])
def test_overlay_identity_validation_and_base_fallback(tmp_path, monkeypatch, damage):
    native_items = [{'slot': slot, 'item_id': 100+slot} for slot in range(16)]
    base = tmp_path/'base.json'
    overlay = tmp_path/'overlay.json'
    base.write_text(json.dumps({'profiles': {'test': {'equipment': native_items}}}))
    monkeypatch.setattr(adapter, 'DEFAULT_GEAR_PROFILES', base)
    monkeypatch.setattr(adapter, 'DEFAULT_WOWSIMS_GEAR_PROFILES', overlay)
    assert adapter.expected_gear_manifest('test')[0]['item_id'] == 100
    adapter._expected_gear_manifest_json.cache_clear()
    document = {'slot_map': list(range(16)), 'profiles': {'test': {'items': [
        {'id': 200+slot} for slot in range(16)]}}}
    overlay.write_text(json.dumps(document))
    assert adapter.expected_gear_manifest('test')[0]['item_id'] == 200
    adapter._expected_gear_manifest_json.cache_clear()
    if damage == 'incomplete': document['profiles']['test']['items'] = [{'id': 200}]
    if damage == 'duplicate': document['slot_map'][1] = 0
    if damage == 'invalid': document['profiles']['test']['items'][0] = {'id': -1}
    overlay.write_text(json.dumps(document))
    with pytest.raises(adapter.Phase8CalibrationNormalizationError):
        adapter.expected_gear_manifest('missing' if damage == 'unknown' else 'test')
