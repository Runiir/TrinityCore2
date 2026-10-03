"""Ordinary logout/reentry with a separately reviewed character-selection frame."""
import argparse
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .interaction_trial import Trial, binding_key
from .interaction_macros import require
from .interaction_lifecycle import Packets, request_logout
from .interaction_bridge_deploy import identity, shot
from .interaction_social import actor
from .interaction_archaeology_projects import native, completed_panel
from .interaction_quest_fixture import quest_state
from .observation.inventory import Inventory
from .world.objects import INDEX


def canonical(value):
    return json.loads(json.dumps(value))


def public(value):
    return {k: value.get(k) for k in ['guid', 'money', 'equipment', 'group',
        'raid_profile', 'quests', 'quest_headers', 'quest_entry_count']}


def facts(t, label):
    t.clean_panels()
    state, frame = t.observe(label)
    saved = {'archaeology': native(), 'quests': quest_state(t.fixture['guid'])}
    result = {'public': public(state), 'native': canonical(saved), 'frame': frame,
        'session': actors.session_entry(t.fixture)['session']}
    t.receipt.setdefault('facts', {})[label] = result
    t.persist()
    return result


def quest_panel(t, expected):
    state, _ = t.observe('quest_binding')
    keys = state.get('quest_log_keys') or []
    if not keys:
        raise RuntimeError('owned quest-log binding is absent')
    def outcome(b, a, s):
        observed = {q['id'] for q in a.get('quests', [])}
        wanted = {q['quest'] for q in expected['active']}
        checks = {'panel': 'QuestLogFrame' in a['panels'], 'all_active_ids': observed == wanted,
            'native_preserved': canonical(quest_state(t.fixture['guid'])) == expected,
            'ui_clean': not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status': 'quest_session_log_pass' if all(checks.values()) else
            'client_or_protocol_failure', 'oracle': {'checks': checks, 'public': a.get('quests'),
            'native': expected}}
    require(t.step('quests.session_log', 'Open the preserved quest log.',
        {'log': {'kind': 'key', 'value': binding_key(keys[0]),
                 'description': 'Press the observed quest-log binding.'}},
        outcome, diagnostic_action='log'), 'quest_session_log_pass')
    t.clean_panels()


def close(t, completed, error=None):
    t.receipt.update(completed=completed, failure=error, finished_at=time.time())
    t.persist()
    print(json.dumps({'completed': completed, 'failure': error}), flush=True)


def logout(out, earned_source):
    t = Trial(out, controller='code')
    try:
        source = earned_source.resolve()
        if not source.is_relative_to(lab.ROOT/'evidence') or source.name != 'episode.json':
            raise ValueError('require an owned closed earned archaeology episode')
        earned = json.loads(source.read_text())
        if not earned.get('completed') or earned.get('failure') or not earned.get('earned_state_retained'):
            raise RuntimeError('source earned episode did not pass')
        before = facts(t, 'before_logout')
        if before['native']['archaeology'] != earned['native_after']:
            raise RuntimeError('earned source differs from current native state')
        t.receipt.update(phase='logout', earned_source={'file': str(source), 'sha256': lab.sha256(source)},
            baseline=before, bridge=identity('modern_world'), native_server=identity('worldserver'))
        t.persist()
        completed_panel(t, 'before_logout_history', before['native']['archaeology'])
        quest_panel(t, before['native']['quests'])
        t.clean_panels()
        observed = Inventory(lab.ROOT, before['session'], t.fixture['guid']).poll()
        fields = observed.objects.get(t.fixture['guid'])
        flags = fields.get(INDEX['PLAYER_FLAGS'], 0) if fields else None
        if flags is None or flags & 0x20:
            raise RuntimeError('logout cancellation requires an observed non-resting character')
        t.receipt['native_logout_fixture'] = {'player_flags': flags, 'session': before['session']}
        t.persist()
        packets = Packets(before['session'])
        request_logout(t, packets, 'cancel', True)
        started = request_logout(t, packets, 'complete', False)
        deadline = time.monotonic()+32
        while not (packets.has(started, 'SMSG_LOGOUT_COMPLETE', 'from_native') and
                   packets.has(started, 'SMSG_ENUM_CHARACTERS_RESULT', 'from_native')):
            if time.monotonic() > deadline:
                raise RuntimeError('logout completion/enumeration deadline exceeded')
            time.sleep(.2)
        frame = shot(t.out/'character_selection.png')
        t.receipt['cases'].append({'id': 'lifecycle.logout_complete', 'status': 'logout_complete_pass',
            'selection_source': 'code', 'time': started, 'frame': frame,
            'oracle': {'native_completion': True, 'native_enumeration': True}})
        t.receipt['character_selection'] = frame
        close(t, True)
    except Exception as error:
        close(t, False, f'{type(error).__name__}: {error}')


