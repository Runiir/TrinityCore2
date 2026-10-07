"""Observe UI170's already-paid1462 after its exact flyout instrumentation error.

This command never buys, casts, moves a bar action or writes saved state. The
original failed Trial stays immutable. Its existing native outcome is joined to
a newly collected stock learned caption, under its own honest collection clock.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

from . import lab_runtime as lab
from .hunter_learn_contract import require, reconciled_known
from .hunter_learn_reconciliation import (FAILED_SOURCE, observation_reconciliation,
    validate_observation_reconciliation)
from .hunter_learn_sources import linked, private_json
from .hunter_rest_accrual import bound
from .interaction_hunter_fixture import protected
from .interaction_owned_class_fixture import saved, SCRIPT_BOUNDARY
from .interaction_social import actor
from .interaction_spellbook_learn_spell import baseline, caption
from .interaction_spellbook_navigation import known
from .interaction_spellbook_recon import resources
from .interaction_actionbar_pages import detail as bar_detail
from .interaction_trial import Trial
from .observation.inventory import Inventory
from .observation.journal import entries


def original(t, preparation, source):
    old, session = baseline(t, preparation)
    require(bound(source) == FAILED_SOURCE, 'requires the exact immutable UI170 flyout failure')
    failed = private_json(source)
    selected_ref = failed['purchase_source']
    selected = linked(selected_ref)
    require(failed['finished_at'] <= t.receipt['started_at'] and all(
        value.get('actor') == t.fixture and value.get('runtime') == t.receipt['runtime'] and
        value.get('native_session') == session and value.get('fixture_source') == bound(preparation)
        for value in (failed, selected)), 'observation requires the original owned session, actor and runtime')
    screen = failed['screen_review']
    review_ref = {key: screen[key] for key in ('path', 'sha256')}
    review = private_json(Path(review_ref['path']), False)
    require(bound(Path(review_ref['path'])) == review_ref and review.get('reviewed') is True and
        review.get('source') == selected_ref and review.get('control') == 'Train' and
        review.get('frame') == screen['frame'] == selected['frame'] and
        review.get('fixture_source_sha256') == bound(preparation)['sha256'] and
        selected['finished_at'] <= review['reviewed_at'] <= failed['started_at'],
        'original selected Train review or its immutable source differs')
    entry = linked(failed['entry_source'])
    require(entry.get('actor') == t.fixture and entry.get('runtime') == t.receipt['runtime'] and
        entry.get('native_session') == session and entry.get('fixture_source') == bound(preparation) and
        failed['baseline']['snapshot'] == old['learn_offline_baseline'],
        'original owned entry or six-actor baseline differs')
    keys = ('baseline', 'entry_source', 'login_known_spell_ids', 'book_layout_baseline', 'pose_fixture',
        'trainer_identity', 'native_catalog', 'screen_review', 'purchase_source', 'purchase_started_at',
        'purchase_finished_at', 'purchase_packets', 'trainer_identity_checked_at')
    t.receipt.update({key: deepcopy(failed[key]) for key in keys})
    t.receipt.update(source=selected_ref, fixture_source=bound(preparation), native_session=session,
        observation_settlement_source=FAILED_SOURCE, original_case=deepcopy(failed['cases'][0]),
        original_purchase_interval=[failed['purchase_started_at'], failed['purchase_finished_at']],
        original_purchase_input_sent=True, purchase_input_sent=False, input_sent=False,
        gameplay_input_sent=False, mutation_sent=False, train_input_replayed=False, book_navigation_input_sent=False,
        observation_only=True, qualification_added=False, phase='hunter_learn_observation_reconciliation_started')
    t.persist()
    return old, session, failed, selected, selected_ref


def current(t, old, session, failed, selected, selected_ref, oracle, label):
    state, frame = t.observe(label + '_state')
    require(not frame['movement'].get('dead') and not frame['movement'].get('in_combat') and
        not frame['movement'].get('speed') and frame['movement'].get('health_percent') == 100 and
        failed['cases'][0]['after_frame']['movement'].get('health_percent') == 100 and not state.get('cursor_info') and
        not state.get('spell_targeting'), 'paid observation requires an idle living owner and empty cursor')
    public = bar_detail(t, label + '_actions')
    saved_now, resources_now = saved(6), resources(oracle.poll())
    require(known(6) == saved_now['spells'], 'current native saved spell authority differs')
    observed_until = time.time()
    proof = observation_reconciliation(failed, FAILED_SOURCE, selected, selected_ref,
        saved=saved_now, resources=resources_now, protected_checks=protected(old), public=public,
        state=state, frame=frame, rows=list(entries(lab.ROOT / 'evidence/world_packets.jsonl')),
        observed_until=observed_until)
    return proof, state, frame


def observe(t, preparation, source):
    old, session, failed, selected, selected_ref = original(t, preparation, source)
    oracle = Inventory(lab.ROOT, session, 6).poll()
    before, _, _ = current(t, old, session, failed, selected, selected_ref, oracle,
        'hunter_learn_reconciliation_before')
    t.receipt['reconciliation_preconditions'] = before
    t.persist()
    learned = reconciled_known(failed['login_known_spell_ids'], failed['purchase_packets'], before['purchase_checks'])
    t.receipt.update(book_navigation_input_sent=True, input_sent=True)
    t.persist()
    t.clean_panels()
    probe, row = caption(t, learned, 'hunter_learn_reconciled', True)
    t.clean_panels()
    after, state, frame = current(t, old, session, failed, selected, selected_ref, oracle,
        'hunter_learn_reconciliation_after')
    t.receipt.update(observation_reconciliation=after, purchase_checks=after['purchase_checks'],
        after_saved=after['after_saved'], after_resources=after['after_resources'],
        protected_checks=after['protected_checks'], public_actionbar_after=after['public_actionbar_after'],
        auto_action_placement=None, actionbar_restoration_required=False,
        reconciled_known_spell_ids=sorted(learned), learned_probe=probe, learned_row=row, state=state, frame=frame,
        completed=True, phase='hunter_learn_transition_complete', finished_at=time.time())
    validate_observation_reconciliation(t.receipt, failed, selected,
        wire=list(entries(lab.ROOT / 'evidence/world_packets.jsonl')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('preparation', 'source', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        t = Trial(args.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try:
            observe(t, args.preparation, args.source)
        except BaseException as error:
            t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            if not isinstance(error, Exception):
                raise
        finally:
            t.receipt['finished_at'] = time.time()
            t.persist()
        print(json.dumps({key: t.receipt.get(key) for key in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
