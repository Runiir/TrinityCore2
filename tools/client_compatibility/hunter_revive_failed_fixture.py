"""Guards for preserving a closed failed Revive and restoring its offline fixture."""
from copy import deepcopy
import json
import math
from pathlib import Path
from . import lab_runtime as lab
from .hunter_revive_fixture import dead_snapshot
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_pet_summon import cast_identity
from .interaction_retained_class_fixture import closed
from .world.objects import INDEX


FAILURE = 'RuntimeError: one ordinary Revive did not pass native and public outcome checks; do not replay'
ORIGIN_CHECKS = {'original_character', 'original_saved_rows', 'native_worldserver'}
CAPTURE_CHECKS = {key: key not in {'same_owned_pet', 'native_dead_to_alive', 'public_owned_living_pet'}
    for key in ('one_modern_cast', 'one_native_cast', 'matching_native_completion', 'no_failure_packets',
        'same_owned_pet', 'native_dead_to_alive', 'public_owned_living_pet', 'owner_health_unchanged',
        'resources', 'saved_rows', 'no_public_errors', 'ui_clean',
        'actor_1_unchanged', 'actor_2_unchanged', 'actor_3_unchanged', 'actor_4_unchanged', 'actor_5_unchanged')}
ALLOWED_HUNTER_COLUMNS = {'totaltime', 'leveltime', 'logout_time', 'latency'}


def times(e, keys):
    values = [e.get(k) for k in keys]
    return (all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values) and
        all(a < b for a, b in zip(values, values[1:])))


def validate_failed_cast(e):
    """Admit this fully recorded failure, never a partial receipt or successful cast."""
    if (e.get('schema') != 'client442_laya_interactions_v1' or e.get('completed') is not False or
        e.get('failure') != FAILURE or e.get('phase') is not None or
        e.get('controller') != 'code_diagnostic_ordinary_inputs' or e.get('model') is not None or
        e.get('revision') is not None or e.get('fine_tuned') is not False or e.get('cases') != [] or
        e.get('input_sent') is not True or e.get('qualification_added') is not False or
        e.get('ordinary_input') != {'kind': 'chat', 'value': '/cast Revive Pet'} or
        e.get('custom_script_permission') != 'blocked_by_user' or e.get('softTargetInteract') != SCRIPT_BOUNDARY or
        not times(e, ('started_at', 'cast_started_at', 'cast_finished_at', 'finished_at')) or
        set(e.get('capture_checks', {})) != set(CAPTURE_CHECKS) or
        any(e.get('capture_checks', {}).get(k) is not v for k, v in CAPTURE_CHECKS.items()) or e.get('failure_packets') != [] or
        e.get('restoration_checks') is not None or not e.get('native_session')):
        raise RuntimeError('requires the closed one-Revive native/public outcome failure')
    actor = e.get('actor', {})
    if tuple(actor.get(k) for k in ('actor', 'guid', 'account_id', 'character_name', 'race', 'class', 'level')) != (
        'scout', 6, 2, 'Harnesshunt', 1, 3, 10):
        raise RuntimeError('failed Revive actor differs')
    parsed = []
    for packet in e.get('cast_packets', []):
        if (packet.get('session') != e['native_session'] or
            not e['cast_started_at'] <= packet.get('time', 0) <= e['cast_finished_at']):
            raise RuntimeError('failed Revive packet window differs')
        row = cast_identity(packet)
        if row: parsed.append((packet, row))
    modern = [r for p, r in parsed if p['name'] == 'CMSG_CAST_SPELL' and p['direction'] == 'from_client']
    native = [r for p, r in parsed if p['name'] == 'CMSG_CAST_SPELL' and p['direction'] == 'to_native']
    go = [r for p, r in parsed if p['name'] == 'SMSG_SPELL_GO' and p['direction'] == 'from_native' and r['spell'] == 982]
    failures = [p for p in e.get('cast_packets', []) if p['name'] in
        ('SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER')]
    if (len(modern) != 1 or len(native) != 1 or len(go) != 1 or failures or
        modern[0]['spell'] != 982 or native[0]['spell'] != 982 or
        go[0]['counter'] != native[0]['counter'] or go[0]['caster'] != 6 or go[0]['unit'] != 6 or
        json.loads(json.dumps([modern, native, go])) !=
            [e.get('modern_cast_requests'), e.get('native_cast_requests'), e.get('native_completions')]):
        raise RuntimeError('failed Revive does not contain exactly one matching native982 completion')
    before, after = e.get('native_pet_before', {}), e.get('native_pet_after', {})
    for pet in (before, after):
        fields = {int(k): v for k, v in pet.get('fields', {}).items()}
        if (fields.get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or fields.get(INDEX['OBJECT_FIELD_ENTRY']) != 299 or
            fields.get(INDEX['UNIT_FIELD_SUMMONEDBY']) != 6 or fields.get(INDEX['UNIT_FIELD_SUMMONEDBY'] + 1, 0) != 0 or
            fields.get(INDEX['UNIT_FIELD_HEALTH'], 0) != 0 or not fields.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0)):
            raise RuntimeError('failed Revive dead owned Wolf16 evidence differs')
    if not before.get('guid') or before['guid'] != after.get('guid') or e.get('outcome_state', {}).get('target', {}).get('health', 0) != 0:
        raise RuntimeError('failed Revive pet identity or public failure differs')
    return e


def failed_cast(path):
    path = Path(path)
    if path.is_symlink(): raise ValueError('requires an owned failed episode, without a symlink')
    path = path.resolve()
    if path.name != 'episode.json' or not path.is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires a private fully closed failed episode')
    return validate_failed_cast(json.loads(path.read_text()))


