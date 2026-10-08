"""Full six-actor preservation and once-only exact FLOAT attribution for a bag swap."""
from copy import deepcopy

from . import bag_swap_contract as contract
from . import item_actionbar_preservation as shared

ACCOUNTING, PRECISION_QUERY = shared.ACCOUNTING, shared.PRECISION_QUERY
float32, float32_bits, exact_precision, native_rest = (
    shared.float32, shared.float32_bits, shared.exact_precision, shared.native_rest)
require, finite, strict_equal = contract.require, contract.finite, contract.strict_equal


def login_rest(before, after, entry, exact_before, exact_after, rate=1):
    require(type(entry) is dict and entry.get('phase') == contract.ENTRY_PHASE,
        'fresh bag-swap ordinary entry receipt is required')
    normalized = deepcopy(entry)
    normalized['phase'] = 'item_actionbar_entered'
    return shared.login_rest(before, after, normalized, exact_before, exact_after, rate)


def _preserved(before, after, *, swapped=False, offline=True):
    old = contract.owned_snapshot(before)
    now = contract.owned_snapshot(after, offline=offline, swapped=swapped)
    require(all(strict_equal(after[g], before[g]) for g in ('1', '3', '4', '5', '6')),
        'a protected actor changed during the bag swap')
    require(set(now['native']) == set(old['native']), 'the complete native projection changed shape')
    changed = {k for k in old['native'] if not strict_equal(now['native'][k], old['native'][k])}
    require(changed <= ACCOUNTING | {'rest_bonus', 'online'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, now) for k in ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        now['pets'] == old['pets'] == [] and strict_equal(now['saved'], old['saved']),
        'bag swap changed health/power/pose, pets, saved spells/skills/quests/actions or unrelated native fields')
    shared.action_rows(old['saved'].get('actions'))
    inventory = contract.inventory_rows(old['inventory'], now['inventory'], swapped=swapped)
    return old, now, inventory


def online_preservation(before, after, *, swapped=False):
    """SaveAll is diagnostic; admission still requires the normal offline closure."""
    old, now, inventory = _preserved(before, after, swapped=swapped, offline=False)
    require(now['native']['online'] == 1 and finite(now['native'].get('rest_bonus')) and
        old['native']['rest_bonus'] <= now['native']['rest_bonus'] < contract.REST_CAP,
        'online ordinary accounting/rest state differs')
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'swapped': swapped,
        'inventory': inventory, 'health_power_pose_preserved': True,
        'saved_actions_preserved': True, 'rest_attribution_pending': True, 'operations_admitted': 0}


def preserve_six(before, after, entry, exact_before, exact_after, *, swapped=False, offline=True):
    old, now, inventory = _preserved(before, after, swapped=swapped, offline=offline)
    rest = login_rest(old['native'], now['native'], entry, exact_before, exact_after)
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'all_six_preserved': True,
        'swapped': swapped, 'inventory': inventory, 'native_rest': rest,
        'all_item_instance_fields_unchanged': True, 'health_power_pose_preserved': True,
        'saved_actions_preserved': True, 'pets_absent': True}