def reenter(out, source):
    source = source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name != 'episode.json':
        raise ValueError('require an owned closed logout episode')
    prior = json.loads(source.read_text())
    if not prior.get('completed') or prior.get('failure') or prior.get('phase') != 'logout':
        raise RuntimeError('source logout did not pass')
    t = Trial(out, controller='code')
    try:
        if (t.receipt['runtime'] != prior['runtime'] or identity('worldserver') != prior['native_server'] or
                identity('modern_world') != prior['bridge'] or t.fixture != prior['actor']):
            raise RuntimeError('source actor/client/server lifetimes differ')
        t.receipt.update(phase='reenter', source={'file': str(source), 'sha256': lab.sha256(source)},
            reviewed_character_selection=prior['character_selection'], baseline=prior['baseline'])
        t.persist()
        packets = Packets(prior['baseline']['session'])
        frame = shot(t.out/'reviewed_character_selection_before.png')
        if frame['sha256'] != prior['character_selection']['sha256']:
            # Animated lobby backgrounds change pixels; retain the new owned
            # frame, but the explicit CLI option attests separate visual review.
            t.receipt['lobby_animation_changed'] = True
        started = time.time()
        t.execute({'kind': 'key', 'value': 'Return', 'hold': .4})
        time.sleep(8)
        after = facts(t, 'after_reentry')
        baseline = prior['baseline']
        checks = {'same_character': after['public']['guid'] == baseline['public']['guid'],
            'native_state': after['native'] == baseline['native'],
            'public_state': after['public'] == baseline['public'],
            'ordinary_login': packets.has(started, 'CMSG_PLAYER_LOGIN', 'from_client'),
            'native_login': packets.has(started, 'SMSG_LOGIN_VERIFY_WORLD', 'from_native')}
        t.receipt['cases'].append({'id': 'lifecycle.reenter', 'time': started,
            'status': 'session_persistence_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'selection_source': 'code', 'input': {'kind': 'key', 'value': 'Return'},
            'before_frame': frame, 'after_frame': after['frame'], 'oracle': {'checks': checks}})
        t.persist()
        if not all(checks.values()):
            raise RuntimeError('reentry identity/resources/quest/login checks differ')
        completed_panel(t, 'after_reentry_history', after['native']['archaeology'])
        quest_panel(t, after['native']['quests'])
        final = facts(t, 'after_panel_checks')
        if final['native'] != baseline['native']:
            raise RuntimeError('read-only reentry panels mutated native state')
        close(t, True)
    except Exception as error:
        close(t, False, f'{type(error).__name__}: {error}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['logout', 'reenter'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--reviewed-character-selection', action='store_true')
    a = p.parse_args()
    if a.action == 'reenter' and not a.reviewed_character_selection:
        p.error('reenter requires a separate visual review of the saved character-selection frame')
    with actor('primary'):
        if a.action == 'logout': logout(a.output, a.source)
        else: reenter(a.output, a.source)
