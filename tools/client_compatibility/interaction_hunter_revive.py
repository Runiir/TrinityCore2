"""Cast ordinary Revive Pet once on the exact staged disposable owned pet."""
import argparse
from copy import deepcopy
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .hunter_revive_fixture import restored_pets
from .hunter_revive_lifecycle import RevivePresence, corpse_budget, dead_identity, dead_pet_rows, native_revive_timing, bind_call_lifetime
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared, reviewed, saved, pets, origin_checks, SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_spellbook_pet_recon import entry_source
from .interaction_spellbook_navigation import wire_known, detail, navigate
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_observation import read_page
from .interaction_pet_dismiss import public_pet, vitals
from .interaction_pet_summon import cast_identity
from .interaction_pet_command_probe import expected_guid
from .interaction_pet_target import pair
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX


class ReviveTrial(Trial):
    revive_before_submit = None

    def execute(self, action, *, before_submit=None):
        if action == {'kind': 'chat', 'value': '/cast Revive Pet'}:
            if self.revive_before_submit is None or before_submit is not None:
                raise RuntimeError('ordinary Revive requires its final native corpse budget guard')
            return super().execute(action, before_submit=self.revive_before_submit)
        return super().execute(action, before_submit=before_submit)


def hunter_vitals(oracle):
    # Native class power indexing places this Hunter's primary focus in slot0.
    return vitals(oracle)


def caption(t, session):
    known = wire_known(t, session)
    if 982 not in known:
        raise RuntimeError('actual same-entry native Revive982 is not known')
    t.clean_panels()
    require(click_case(t, 'fixture.revive.book', 'Inspect the stock Revive Pet caption.',
        lambda c: c['name'] == 'SpellbookMicroButton', lambda b, a, s:
        {'status': 'spellbook_open_pass' if s and 'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
        hold=.4), 'spellbook_open_pass')
    try:
        tabs = detail(t, 'revive_tabs')['tabs']
        for tab in sorted(tabs, key=lambda r: r.get('name') != 'Beast Mastery'):
            if tab.get('hidden') or tab.get('guild'): continue
            line = tab['index']
            require(navigate(t, known, 'fixture.revive.line' + str(line), 'SpellBookSkillLineTab' + str(line),
                line=line, check_content=False), 'spellbook_navigation_pass')
            for page in range(3):
                probe = detail(t, 'revive_page' + str(line) + '_' + str(page), line=line)
                rows = [r for r in probe['rows'] if r.get('id') == 982 and r.get('known') is True and
                    r.get('kind') == 'SPELL' and r.get('name') == 'Revive Pet']
                if len(rows) == 1: return rows[0]
                if probe.get('page', 0) >= probe.get('max_pages', 0): break
                require(navigate(t, known, 'fixture.revive.next' + str(line) + '_' + str(page),
                    'SpellBookNextPageButton', page=probe['page'] + 1, check_content=False), 'spellbook_navigation_pass')
        raise RuntimeError('Revive982 is absent from the bounded stock spellbook')
    finally:
        t.clean_panels()


def context(t, preparation, entry, fixture_path, allow_expired=False):
    old = prepared(t, preparation)
    session = actors.session_entry(t.fixture)['session']
    entered = entry_source(t, entry, session, preparation)
    fixture = closed(fixture_path)
    if (fixture.get('phase') != 'owned_revive_dead_fixture_staged' or t.fixture.get('guid') != 6 or
        old.get('fixture_source') != bound(fixture_path) or fixture['runtime']['worldserver'] != t.receipt['runtime']['worldserver'] or
        fixture['runtime']['modern_world'] != t.receipt['runtime']['modern_world'] or
        saved(6) != old['natural_saved'] or not all(protected(old).values())):
        raise RuntimeError('exact disposable dead-pet preparation or protected actors differ')
    oracle = RevivePresence(session, 6, entered['started_at']).poll()
    fields = oracle.pet['fields'] if oracle.pet else {}
    current = pets(6)
    dead = [p for p in current if p['id'] == 16 and p['curhealth'] == 0 and p['slot'] == 0]
    expired = (allow_expired and oracle.pet and oracle.pet['guid'] in oracle.removed and
        pair(oracle.player, 'UNIT_FIELD_SUMMON') == 0 and len(dead) == 1 and dead[0]['active'] == 0)
    if ((not oracle.present() and not expired) or fields.get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or
        fields.get(INDEX['OBJECT_FIELD_ENTRY']) != 299 or pair(fields, 'UNIT_FIELD_SUMMONEDBY') != 6 or
        fields.get(INDEX['UNIT_CREATED_BY_SPELL']) not in (13481, 883) or
        not dead_pet_rows(fixture, current) or
        fields.get(INDEX['UNIT_FIELD_HEALTH'], 0) != 0 or not fields.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0) or
        vitals(oracle)['UNIT_FIELD_HEALTH'] != 209):
        raise RuntimeError('requires the actual dead native owned Wolf16 and healthy owner')
    inventory = Inventory(lab.ROOT, session, 6).poll()
    if resources(inventory) != entered['resources']:
        raise RuntimeError('owner resources changed before Revive')
    return old, entered, fixture, session, oracle, inventory


