"""Qualify the installed Classic guild UI opening path and restore its preference."""
import argparse
import json
from pathlib import Path
import time

from .interaction_trial import Trial
from .interaction_operations import controls
from .interaction_macros import require
from . import lab_runtime as lab


def suite(trial):
    trial.clean_panels()
    state, frame = trial.observe('guild_preference_baseline')
    baseline = state.get('guild_ui', {}).get('classic')
    if not isinstance(baseline, bool):
        raise RuntimeError('Classic guild preference is not observable')
    trial.receipt['guild_fixture'] = {'baseline': state['guild_ui'], 'frame': frame,
                                    'qualified_scope': 'opening Classic guild UI only'}
    trial.persist()
    with lab.connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT g.guildid,g.name FROM client442_characters.guild g JOIN client442_characters.guild_member m '
                       'ON m.guildid=g.guildid WHERE m.guid=%s', (trial.fixture['guid'],))
        guild = cursor.fetchone()
        if not guild:
            raise RuntimeError('guild trial requires native owned membership')
        cursor.execute('SELECT c.name,c.level,m.rank FROM client442_characters.guild_member m '
                       'JOIN client442_characters.characters c ON c.guid=m.guid WHERE m.guildid=%s', (guild[0],))
        members = cursor.fetchall()
    trial.receipt['native_guild_fixture'] = {'guild_id': guild[0], 'name': guild[1], 'members': members}
    trial.persist()
    try:
        trial.receipt.setdefault('fixture_inputs', []).append({'time': time.time(), 'source': 'code_fixture',
            'input': '/console useClassicGuildUI 1', 'reason': 'use the installed local guild UI while Battle.net clubs are disabled'})
        trial.persist()
        trial.execute({'kind': 'chat', 'value': '/console useClassicGuildUI 1'})
        state, _ = trial.observe('classic_preference_enabled')
        if state.get('guild_ui', {}).get('classic') is not True:
            raise RuntimeError('normal console command did not enable the Classic guild preference')
        require(trial.step('guild.classic_open', 'Open the guild window.', {
            'guild': {'kind': 'key', 'value': 'j', 'description': 'Press J to open the guild window.'},
            'friends': {'kind': 'key', 'value': 'o', 'description': 'Press O to open friends.'},
            'map': {'kind': 'key', 'value': 'm', 'description': 'Press M to open the world map.'}},
            lambda b, a, s: {'status': 'panel_open_pass' if 'GuildFrame' in a['panels'] else
                ('controller_failure' if s != 'guild' else 'client_or_protocol_failure'),
                'oracle': {'panels': a['panels'], 'guild_ui': a['guild_ui'], 'lua_errors': a['lua_errors'],
                           'qualified_scope': 'panel visibility only; membership and guild mutations still pending'}}),
            'panel_open_pass')
        lab.private_write(trial.out / 'guild_controls.json', json.dumps(controls(trial), indent=2) + '\n')
        after, frame = trial.observe('guild_roster_contents')
        observed = after.get('guild_ui', {})
        native = {(name, level, rank) for name, level, rank in members}
        visible = {(m['name'].split('-', 1)[0], m['level'], m['index']) for m in observed.get('members', [])}
        passed = observed.get('name') == guild[1] and observed.get('member_count') == len(members) and native == visible
        row = {'id': 'guild.roster_contents', 'status': 'guild_roster_pass' if passed else 'client_or_protocol_failure',
               'selection_source': 'read_only_native_oracle', 'time': time.time(), 'after': after, 'after_frame': frame,
               'oracle': {'native_name': guild[1], 'native_members': members, 'visible': observed,
                          'qualified_scope': 'guild identity and roster name level rank, not guild mutations'}}
        trial.receipt['cases'].append(row); trial.persist(); require(row, 'guild_roster_pass')
    finally:
        trial.clean_panels()
        value = '/console useClassicGuildUI ' + str(int(baseline))
        trial.receipt.setdefault('fixture_inputs', []).append({'time': time.time(), 'source': 'code_fixture_cleanup',
            'input': value, 'reason': 'restore the original owned client preference'})
        trial.persist(); trial.execute({'kind': 'chat', 'value': value})
        state, frame = trial.observe('guild_preference_restored')
        trial.receipt['guild_preference_restored'] = {'matches': state['guild_ui']['classic'] == baseline, 'frame': frame}
        trial.persist()
        if not trial.receipt['guild_preference_restored']['matches']:
            raise RuntimeError('original guild preference was not restored')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); trial = Trial(args.output)
    try:
        suite(trial); trial.receipt['completed'] = True
    except Exception as e:
        trial.receipt['failure'] = f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at'] = time.time(); trial.persist()
        print(json.dumps({'completed': trial.receipt['completed'], 'failure': trial.receipt['failure']}))
