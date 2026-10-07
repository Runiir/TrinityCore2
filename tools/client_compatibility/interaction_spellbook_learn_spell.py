"""One ordinary trainer purchase and stock FUTURESPELL-to-SPELL transition1462."""
import argparse
import json
from pathlib import Path
import time

from . import actors, lab_runtime as lab
from .hunter_learn_contract import (require as guard, SPELL, NAME, TRAINER_GUID, PRICE, MONEY, BASE_SPELLS,
    native_prerequisites, book_row, learned_checks, reconciled_known)
from .hunter_learn_sources import closed, linked, whole, private_json
from .hunter_rest_accrual import bound
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared, reviewed, enter as ordinary_enter, saved, pets, SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_spellbook_navigation import detail, navigate, known, wire_known
from .interaction_spellbook_recon import resources
from .interaction_operations import controls, click_case, point
from .interaction_macros import require
from .interaction_pet_control_training import catalog
from .interaction_parked_client_resource_pause import snapshot
from .interaction_hunter_learn_pose import stage as stage_pose, restore as restore_pose
from .interaction_actionbar_pages import detail as bar_detail
from .observation.inventory import Inventory
from .observation.journal import Cursor, entries


def baseline(t, preparation):
    old = prepared(t, preparation)
    guard(tuple(t.fixture.get(k) for k in ('guid', 'account_id', 'character_name', 'race', 'class', 'level')) ==
        (6, 2, 'Harnesshunt', 1, 3, 10) and old.get('learn_offline_baseline') and old.get('remote_source'),
        'ordinary1462 requires the remotely admitted normalized Hunter continuation')
    linked(old['accepted_previous_sources'][2])
    guard(old.get('learning_reentry_only') is not True, 'restored reentry preparation cannot purchase another lesson')
    guard(all(protected(old).values()), 'protected actors differ')
    return old, actors.session_entry(t.fixture)['session']


def prior(t, path, preparation, phase):
    old, session = baseline(t, preparation)
    e = closed(path)
    phases = phase if isinstance(phase, tuple) else (phase,)
    guard(e.get('phase') in phases and e.get('actor') == t.fixture and e.get('runtime') == t.receipt['runtime'] and
        e.get('native_session') == session and e.get('fixture_source') == bound(preparation),
        'source-bound ordinary1462 stage differs')
    guard(e['finished_at'] <= t.receipt['started_at'], 'ordinary1462 stage source chronology differs')
    t.receipt.update(source=bound(path), native_session=session, entry_source=e['entry_source'],
        baseline=e['baseline'], login_known_spell_ids=e['login_known_spell_ids'], book_layout_baseline=e['book_layout_baseline'])
    if e.get('pose_fixture'):
        t.receipt['pose_fixture'] = e['pose_fixture']
    if e.get('purchase_source'):
        t.receipt['purchase_source'] = e['purchase_source']
    t.persist()
    return old, session, e


def enter(t, preparation, review_path, precision_path):
    from .hunter_learn_preservation import precision
    old = prepared(t, preparation)
    exact = closed(precision_path)
    guard(exact.get('phase') == 'hunter_learn_rest_precision_complete' and exact.get('source') == bound(preparation) and
        exact.get('before') == exact.get('after') == snapshot() == old['learn_offline_baseline'],
        'fresh entry requires its own exact offline FLOAT baseline')
    precision(exact['row'], exact['before'])
    ordinary_enter(t, preparation, review_path)
    session = t.receipt['native_session']
    t.receipt['login_packets'] = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')
        if p.get('session') == session and t.receipt['started_at'] <= p.get('time', 0) <= time.time() and
        p.get('name') in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')]
    t.receipt.update(rest_baseline_source=bound(precision_path), learn_offline_baseline=exact['before'],
        native_pet_reload=reload_pet(session, t.receipt['started_at'], time.time(),
            next(p for p in exact['before']['6']['pets'] if p['id'] == 16)), qualification_added=False)


