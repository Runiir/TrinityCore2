"""Apply a learned glyph through the stock catalog and observed socket controls."""
import argparse
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls, point, click_case
from .interaction_macros import require, edit_case
from .interaction_trade import inventory
from .interaction_talents import native_state, glyph_detail, detail
from .interaction_glyph_learn import spells, LEARNED
from .interaction_fixture_permissions import item_fixture_permission
from .interaction_crafting import fixture_command
from .observation.inventory import Inventory
from .observation.journal import entries

GLYPH = 483
SOCKET = 2
AURA = 58095
POWDER = 64670


def open_glyphs(t):
    require(t.step('glyphs.application_open', 'Open the talents window.',
        {'open': {'kind': 'key', 'value': 'n', 'description': 'Open talents with N.'}},
        lambda b,a,s: {'status': 'talents_open_pass' if 'PlayerTalentFrame' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='open', await_state=lambda s: 'PlayerTalentFrame' in s['panels']), 'talents_open_pass')
    state,_ = t.observe('selected_tab')
    if state.get('talent_probe', {}).get('selected') != 3:
        require(click_case(t, 'glyphs.application_tab', 'Open glyphs.',
            lambda c: c['name'] == 'PlayerTalentFrameTab3',
            lambda b,a,s: {'status': 'glyph_panel_pass' if s and a.get('talent_probe', {}).get('selected') == 3 else
                'client_or_protocol_failure'}), 'glyph_panel_pass')


def suite(t, remove_source=None, removal_powder=False, recover_applied=False):
    session = actors.session_entry(t.fixture)['session']
    t.clean_panels()
    before,items,known = native_state(),inventory(),spells()
    if not any(r[0] == LEARNED and r[1:] == (1,0) for r in known):
        raise RuntimeError('Battle must have been learned normally before its application trial')
    expected = [0]*9
    if remove_source:
        prior = json.loads(remove_source.read_text())
        recovered = (recover_applied and prior.get('finished_at') and not prior.get('completed') and
            prior.get('socket_semantics_oracle', {}).get('passed') and
            prior.get('application_oracle', {}).get('public_socket', {}).get('spell') == AURA and
            prior.get('restoration', {}).get('glyph_state_preserved_for_followup') == json.loads(json.dumps(before['glyphs'])) and
            all(prior.get('restoration', {}).get(k) for k in ['inventory_money_unchanged', 'learned_spells_preserved', 'talents_unchanged']))
        if (not (prior.get('completed') and prior.get('application_oracle', {}).get('passed') or recovered) or
                prior['actor'] != t.fixture):
            raise RuntimeError('removal requires a closed successful owned glyph application')
        expected[SOCKET-1] = GLYPH
        t.receipt['application_source'] = {'file': str(remove_source), 'sha256': lab.sha256(remove_source)}
        t.receipt['closed_failed_application_state_recovered'] = bool(recovered)
    if len(before['glyphs']) != 1 or list(before['glyphs'][0][2:]) != expected:
        raise RuntimeError('native glyph fixture differs from the registered socket baseline')
    t.receipt['baseline'] = {'talents': before, 'inventory_money': items, 'spells': known}
    t.persist()
    oracle = Inventory(lab.ROOT, session, 1).poll()
    if removal_powder and (not remove_source or oracle.count(POWDER)):
        raise RuntimeError('removal powder requires an owned applied glyph and zero pre-existing powder')
    try:
        if removal_powder:
            with item_fixture_permission(t):
                fixture_command(t, '/cleartarget', 'powder fixture targets only the owned actor')
                fixture_command(t, f'.additem {POWDER} 1', 'one disposable Vanishing Powder for ordinary glyph removal')
                deadline=time.monotonic()+12
                while oracle.poll().count(POWDER) != 1:
                    if time.monotonic()>deadline: raise RuntimeError('native powder fixture did not settle')
                    time.sleep(.2)
            t.receipt['powder_fixture'] = {'item': POWDER, 'before': 0, 'prepared': 1}; t.persist()
        open_glyphs(t)
        if not remove_source:
            require(edit_case(t, 'glyphs.application_search', 'Find the learned Battle glyph.',
                lambda c: c['name'] == 'GlyphFrameSearchBox', 'Battle'), 'ui_edit_pass')
            catalog = glyph_detail(t, 'battle_catalog')
            battle = [r for r in catalog['rows'] if r.get('id') == GLYPH]
            if len(battle) != 1 or not battle[0].get('known'):
                raise RuntimeError('public catalog does not show one learned Battle glyph')
            candidates = [c for c in controls(t) if c['enabled'] and c['kind'] == 'Button' and
                c['name'].startswith('GlyphFrameScrollFrameButton') and c['text'] == 'Battle']
            t.receipt['catalog_controls'] = candidates; t.persist()
            if len(candidates) != 1:
                raise RuntimeError('learned Battle catalog button is absent or ambiguous')
            require(t.step('glyphs.select_learned', 'Select Battle for placement.',
                {'select': {'kind': 'click', 'value': point(candidates[0]), 'description': 'Select the observed learned Battle glyph.'}},
                lambda b,a,s: {'status': 'glyph_pending_pass' if a.get('pending_glyph') else 'client_or_protocol_failure',
                    'oracle': {'pending_glyph': a.get('pending_glyph')}},
                diagnostic_action='select', await_state=lambda s: bool(s.get('pending_glyph'))), 'glyph_pending_pass')
            pending = detail(t, 'pending_minor_socket')
            matching = [r['index'] for r in pending['glyphs'] if r.get('matches_pending')]
            t.receipt['socket_semantics_oracle'] = {'public_types': [r['type'] for r in pending['glyphs']],
                'pending_name': pending.get('pending_glyph'), 'matching_sockets': matching,
                'passed': matching == [2,3,5] and [r['type'] for r in pending['glyphs']] == [1,2,2,1,2,1,3,3,3]}
            t.persist()
            if not t.receipt['socket_semantics_oracle']['passed']:
                raise RuntimeError('the learned Minor glyph does not match exactly the three stock Minor sockets')
        candidates = [c for c in controls(t) if c['enabled'] and c['name'] == 'GlyphFrameGlyph'+str(SOCKET)]
        if len(candidates) != 1:
            raise RuntimeError('the observed Minor socket is absent or ambiguous')
        started = time.time()
        if remove_source:
            require(t.step('glyphs.remove_dialog', 'Request removal of Battle.',
                {'remove': {'kind': 'click', 'value': point(candidates[0]), 'button': 3, 'modifiers': ['shift'],
                    'description': 'Shift-right-click the occupied Minor socket.'}},
                lambda b,a,s: {'status': 'glyph_remove_dialog_pass' if any('StaticPopup' in p for p in a['panels']) else
                    'client_or_protocol_failure'}, diagnostic_action='remove',
                await_state=lambda s: any('StaticPopup' in p for p in s['panels'])), 'glyph_remove_dialog_pass')
            popup = detail(t, 'remove_confirmation')
            if len(popup['popups']) != 1 or popup['popups'][0]['which'] != 'CONFIRM_REMOVE_GLYPH':
                raise RuntimeError('ordinary removal did not show the expected confirmation')
            buttons = [c for c in controls(t) if c['enabled'] and c['name'] == popup['popups'][0]['name']+'Button1']
            if len(buttons) != 1: raise RuntimeError('glyph removal confirmation is absent or ambiguous')
            action = {'kind': 'click', 'value': point(buttons[0]), 'description': 'Confirm removal in the observed glyph popup.'}
        else:
            action = {'kind': 'click', 'value': point(candidates[0]), 'description': 'Place Battle in the observed empty Minor socket.'}
        key = 'removal' if remove_source else 'application'
        def outcome(b,a,s):
            public = detail(t, key+'_socket')
            target = next(r for r in public['glyphs'] if r['index'] == SOCKET)
            wanted = [0]*9
            if not remove_source: wanted[SOCKET-1] = GLYPH
            # Cursor closure precedes the glyph cast completion. Read the public
            # outcome first, then save native state; poll the native result with
            # a bounded deadline rather than declaring a pre-effect DB row final.
            deadline=time.monotonic()+12
            while True:
                actual = native_state()
                native_ok = len(actual['glyphs']) == 1 and list(actual['glyphs'][0][2:]) == wanted
                if native_ok or time.monotonic()>deadline: break
                time.sleep(.2)
            # Stock GetGlyphSocketInfo exposes the aura spell, but no sixth
            # glyph ID on this build. The pinned Battle aura identifies it.
            public_ok = target.get('spell', 0) == (0 if remove_source else AURA) and target.get('type') == 2
            packets = [p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session') == session and
                p.get('time', 0) >= started and p.get('name') in ['CMSG_CAST_SPELL', 'CMSG_REMOVE_GLYPH', 'CMSG_USE_ITEM',
                    'SMSG_SPELL_START', 'SMSG_SPELL_GO', 'SMSG_CAST_FAILED', 'SMSG_TALENTS_INFO']]
            consumed = not removal_powder or oracle.poll().count(POWDER) == 0
            passed = native_ok and public_ok and consumed and not a.get('lua_errors')
            t.receipt[key+'_oracle'] = {'passed': passed, 'native': actual, 'public_socket': target,
                'native_socket_matches': native_ok, 'public_socket_matches': public_ok, 'powder_consumed': consumed, 'packets': packets}
            t.persist()
            return {'status': 'glyph_'+key+'_pass' if passed else 'client_or_protocol_failure',
                'oracle': t.receipt[key+'_oracle']}
        require(t.step('glyphs.'+key, 'Remove Battle.' if remove_source else 'Apply Battle to the empty Minor socket.',
            {'act': action}, outcome, diagnostic_action='act', await_state=lambda s: not s.get('pending_glyph') and
                (not remove_source or not any('StaticPopup' in p for p in s['panels']))), 'glyph_'+key+'_pass')
    finally:
        t.clean_panels()
        if removal_powder and oracle.poll().count(POWDER):
            if oracle.count(POWDER) != 1: raise RuntimeError('unexpected powder quantity after removal')
            with item_fixture_permission(t):
                fixture_command(t, '/cleartarget', 'restore only the owned powder fixture')
                fixture_command(t, f'.additem {POWDER} -1', 'remove only unused disposable powder')
                deadline=time.monotonic()+12
                while oracle.poll().count(POWDER):
                    if time.monotonic()>deadline: raise RuntimeError('unused powder removal did not settle')
                    time.sleep(.2)
        after = native_state()
        t.receipt['restoration'] = {'inventory_money_unchanged': inventory() == items, 'learned_spells_preserved': spells() == known,
            'talents_unchanged': after['character'] == before['character'] and after['talents'] == before['talents'],
            'glyph_state_preserved_for_followup': after['glyphs']}
        t.persist()
        if not all(v for k,v in t.receipt['restoration'].items() if k != 'glyph_state_preserved_for_followup'):
            raise RuntimeError('glyph action changed unrelated character state')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--remove-source', type=Path)
    p.add_argument('--removal-powder', action='store_true')
    p.add_argument('--recover-applied', action='store_true', help='Recover retained native/public placement from a closed failed oracle')
    a = p.parse_args()
    t = Trial(a.output, controller='code')
    try: suite(t, a.remove_source, a.removal_powder, a.recover_applied); t.receipt['completed'] = True
    except Exception as e: t.receipt['failure'] = f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at'] = time.time(); t.persist()
        print(json.dumps({'completed': t.receipt['completed'], 'failure': t.receipt['failure']}), flush=True)