def ready(t, oracle):
    read_page(t, 'revive_core_state', 'state', '/tcui')
    state, frame = t.observe('revive_dead_target')
    oracle.poll()
    if (state.get('target', {}).get('guid') != expected_guid(oracle.pet) or
        state['target'].get('health') != 0 or state['target'].get('name') != 'Wolf' or
        pair(oracle.player, 'UNIT_FIELD_TARGET') != oracle.pet['guid'] or
        state.get('panels') or state.get('lua_errors') or state.get('blocked_actions')):
        raise RuntimeError('actual stock dead-pet target or native selection differs')
    return state, frame


def load_dead(t, oracle, session, fixture_guard=None):
    if oracle.poll().present(): return
    if 883 not in wire_known(t, session): raise RuntimeError('ordinary Call Pet1 is not native-known')
    since = time.time()
    old_guid = oracle.pet['guid']
    t.receipt.update(call_dead_pet_started_at=since, call_dead_pet_fixture_only=True, call_dead_pet_input_sent=False)
    t.persist()
    def before_call(state):
        oracle.poll()
        if (oracle.present() or oracle.pet['guid'] != old_guid or not dead_identity(oracle.pet) or
            old_guid not in oracle.removed or pair(oracle.player, 'UNIT_FIELD_SUMMON') != 0 or
            t.receipt['call_dead_pet_input_sent']):
            raise RuntimeError('fixture CallPet requires the same expired absent corpse; no CallPet submitted')
        if fixture_guard is not None: fixture_guard()
        t.receipt.update(call_dead_pet_input_sent=True, call_dead_pet_submitted_at=time.time(),
            call_dead_pet_absence_before_submission={'guid': old_guid, 'native_present': False, 'native_summon': 0})
        t.persist()
    t.execute({'kind': 'chat', 'value': '/cast Call Pet 1'}, before_submit=before_call)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        oracle.poll()
        if oracle.present(): break
        time.sleep(.1)
    requested = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl') if
        p.get('session') == session and p.get('name') == 'CMSG_CAST_SPELL' and
        p.get('direction') == 'to_native' and p.get('time', 0) >= since]
    t.receipt['call_dead_pet_native_requests'] = requested
    t.persist()
    if (len(requested) != 1 or cast_identity(requested[0])['spell'] != 883 or
        not oracle.present() or oracle.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or
        oracle.pet['fields'].get(INDEX['UNIT_FIELD_HEALTH'], 0) != 0):
        raise RuntimeError('one ordinary fixture Call Pet did not load the same dead Wolf16')
    bind_call_lifetime(oracle, since, requested)
    t.execute({'kind': 'chat', 'value': '/targetexact Wolf'})


def guard_fixture(t, old, fixture, inventory, oracle, owner_vitals):
    if (saved(6) != old['natural_saved'] or not all(protected(old).values()) or
        not dead_pet_rows(fixture, pets(6)) or hunter_vitals(oracle.poll()) != owner_vitals or
        resources(inventory) != t.receipt['baseline_resources']):
        raise RuntimeError('dead-pet fixture, named pet, owner resources or protected actors changed')