def linked_closed(ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise RuntimeError('failed Revive source binding is absent')
    path = Path(ref['path'])
    if path.is_symlink() or bound(path) != ref:
        raise RuntimeError('failed Revive source hash differs')
    return closed(path)


def sources(preparation_path, fixture_path, cast_path, park_path):
    old, fixture, park = [closed(p) for p in (preparation_path, fixture_path, park_path)]
    cast = failed_cast(cast_path)
    expected = bound(preparation_path)
    entry = linked_closed(cast.get('entry_source'))
    recon = linked_closed(cast.get('recon_source'))
    if (fixture.get('schema') != 'client442_owned_revive_dead_fixture_v1' or
        fixture.get('phase') != 'owned_revive_dead_fixture_staged' or fixture.get('after') != dead_snapshot(fixture['before']) or
        fixture.get('expected_after') != fixture['after'] or len(fixture.get('checks', {})) != 7 or
        not all(v is True for v in fixture['checks'].values()) or
        old.get('phase') != 'await_owned_class_lobby_review' or old.get('fixture_source') != bound(fixture_path) or
        old.get('class_actor') != cast['actor'] or old.get('origin_actor', {}).get('guid') != 2 or
        old.get('natural_native') != fixture['after']['6']['native'] or old.get('natural_saved') != fixture['after']['6']['saved'] or
        old.get('retained_class_pets') != fixture['after']['6']['pets'] or
        old.get('protected_baseline') != {g: fixture['before'][g] for g in ('1', '2', '3', '4', '5')} or
        set(old.get('checks', {})) != ORIGIN_CHECKS | {f'actor_{g}_unchanged' for g in ('1', '2', '3', '4', '5')} or
        not all(v is True for v in old['checks'].values()) or
        cast.get('dead_fixture_source') != bound(fixture_path) or cast.get('fixture_source') != expected or
        any(e.get('runtime') != cast['runtime'] for e in (old, entry, recon, park)) or
        any(e.get('fixture_source') != expected for e in (entry, recon, park)) or
        entry.get('phase') != 'owned_class_entered' or entry.get('native_session') != cast['native_session'] or
        entry.get('actor') != cast['actor'] or
        recon.get('phase') != 'await_owned_revive_cast_review' or recon.get('actor') != cast['actor'] or
        recon.get('native_session') != cast['native_session'] or recon.get('revive_spell', {}).get('id') != 982 or
        recon.get('revive_spell', {}).get('known') is not True or
        recon.get('dead_fixture_source') != bound(fixture_path) or recon.get('entry_source') != cast.get('entry_source') or
        park.get('actor') != cast['actor'] or park.get('phase') != 'await_original_selection_review' or
        set(park.get('checks', {})) != ORIGIN_CHECKS | {'class_offline'} or
        not all(v is True for v in park['checks'].values()) or
        not fixture['finished_at'] < old['started_at'] < old['finished_at'] <= cast['started_at'] or
        not cast['finished_at'] <= park['started_at'] < park['finished_at'] or
        any(fixture['runtime'].get(k) != cast['runtime'].get(k) for k in ('worldserver', 'modern_world'))):
        raise RuntimeError('failed Revive preparation, fixture, entry or ordinary park sources differ')
    return old, fixture, cast, park


def offline_restore(before, fixture, park, rest_proof=None):
    """Return the sole permitted cleanup state; reject every other offline change."""
    original = fixture['before']
    dead_snapshot(original)
    if set(before) != set(original) or any(v['native']['online'] != 0 for v in before.values()):
        raise RuntimeError('failed Revive cleanup requires all six offline')
    if any(before[g] != original[g] for g in ('1', '2', '3', '4', '5')):
        raise RuntimeError('failed Revive cleanup protected actor differs')
    hunter = before['6']
    changed = {k for k in set(original['6']['native']) | set(hunter['native'])
        if original['6']['native'].get(k) != hunter['native'].get(k)}
    allowed = set(ALLOWED_HUNTER_COLUMNS)
    if (rest_proof and rest_proof.get('schema') == 'client442_owned_hunter_native_offline_rest_v1' and
        rest_proof.get('input_sent') is False and
        rest_proof.get('original_rest_bonus') == original['6']['native'].get('rest_bonus') and
        rest_proof.get('expected_db_rest_bonus') == rest_proof.get('preserved_rest_bonus') == hunter['native'].get('rest_bonus')):
        allowed.add('rest_bonus')
    if (changed - allowed or hunter['native'] != park['retained_class_fixture'] or
        hunter['saved'] != original['6']['saved'] or hunter['saved'] != park['retained_class_saved'] or
        hunter['inventory'] != original['6']['inventory'] or hunter['pets'] != park['retained_class_pets']):
        raise RuntimeError('failed Revive cleanup saved Hunter state differs')
    rows, old = hunter['pets'], original['6']['pets']
    if len(rows) != 2 or {p['id'] for p in rows} != {4, 16}:
        raise RuntimeError('failed Revive cleanup pet set differs')
    current = {p['id']: p for p in rows}
    baseline = {p['id']: p for p in old}
    pet = current[16]
    ignored = {'curhealth', 'CreatedBySpell', 'active', 'savetime'}
    if (current[4] != baseline[4] or (pet['curhealth'], pet['CreatedBySpell'], pet['active']) != (0, 883, 0) or
        pet['savetime'] < baseline[16]['savetime'] or
        {k: v for k, v in pet.items() if k not in ignored} != {k: v for k, v in baseline[16].items() if k not in ignored}):
        raise RuntimeError('failed Revive cleanup differs beyond the recorded dead/called fixture')
    result = deepcopy(before)
    restored = next(p for p in result['6']['pets'] if p['id'] == 16)
    for key in ('curhealth', 'CreatedBySpell', 'active'): restored[key] = baseline[16][key]
    return result
