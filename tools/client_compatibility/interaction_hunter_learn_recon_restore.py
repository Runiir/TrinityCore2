"""Restore the stock book after UI170's pre-purchase actionbars timeout."""
import argparse
import json
from pathlib import Path
import time

from . import actors, lab_runtime as lab
from .hunter_learn_contract import require, BASE_SPELLS, SPELL
from .hunter_learn_sources import closed, private_json
from .hunter_rest_accrual import bound
from .interaction_hunter_fixture import protected
from .interaction_owned_class_fixture import prepared, saved, SCRIPT_BOUNDARY
from .interaction_social import actor
from .interaction_spellbook_learn_spell import restore_layout
from .interaction_spellbook_navigation import wire_known
from .interaction_spellbook_recon import resources
from .interaction_trial import Trial
from .observation.inventory import Inventory
from .observation.journal import entries

FAILED_SHA256 = 'f84dc169aa00171ad77510d75685dc8ac257fde2274b734aa0ea6503514e856d'
FORBIDDEN = {'CMSG_TRAINER_BUY_SPELL', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION', 'CMSG_SET_ACTION_BUTTON'}


def no_gameplay(session, since):
    require(not any(p.get('session') == session and p.get('time', 0) >= since and
        ((p.get('direction') == 'to_native' and p.get('name') in FORBIDDEN) or
         (p.get('direction') in ('from_native', 'to_client') and
          p.get('name') in ('SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS')))
        for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')),
        'failed reconnaissance cleanup refuses purchase, cast, pet or action input')


def restore(t, preparation, entry_path, failed_path):
    old = prepared(t, preparation)
    entry, failed = closed(entry_path), private_json(failed_path)
    session = actors.session_entry(t.fixture)['session']
    require(lab.sha256(failed_path) == FAILED_SHA256 and failed.get('completed') is False and
        failed.get('failure') == 'RuntimeError: actionbars diagnostic did not become visible' and
        failed.get('fixture_source') == bound(preparation) and
        entry.get('phase') == 'owned_class_entered' and entry.get('fixture_source') == bound(preparation) and
        entry.get('native_session') == session and
        all(e.get('actor') == t.fixture and e.get('runtime') == t.receipt['runtime'] for e in (entry, failed)) and
        entry['finished_at'] <= failed['started_at'] < failed['finished_at'] <= t.receipt['started_at'],
        'requires the immutable UI170 failed reconnaissance and its successful ordinary entry')
    layout = failed['spellbook_details']['hunter_learn_baseline_layout']['state']['spellbook_probe']
    expected = {'book_type': 'spell', 'skill_line': 1, 'page': 1,
        'pages': {'1': 1, '2': 1, '3': 1, '4': 1}}
    require(all(layout.get(k) == v for k, v in expected.items()), 'original captured stock layout differs')
    oracle = Inventory(lab.ROOT, session, 6).poll()
    before = resources(oracle)
    require(t.fixture.get('guid') == 6 and before == entry['resources'] and
        saved(6) == baseline_saved(old) and all(protected(old).values()), 'pre-purchase state changed')
    no_gameplay(session, entry['started_at'])
    known = wire_known(t, session)
    require(SPELL not in known and sorted(known) == sorted(failed['native_known_spell_packet']['ids']) and
        failed['native_known_spell_packet']['session'] == session, 'unchanged native login authority is required')
    state, frame = t.observe('hunter_learn_failed_recon_before_restore')
    require(not frame['movement']['dead'] and not frame['movement']['in_combat'] and
        not frame['movement']['speed'] and not state.get('cursor_info') and
        not state.get('spell_targeting'), 'stock book restoration requires an idle living owner and empty cursor')
    t.receipt.update(sources=[bound(preparation), bound(entry_path), bound(failed_path)],
        original_layout=expected, before_resources=before, native_session=session, before_state=state, before_frame=frame,
        recovery_only=True, failed_whole_excluded=True, qualification_added=False)
    t.persist()
    after = restore_layout(t, known, layout)
    t.clean_panels()
    state, frame = t.observe('hunter_learn_failed_recon_restored')
    no_gameplay(session, entry['started_at'])
    require(all(after.get(k) == v for k, v in expected.items()) and
        resources(oracle) == before and saved(6) == baseline_saved(old) and all(protected(old).values()) and
        not frame['movement']['dead'] and not frame['movement']['in_combat'] and not frame['movement']['speed'] and
        not state.get('cursor_info') and not state.get('spell_targeting') and
        not state.get('panels') and not state.get('lua_errors') and not state.get('blocked_actions'),
        'failed reconnaissance original layout or owner state did not restore')
    t.receipt.update(after_layout=after, state=state, frame=frame, completed=True,
        phase='hunter_learn_failed_recon_layout_restored', input_sent=True)


def baseline_saved(old):
    require(old['natural_saved']['spells'] == BASE_SPELLS, 'source baseline is not untrained')
    return old['natural_saved']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation', 'entry', 'source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    with actor('scout'):
        t = Trial(a.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try:
            restore(t, a.preparation, a.entry, a.source)
        except BaseException as error:
            t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            if not isinstance(error, Exception):
                raise
        finally:
            t.receipt['finished_at'] = time.time()
            t.persist()
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