def prepare_cast_corpse(t, oracle, session, old, fixture, inventory, owner_vitals):
    oracle.poll()
    budget = corpse_budget(oracle, time.time())
    t.receipt['reviewed_corpse_budget'] = budget
    t.receipt['reviewed_same_pet_fixture_recovery'] = not oracle.present() or not budget['setup_budget']
    t.persist()
    if oracle.present() and not budget['setup_budget']:
        guid = oracle.pet['guid']
        wait = {'guid': guid, 'started_at': time.time(), 'inputs_sent': False, 'initial_budget': budget}
        t.receipt['natural_corpse_expiry_wait'] = wait
        t.persist()
        # An unbound login corpse may have nearly its full lifetime remaining.
        # Wait for destruction and cleared ownership, never dismiss or reload it
        # while present. Packet receipt alone cannot establish its death clock.
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            oracle.poll()
            if oracle.pet['guid'] != guid or not dead_identity(oracle.pet):
                raise RuntimeError('reviewed dead corpse changed during its natural expiry wait')
            if guid in oracle.removed and pair(oracle.player, 'UNIT_FIELD_SUMMON') == 0: break
            time.sleep(.1)
        else: raise RuntimeError('reviewed corpse did not expire naturally within its bounded wait')
        wait.update(finished_at=time.time(), destruction_packet=oracle.destructions.get(guid),
            native_summon_cleared=True)
        t.persist()
    guard_fixture(t, old, fixture, inventory, oracle, owner_vitals)
    load_dead(t, oracle, session, lambda: guard_fixture(t, old, fixture, inventory, oracle, owner_vitals))
    before, frame = ready(t, oracle)
    guard_fixture(t, old, fixture, inventory, oracle, owner_vitals)
    budget = corpse_budget(oracle.poll(), time.time())
    t.receipt['pre_chat_corpse_budget'] = budget
    t.persist()
    if not budget['native_present'] or not budget['setup_budget']:
        raise RuntimeError('dead-pet readiness exhausted the setup budget; no Revive submitted')
    return before, frame


def final_submission(t, oracle, old, fixture, inventory, owner_vitals, pet_guid, state):
    if t.receipt.get('input_sent') or t.receipt.get('cast_input_sent'):
        raise RuntimeError('the one ordinary Revive has already been submitted; refusing another Return')
    guard_fixture(t, old, fixture, inventory, oracle, owner_vitals)
    budget = corpse_budget(oracle.poll(), time.time())
    valid = (budget['native_present'] and budget['submission_budget'] and budget['guid'] == pet_guid and
        pair(oracle.player, 'UNIT_FIELD_TARGET') == pet_guid and
        state.get('target', {}).get('guid') == expected_guid(oracle.pet) and
        state['target'].get('health') == 0 and state['target'].get('name') == 'Wolf' and
        not state.get('panels') and not state.get('lua_errors') and not state.get('blocked_actions'))
    t.receipt.update(final_submission_corpse_budget=budget, final_submission_ready=bool(valid))
    t.persist()
    if not valid:
        raise RuntimeError('dead corpse lacks the final native/public cast budget; no Revive submitted')
    t.receipt.update(cast_started_at=time.time(), input_sent=True, cast_input_sent=True)
    t.persist()


def capture_outcome(t, oracle, **details):
    # Regeneration is observed later through the same mutable native oracle.
    # Freeze the pet at this capture window rather than moving its proof ahead.
    t.receipt.update(**details, native_pet_after=deepcopy(oracle.pet))
    t.persist()


