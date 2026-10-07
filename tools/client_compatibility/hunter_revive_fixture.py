"""Exact state guards for one offline, disposable Hunter pet health fixture."""
from copy import deepcopy


def dead_snapshot(before):
    if set(before) != {str(n) for n in range(1, 7)} or any(v['native']['online'] for v in before.values()):
        raise RuntimeError('requires all six owned characters offline')
    hunter = before['6']
    if tuple(hunter['native'][k] for k in ('guid', 'account', 'name', 'race', 'class', 'level')) != (6, 2, 'Harnesshunt', 1, 3, 10):
        raise RuntimeError('owned Hunter identity differs')
    rows = hunter['pets']
    if len(rows) != 2 or {p['id'] for p in rows} != {4, 16}:
        raise RuntimeError('requires exactly Harnesswolf4 and disposable Wolf16')
    named = next(p for p in rows if p['id'] == 4)
    pet = next(p for p in rows if p['id'] == 16)
    if tuple(named[k] for k in ('owner', 'entry', 'name', 'renamed', 'slot', 'active', 'curhealth')) != (6, 42717, 'Harnesswolf', 1, 5, 0, 278):
        raise RuntimeError('stored named pet differs')
    if tuple(pet[k] for k in ('owner', 'entry', 'name', 'renamed', 'CreatedBySpell', 'PetType', 'level', 'slot', 'active', 'curhealth')) != (6, 299, 'Wolf', 0, 13481, 1, 10, 0, 1, 278):
        raise RuntimeError('disposable normally tamed pet differs')
    result = deepcopy(before)
    next(p for p in result['6']['pets'] if p['id'] == 16)['curhealth'] = 0
    return result


def restored_pets(before, current):
    if len(before) != 2 or len(current) != 2 or {p['id'] for p in current} != {4, 16}:
        return False
    old = {p['id']: p for p in before}
    for pet in current:
        expected = old.get(pet['id'])
        if not expected:
            return False
        if pet['id'] == 4:
            if pet != expected:
                return False
        elif (pet.get('savetime', 0) < expected['savetime'] or
              {k: v for k, v in pet.items() if k != 'savetime'} !=
              {k: v for k, v in expected.items() if k != 'savetime'}):
            return False
    return True