def reload_pet(session, since, until, baseline_pet):
    from .hunter_learn_pet import reload_proof
    return reload_proof(entries(lab.ROOT / 'evidence/world_packets.jsonl'), session, since, until, baseline_pet)


def open_book(t, label):
    state, _ = t.observe(label + '_before')
    if 'SpellBookFrame' not in state.get('panels', []):
        require(click_case(t, label + '.open', 'Open the observed stock spellbook.',
            lambda c: c['name'] == 'SpellbookMicroButton', lambda b, a, s: {'status': 'spellbook_open_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}), 'spellbook_open_pass')
    return detail(t, label + '_layout')


def caption(t, login_ids, label, learned):
    open_book(t, label)
    require(navigate(t, login_ids, label + '.beast_mastery', 'SpellBookSkillLineTab2', line=2, check_content=False),
        'spellbook_navigation_pass')
    # Poll the actual transition. A settled page alone can still contain the old row.
    deadline = time.monotonic() + 20
    while True:
        probe = detail(t, label + '_caption', book_type='spell', line=2)
        try:
            row = book_row(probe, learned)
            return probe, row
        except RuntimeError:
            if probe.get('page', 0) > 1:
                require(navigate(t, login_ids, label + '.page1', 'SpellBookPrevPageButton', line=2,
                    page=probe['page'] - 1, check_content=False), 'spellbook_navigation_pass')
            elif time.monotonic() >= deadline:
                raise RuntimeError('actual stock1462 learned-state caption did not settle; no purchase replay')
            else:
                time.sleep(.2)


def recon(t, preparation, entry):
    old, session = baseline(t, preparation)
    entered = entry_source(t, entry, session, preparation)
    guard(entered.get('learn_offline_baseline') == old['learn_offline_baseline'] and entered.get('rest_baseline_source'),
        'new Hunter entry ancestry or exact rest baseline differs')
    prerequisite = native_prerequisites()
    oracle = Inventory(lab.ROOT, session, 6).poll()
    login = wire_known(t, session)
    guard(SPELL not in login and known(6) == BASE_SPELLS and resources(oracle) == entered['resources'] and
        resources(oracle)['money'] == MONEY, 'Beast Lore must be absent natively, persistently and affordable')
    t.clean_panels()
    layout = open_book(t, 'hunter_learn_baseline')
    probe, row = caption(t, login, 'hunter_learn_future', False)
    bars = bar_detail(t, 'hunter_learn_bar_baseline')
    guard(bars.get('active_spec') == old['learn_offline_baseline']['6']['native']['activeTalentGroup'] + 1,
        'public and native active action spec differ')
    state, frame = t.observe('hunter_learn_untrained_rendered')
    baseline_value = {'snapshot': old['learn_offline_baseline'], 'saved': saved(6), 'resources': resources(oracle),
        'pets': pets(6), 'prerequisite_fingerprint': prerequisite, 'entry_source': bound(entry),
        'rest_baseline_source': entered['rest_baseline_source'], 'native_pet_reload': entered['native_pet_reload'],
        'bar_layout': bars, 'active_spec': old['learn_offline_baseline']['6']['native']['activeTalentGroup']}
    t.receipt.update(entry_source=bound(entry), baseline=baseline_value, login_known_spell_ids=sorted(login),
        future_probe=probe, future_row=row, state=state, frame=frame, book_layout_baseline=layout,
        native_session=session, protected_checks=protected(old), input_sent=True,
        completed=True, phase='hunter_learn_untrained_reconciled', qualification_added=False)


def stage(t, preparation, source):
    old, session, e = prior(t, source, preparation, 'hunter_learn_untrained_reconciled')
    t.clean_panels()
    fixture, state, frame = stage_pose(t, old, Inventory(lab.ROOT, session, 6).poll(), e['baseline'])
    t.receipt.update(pose_fixture=fixture, state=state, frame=frame, completed=True, phase='hunter_learn_trainer_staged',
        protected_checks=protected(old), qualification_added=False)


def open_trainer(t, preparation, source, review_path):
    old, session, e = prior(t, source, preparation, 'hunter_learn_trainer_staged')
    d = reviewed(t, review_path, 'Benjamin Foxworthy')
    guard(d.get('source') == bound(source) and d['frame'] == e['frame'], 'fresh trainer review source differs')
    state, _ = t.observe('hunter_learn_trainer_before')
    guard(state.get('target', {}).get('guid') == e['state']['target']['guid'], 'current staged trainer identity differs')
    require(t.step('spellbook.learn_spell.trainer_interact', 'Speak to the reviewed existing Hunter trainer.',
        {'interact': {'kind': 'click', 'value': d['point'], 'button': 3, 'hold': .4,
            'description': 'Right-click the reviewed Benjamin Foxworthy.'}},
        lambda b, a, s: {'status': 'hunter_trainer_open_pass' if s == 'interact' and
            any(p in a['panels'] for p in ('GossipFrame', 'ClassTrainerFrame')) else 'client_or_protocol_failure'},
        diagnostic_action='interact'), 'hunter_trainer_open_pass')
    state, _ = t.observe('hunter_learn_trainer_response')
    if 'GossipFrame' in state['panels']:
        require(click_case(t, 'spellbook.learn_spell.trainer_gossip', 'Open the normal trainer service.',
            lambda c: 'train' in c['text'].lower(), lambda b, a, s: {'status': 'hunter_service_pass' if s and
                'ClassTrainerFrame' in a['panels'] else 'client_or_protocol_failure'}), 'hunter_service_pass')
    state, frame = t.observe('hunter_learn_trainer_open')
    native = catalog(session, t.receipt['started_at'], entry=46983, trainer_id=40)
    rows = [r for r in native['rows'] if r[0] == SPELL]
    guard(native['guid'] == TRAINER_GUID and rows == [[1462, 1, 646, 0, 0, 0, 0, 0, 0, 0]] and
        'ClassTrainerFrame' in state['panels'] and saved(6) == e['baseline']['saved'] and all(protected(old).values()),
        'fresh exact native Beast Lore catalog differs')
    t.receipt.update(native_catalog=native, trainer_controls=controls(t), state=state, frame=frame,
        completed=True, phase='hunter_learn_trainer_open', qualification_added=False)


def expose(t, preparation, source):
    old, session, e = prior(t, source, preparation, 'hunter_learn_trainer_open')
    native_prerequisites()
    guard(e['native_catalog']['guid'] == TRAINER_GUID and any(r == [1462, 1, 646, 0, 0, 0, 0, 0, 0, 0]
        for r in e['native_catalog']['rows']), 'fresh available1462 catalog differs')
    for attempt in range(8):
        current = [c for c in controls(t) if c['name'].startswith('ClassTrainerSkill')]
        if any(c['text'].strip() == NAME for c in current):
            break
        header = next((c for i, c in enumerate(current[:-1]) if c['text'] and not c['text'].startswith('  ') and
            current[i + 1]['text'].startswith('  ')), None)
        guard(header, 'Beast Lore is absent from bounded observed trainer rows')
        require(click_case(t, 'spellbook.learn_spell.collapse_' + str(attempt), 'Collapse the observed expanded trainer header.',
            lambda c: c['name'] == header['name'] and c['text'] == header['text'],
            lambda b, a, s: {'status': 'hunter_header_pass' if s and 'ClassTrainerFrame' in a['panels'] else
                'client_or_protocol_failure'}), 'hunter_header_pass')
    guard(any(c['text'].strip() == NAME for c in controls(t) if c['name'].startswith('ClassTrainerSkill')),
        'Beast Lore is absent after bounded trainer header exposure')
    state, frame = t.observe('hunter_learn_trainer_row_exposed')
    t.receipt.update(state=state, frame=frame, native_catalog=e['native_catalog'], trainer_controls=controls(t),
        completed=True, phase='hunter_learn_trainer_exposed', qualification_added=False)


def select(t, preparation, source, review_path):
    old, session, e = prior(t, source, preparation, ('hunter_learn_trainer_open', 'hunter_learn_trainer_exposed'))
    d = reviewed(t, review_path, NAME)
    guard(d.get('source') == bound(source) and d.get('frame') == e['frame'], 'fresh Beast Lore row review differs')
    native_prerequisites()
    row = [c for c in controls(t) if c['name'].startswith('ClassTrainerSkill') and c['text'].strip() == NAME]
    guard(len(row) == 1 and d.get('point') == point(row[0]), 'reviewed Beast Lore row and current observed control differ')
    def selected(b, a, s):
        service = a.get('trainer', {}).get('service', {})
        good = (bool(s) and service.get('name') == NAME and service.get('state') == 'available' and
            service.get('cost') == PRICE and service.get('level') == 0 and
            not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status': 'hunter_lesson_selected_pass' if good else 'client_or_protocol_failure'}
    require(click_case(t, 'spellbook.learn_spell.select1462', 'Select the observed available Beast Lore lesson.',
        lambda c: c['name'].startswith('ClassTrainerSkill') and c['text'].strip() == NAME, selected), 'hunter_lesson_selected_pass')
    state, frame = t.observe('hunter_learn_selected')
    t.receipt.update(state=state, frame=frame, native_catalog=e['native_catalog'], completed=True,
        phase='hunter_learn_lesson_selected', qualification_added=False)


def learn(t, preparation, source, review_path):
    old, session, e = prior(t, source, preparation, 'hunter_learn_lesson_selected')
    d = reviewed(t, review_path, 'Train')
    guard(d.get('source') == bound(source) and d.get('frame') == e['frame'], 'fresh selected Train review differs')
    train = [c for c in controls(t) if c['name'] == 'ClassTrainerTrainButton']
    guard(len(train) == 1 and d.get('point') == point(train[0]), 'reviewed Train point and current observed stock button differ')
    native_prerequisites()
    packets = Cursor(lab.ROOT / 'evidence/world_packets.jsonl')
    for _ in packets.poll():
        pass
    oracle = Inventory(lab.ROOT, session, 6).poll()
    before = resources(oracle)
    state, _ = t.observe('hunter_learn_before_purchase')
    service = state.get('trainer', {}).get('service', {})
    entered = linked(e['entry_source'])
    guard(before == e['baseline']['resources'] and known(6) == BASE_SPELLS and SPELL not in e['login_known_spell_ids'] and
        service.get('name') == NAME and service.get('state') == 'available' and service.get('cost') == PRICE and
        not any(p.get('session') == session and p.get('direction') == 'to_native' and p.get('name') == 'CMSG_TRAINER_BUY_SPELL'
            for p in entries(lab.ROOT / 'evidence/world_packets.jsonl') if p.get('time', 0) >= entered['started_at']),
        'untrained source/resources or one-purchase replay guard differs')
    started = time.time()
    t.receipt.update(purchase_started_at=started, input_sent=True, purchase_input_sent=True,
        qualification_added=False, purchase_source=bound(source), purchase_packets=[], phase='hunter_learn_purchase_started')
    t.persist()
    collected = []
    def capture_purchase(selected, public):
        from .hunter_learn_autobar import addition_guard
        until = time.time()
        collected.extend(p for p in packets.poll() if p.get('session') == session and started <= p.get('time', 0) <= until and
            p.get('name') in ('CMSG_TRAINER_BUY_SPELL', 'SMSG_TRAINER_BUY_SUCCEEDED', 'SMSG_TRAINER_BUY_FAILED',
                'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS', 'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION'))
        after = resources(oracle)
        after_saved = saved(6)
        t.receipt.update(purchase_packets=collected, purchase_finished_at=until, after_resources=after,
            after_saved=after_saved, protected_checks=protected(old), public_actionbar_after=public)
        t.persist()
        placement = addition_guard(e['baseline']['saved']['actions'], after_saved['actions'], collected,
            session, started, until, e['baseline']['active_spec'], public)
        expected_saved = {**e['baseline']['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]]),
            'actions': placement['after_actions'] if placement else e['baseline']['saved']['actions']}
        checks = learned_checks(collected, BASE_SPELLS, known(6), before, after, session, started, until)
        checks.update(ordinary_train=bool(selected), protected_originals=all(protected(old).values()),
            saved_rows=after_saved == expected_saved,
            no_spell_or_pet_cast=not any(p.get('direction') == 'to_native' and p.get('name') in
                ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in collected))
        t.receipt.update(purchase_checks=checks, auto_action_placement=placement,
            actionbar_restoration_required=placement is not None)
        t.persist()
        return checks
    def outcome(b, a, s):
        lab.server_command('saveall')
        time.sleep(1)
        public = bar_detail(t, 'hunter_learn_after_purchase_actions')
        lab.server_command('saveall')
        time.sleep(.5)
        checks = capture_purchase(s, public)
        checks['ui_clean'] = not a.get('lua_errors') and not a.get('blocked_actions')
        t.persist()
        return {'status': 'hunter_learning_pass' if all(checks.values()) else 'client_or_protocol_failure', 'oracle': checks}
    require(click_case(t, 'spellbook.learn_spell.train1462', 'Purchase the selected native Beast Lore lesson once.',
        lambda c: c['name'] == 'ClassTrainerTrainButton', outcome), 'hunter_learning_pass')
    learned = reconciled_known(e['login_known_spell_ids'], t.receipt['purchase_packets'], t.receipt['purchase_checks'])
    t.clean_panels()
    probe, row = caption(t, learned, 'hunter_learn_after', True)
    public = bar_detail(t, 'hunter_learn_transition_actions')
    lab.server_command('saveall')
    time.sleep(.5)
    checks = capture_purchase(True, public)
    state, frame = t.observe('hunter_learn_after_rendered')
    checks['ui_clean'] = not state.get('lua_errors') and not state.get('blocked_actions')
    guard(all(checks.values()), 'late learning side effects differ; never replay Train')
    t.receipt.update(reconciled_known_spell_ids=sorted(learned), learned_probe=probe, learned_row=row, state=state, frame=frame,
        completed=True, phase='hunter_learn_transition_complete', qualification_added=False)


def restore(t, preparation, source, action_cleanup=None):
    old, session, e = prior(t, source, preparation, 'hunter_learn_transition_complete')
    learned = reconciled_known(e['login_known_spell_ids'], e['purchase_packets'], e['purchase_checks'])
    restored_saved = {**e['baseline']['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
    if e.get('actionbar_restoration_required'):
        guard(action_cleanup is not None, 'attributable automatic1462 action placement needs ordinary source-bound cleanup')
        cleanup = closed(action_cleanup)
        guard(cleanup.get('phase') == 'hunter_learn_auto_action_restored' and cleanup.get('source') == bound(source) and
            cleanup.get('actor') == t.fixture and cleanup.get('runtime') == t.receipt['runtime'] and
            cleanup.get('native_session') == session and saved(6) == restored_saved,
            'whole ordinary automatic action cleanup differs')
        t.receipt['action_cleanup_source'] = bound(action_cleanup)
    else:
        guard(action_cleanup is None and saved(6) == restored_saved, 'unexpected saved action drift before restoration')
    after = restore_layout(t, learned, e['book_layout_baseline'])
    t.clean_panels()
    restored = restore_pose(t, e['pose_fixture'], old, restored_saved)
    oracle = Inventory(lab.ROOT, session, 6).poll()
    guard(resources(oracle) == e['after_resources'] and saved(6) == restored_saved, 'learning restoration changed owner resources')
    t.receipt.update(purchase_source=bound(source), book_layout_restored=after, pose_restoration=restored,
        after_saved=restored_saved, completed=True, phase='hunter_learn_online_restored', qualification_added=False)


def restore_layout(t, learned, layout):
    open_book(t, 'hunter_learn_restore')
    for line, target in sorted(layout['pages'].items(), key=lambda item: int(item[0])):
        line = int(line)
        if not target:
            continue
        require(navigate(t, learned, 'spellbook.learn_spell.restore_line' + str(line), 'SpellBookSkillLineTab' + str(line),
            line=line, check_content=False), 'spellbook_navigation_pass')
        for attempt in range(8):
            p = detail(t, 'hunter_learn_restore_page', line=line)
            if p.get('page') == target:
                break
            direction = 'Prev' if p['page'] > target else 'Next'
            require(navigate(t, learned, 'spellbook.learn_spell.restore_page' + str(line) + '_' + str(attempt),
                'SpellBook' + direction + 'PageButton', line=line, check_content=False), 'spellbook_navigation_pass')
        guard(detail(t, 'hunter_learn_restored_line', line=line)['page'] == target, 'original spellbook page exceeded restoration bound')
    require(navigate(t, learned, 'spellbook.learn_spell.restore_selected', 'SpellBookSkillLineTab' + str(layout['skill_line']),
        line=layout['skill_line'], check_content=False), 'spellbook_navigation_pass')
    after = detail(t, 'hunter_learn_layout_restored')
    guard(all(after.get(k) == layout.get(k) for k in ('book_type', 'skill_line', 'pages', 'page')), 'original stock book layout differs')
    return after


def failed_stage(t, preparation, source):
    old, session = baseline(t, preparation)
    failed = private_json(source)
    guard(failed.get('completed') is False and failed.get('failure') and
        type(failed.get('finished_at')) in (int, float) and failed['started_at'] < failed['finished_at'] <= t.receipt['started_at'] and
        failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('fixture_source') == bound(preparation) and failed.get('native_session') == session and
        failed.get('baseline', {}).get('snapshot') == old['learn_offline_baseline'] and failed.get('pose_fixture'),
        'bounded recovery requires the actual closed failed owned learning stage')
    t.receipt.update(fixture_source=bound(preparation), failed_source=bound(source), baseline=failed['baseline'],
        entry_source=failed['entry_source'], native_session=session, pose_fixture=failed['pose_fixture'],
        book_layout_baseline=failed['book_layout_baseline'], login_known_spell_ids=failed['login_known_spell_ids'],
        recovery_only=True, failed_whole_excluded=True, qualification_added=False)
    t.persist()
    return old, session, failed


def recover(t, preparation, source, paid, action_cleanup=None):
    """Restore an observed failure without reissuing the original gameplay input."""
    old, session, failed = failed_stage(t, preparation, source)
    baseline_value = failed['baseline']
    entry = linked(failed['entry_source'])
    until = time.time()
    rows = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl') if p.get('session') == session and
        entry['started_at'] <= p.get('time', 0) <= until and p.get('name') in
        ('CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS', 'CMSG_SET_ACTION_BUTTON',
            'CMSG_CAST_SPELL', 'CMSG_PET_ACTION')]
    guard(not any(p.get('direction') == 'to_native' and p.get('name') in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION') for p in rows),
        'learning recovery refuses unexpected spell or pet input')
    oracle = Inventory(lab.ROOT, session, 6).poll()
    current_resources = resources(oracle)
    current_saved = saved(6)
    learned = set(failed['login_known_spell_ids'])
    guard(SPELL not in learned, 'failed learning source was already trained before its input')
    expected_saved = baseline_value['saved']
    if paid:
        import struct
        guard(failed.get('purchase_input_sent') is True and failed.get('purchase_started_at'),
            'paid recovery requires the actual one-Train attempt')
        buys = [p for p in rows if p.get('direction') == 'to_native' and p.get('name') == 'CMSG_TRAINER_BUY_SPELL']
        learns = [p for p in rows if p.get('direction') == 'from_native' and p.get('name') == 'SMSG_LEARNED_SPELL']
        guard(len(buys) == len(learns) == 1 and buys[0].get('body') == struct.pack('<QII', TRAINER_GUID, 40, SPELL).hex() and
            learns[0].get('body') == struct.pack('<II', SPELL, 0).hex() and
            failed['purchase_started_at'] <= buys[0]['time'] <= learns[0]['time'] <= until and
            current_resources == {**baseline_value['resources'], 'money': MONEY - PRICE},
            'paid recovery needs one attributable native purchase, learn, and exact charge')
        expected_saved = {**baseline_value['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
        learned.add(SPELL)
        if action_cleanup:
            cleaned = closed(action_cleanup)
            guard(cleaned.get('phase') == 'hunter_learn_auto_action_restored' and cleaned.get('source') == bound(source) and
                cleaned.get('actor') == t.fixture and cleaned.get('runtime') == t.receipt['runtime'] and
                cleaned.get('native_session') == session, 'failed paid purchase action cleanup source differs')
            t.receipt['action_cleanup_source'] = bound(action_cleanup)
        else:
            guard(not any(p.get('name') == 'CMSG_SET_ACTION_BUTTON' for p in rows),
                'paid recovery needs attributed ordinary cleanup before any action persistence')
        if current_saved == baseline_value['saved']:
            guard(all(protected(old).values()), 'protected actors differ before learned native persistence')
            t.receipt['native_purchase_persistence'] = {'native_buy': buys[0], 'native_learn': learns[0],
                'before_saved': current_saved, 'expected_after_saved': expected_saved,
                'resources': current_resources, 'gameplay_input_sent': False, 'train_input_replayed': False}
            t.persist()
            lab.server_command('saveall')
            time.sleep(.5)
            current_saved = saved(6)
            guard(current_saved == expected_saved and resources(oracle.poll()) == current_resources and
                all(protected(old).values()), 'observed native learning did not persist its exact declared saved rows')
        t.receipt.update(purchase_started_at=failed['purchase_started_at'], purchase_packets=rows,
            purchase_input_sent=True, purchase_qualified=False, after_resources=current_resources)
    else:
        guard(not any(p.get('name') in ('CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL',
            'SMSG_LEARNED_SPELLS', 'CMSG_SET_ACTION_BUTTON') for p in rows) and
            current_resources == baseline_value['resources'], 'no-purchase pose recovery refuses an actual purchase or charge')
        t.receipt.update(purchase_input_sent=False, purchase_intent_recorded=failed.get('purchase_input_sent') is True,
            purchase_packets=rows, no_purchase_observed=True, recovery_observed_until=until)
    guard(current_saved == expected_saved and all(protected(old).values()),
        'learning failure recovery refuses unexpected saved or protected changes')
    after = restore_layout(t, learned, failed['book_layout_baseline'])
    t.clean_panels()
    restored = restore_pose(t, failed['pose_fixture'], old, expected_saved,
        failed.get('pose_restoration') or failed.get('pose_delete_authority'))
    guard(resources(oracle) == current_resources and saved(6) == expected_saved, 'failure housekeeping changed owner resources')
    t.receipt.update(after_saved=expected_saved, after_resources=current_resources, book_layout_restored=after,
        pose_restoration=restored, purchase_source=bound(source), completed=True,
        phase='hunter_learn_recovery_restored' if paid else 'hunter_learn_no_purchase_recovery_restored',
        failed_whole_excluded=True, recovery_only=True, qualification_added=False, train_input_replayed=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['enter', 'recon', 'stage', 'open', 'expose', 'select', 'learn', 'restore',
        'recover-pose', 'recover-paid'])
    for name in ('preparation', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('source', 'entry', 'review', 'precision', 'action-cleanup'):
        p.add_argument('--' + name, type=Path)
    a = p.parse_args()
    with actor('scout'):
        t = Trial(a.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action == 'enter': enter(t, a.preparation, a.review, a.precision)
            elif a.action == 'recon': recon(t, a.preparation, a.entry)
            elif a.action == 'stage': stage(t, a.preparation, a.source)
            elif a.action == 'open': open_trainer(t, a.preparation, a.source, a.review)
            elif a.action == 'expose': expose(t, a.preparation, a.source)
            elif a.action == 'select': select(t, a.preparation, a.source, a.review)
            elif a.action == 'learn': learn(t, a.preparation, a.source, a.review)
            elif a.action == 'restore': restore(t, a.preparation, a.source, a.action_cleanup)
            else: recover(t, a.preparation, a.source, a.action == 'recover-paid', a.action_cleanup)
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