def run(t, preparation, entry, fixture_path, action, source, review_path):
    old, entered, fixture, session, oracle, inventory = context(t, preparation, entry, fixture_path, True)
    t.receipt.update(native_session=session, entry_source=bound(entry), dead_fixture_source=bound(fixture_path),
        baseline_resources=resources(inventory), baseline_saved=saved(6), native_reviewed_pet=deepcopy(oracle.pet),
        native_pet_before=deepcopy(oracle.pet), qualification_added=False, input_sent=False, cast_input_sent=False)
    owner_vitals = hunter_vitals(oracle)
    if action == 'recon':
        spell = caption(t, session)
        state, frame = prepare_cast_corpse(t, oracle, session, old, fixture, inventory, owner_vitals)
        t.receipt.update(revive_spell=spell, state=state, frame=frame, protected_checks=protected(old),
            native_ready_pet=deepcopy(oracle.pet), native_corpse_budget=corpse_budget(oracle, time.time()),
            completed=True, phase='await_owned_revive_cast_review')
        return
    recon = closed(source)
    if (recon.get('phase') != 'await_owned_revive_cast_review' or recon.get('runtime') != t.receipt['runtime'] or
        recon.get('actor') != t.fixture or recon.get('dead_fixture_source') != bound(fixture_path) or
        recon.get('entry_source') != bound(entry) or recon.get('revive_spell', {}).get('id') != 982):
        raise RuntimeError('closed same-entry observed Revive caption differs')
    if (recon.get('native_ready_pet', {}).get('guid') == oracle.pet['guid'] and
        recon.get('call_dead_pet_started_at') is not None):
        bind_call_lifetime(oracle, recon['call_dead_pet_started_at'], recon.get('call_dead_pet_native_requests', []))
    if action == 'cast':
        checked = reviewed(t, review_path, 'Revive Pet')
        if checked.get('source') != bound(source) or checked.get('frame') != recon['frame']:
            raise RuntimeError('Revive review differs from the exact current dead-pet frame')
    if action == 'cast':
        before, frame = prepare_cast_corpse(t, oracle, session, old, fixture, inventory, owner_vitals)
    else:
        load_dead(t, oracle, session, lambda: guard_fixture(t, old, fixture, inventory, oracle, owner_vitals))
        before, frame = ready(t, oracle)
    if action == 'refresh':
        t.receipt.update(revive_spell=recon['revive_spell'], recon_source=bound(source), state=before, frame=frame,
            native_ready_pet=deepcopy(oracle.pet), native_corpse_budget=corpse_budget(oracle, time.time()),
            completed=True, phase='await_owned_revive_cast_review')
        return
    pet_guid = oracle.pet['guid']
    pet_max_health = oracle.pet['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]
    t.receipt.update(recon_source=bound(source), revive_spell=recon['revive_spell'],
        native_vitals_before=owner_vitals, native_pet_before=deepcopy(oracle.pet),
        ordinary_input={'kind': 'chat', 'value': '/cast Revive Pet'}, chat_setup_started_at=time.time())
    t.persist()
    t.revive_before_submit = lambda state: final_submission(
        t, oracle, old, fixture, inventory, owner_vitals, pet_guid, state)
    try: t.execute(t.receipt['ordinary_input'])
    finally: t.revive_before_submit = None
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        oracle.poll()
        if oracle.present() and oracle.pet['fields'].get(INDEX['UNIT_FIELD_HEALTH'], 0) > 0: break
        time.sleep(.25)
    until = time.time()
    packets = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl') if p.get('session') == session and
        t.receipt['cast_started_at'] <= p.get('time', 0) <= until and p.get('name') in
        ('CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO', 'SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER')]
    parsed = [(p, cast_identity(p)) for p in packets if p['name'] != 'SMSG_SPELL_START']
    modern = [row for p, row in parsed if row and p['direction'] == 'from_client' and p['name'] == 'CMSG_CAST_SPELL']
    native = [row for p, row in parsed if row and p['direction'] == 'to_native' and p['name'] == 'CMSG_CAST_SPELL']
    go = [row for p, row in parsed if row and p['direction'] == 'from_native' and p['name'] == 'SMSG_SPELL_GO' and row['spell'] == 982]
    failures = [p for p in packets if p['name'] in ('SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER')]
    timing = native_revive_timing(packets, native[0], t.receipt['final_submission_corpse_budget']['lifetime_started_at']) if len(native) == 1 else {}
    after, outcome_frame = t.observe('revive_outcome')
    fields = oracle.pet['fields'] if oracle.pet else {}
    checks = {'one_modern_cast': len(modern) == 1 and modern[0]['spell'] == 982,
        'one_native_cast': len(native) == 1 and native[0]['spell'] == 982,
        'matching_native_completion': len(go) == 1 and len(native) == 1 and
            go[0]['counter'] == native[0]['counter'] and go[0]['caster'] == go[0]['unit'] == 6,
        'no_failure_packets': not failures,
        'native_cast_timing': timing.get('one_matching_start_and_completion') is True and
            timing.get('native_completion_ordered') is True and
            timing.get('native_ten_second_cast') is True and timing.get('completion_within_conservative_corpse_deadline') is True,
        'same_owned_pet': oracle.present() and oracle.pet['guid'] == pet_guid and
            fields.get(INDEX['UNIT_FIELD_PETNUMBER']) == 16 and pair(fields, 'UNIT_FIELD_SUMMONEDBY') == 6,
        'native_dead_to_alive': fields.get(INDEX['UNIT_FIELD_HEALTH'], 0) > 0,
        'public_owned_living_pet': after.get('target', {}).get('guid') == expected_guid(oracle.pet) and
            after['target'].get('health', 0) > 0,
        'owner_health_unchanged': hunter_vitals(oracle)['UNIT_FIELD_HEALTH'] == owner_vitals['UNIT_FIELD_HEALTH'],
        'resources': resources(inventory) == t.receipt['baseline_resources'],
        'saved_rows': saved(6) == t.receipt['baseline_saved'],
        'no_public_errors': not after.get('errors'),
        'ui_clean': not after.get('lua_errors') and not after.get('blocked_actions'), **protected(old)}
    capture_outcome(t, oracle, cast_finished_at=until, cast_packets=packets, native_cast_requests=native,
        modern_cast_requests=modern, native_completions=go, failure_packets=failures,
        native_cast_timing=timing,
        capture_checks=checks, outcome_state=after, outcome_frame=outcome_frame)
    if not all(checks.values()):
        raise RuntimeError('one ordinary Revive did not pass native and public outcome checks; do not replay')
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        oracle.poll()
        if oracle.pet['fields'].get(INDEX['UNIT_FIELD_HEALTH']) == pet_max_health and hunter_vitals(oracle) == owner_vitals: break
        time.sleep(1)
    lab.server_command('saveall')
    time.sleep(.5)
    t.execute({'kind': 'chat', 'value': '/cleartarget'})
    t.clean_panels()
    read_page(t, 'revive_restored_core', 'state', '/tcui')
    state, frame = t.observe('revive_restored')
    restored = pets(6)
    restoration = {**origin_checks(old), **protected(old),
        'stored_named_pet': restored[0] == fixture['before']['6']['pets'][0],
        'living_disposable_pet': len(restored) == 2 and restored[1]['id'] == 16 and
            restored[1]['curhealth'] == pet_max_health and restored[1]['slot'] == 0 and restored[1]['active'] == 1,
        'owner_vitals': hunter_vitals(oracle.poll()) == owner_vitals,
        'owner_resources': resources(inventory) == t.receipt['baseline_resources'],
        'saved_rows': saved(6) == t.receipt['baseline_saved'],
        'owner_position': state['world_position'] == before['world_position'],
        'empty_selection': not state['target'].get('exists') and pair(oracle.player, 'UNIT_FIELD_TARGET') == 0,
        'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    public = public_pet(t, 'revive_public_pet')
    restoration['public_owned_pet'] = public.get('exists') is True and public.get('guid') == expected_guid(oracle.pet)
    read_page(t, 'revive_final_core', 'state', '/tcui')
    t.clean_panels()
    t.receipt.update(restoration_checks=restoration, retained_pet_after=restored, restored_frame=frame,
        restored_state=state, public_pet=public, native_pet_max_health=pet_max_health,
        restored_native_pet=deepcopy(oracle.pet),
        offline_fixture_normalization_pending=True)
    if not all(restoration.values()): raise RuntimeError('Revive fixture restoration differs')
    t.receipt.update(completed=True, phase='owned_revive_cast_complete', qualified_scope=
        'One ordinary Revive982 on offline-prepared dead disposable Wolf16, native/public outcome and full resources/pet restoration. '
        'Natural combat death and other class/pet variants remain open.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['recon', 'refresh', 'cast'])
    for key in ('preparation', 'entry', 'fixture', 'output'): parser.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'review'): parser.add_argument('--' + key, type=Path)
    args = parser.parse_args()
    with actor('scout'):
        trial = ReviveTrial(args.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        trial.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try: run(trial, args.preparation, args.entry, args.fixture, args.action, args.source, args.review)
        except Exception as error: trial.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        finally:
            trial.receipt['finished_at'] = time.time()
            trial.persist()
        print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure', 'capture_checks', 'restoration_checks')}), flush=True)
