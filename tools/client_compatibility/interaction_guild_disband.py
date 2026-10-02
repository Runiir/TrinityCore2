"""Disband the explicitly owned disposable guild and restore its original absence."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_guild_commands import command
from .interaction_operations import click_case
from .interaction_macros import require


def guild():
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT guildid,leaderguid FROM client442_characters.guild WHERE name=%s',('Harness Ui Test',))
        row=cur.fetchone()
        if row:
            cur.execute('SELECT guid FROM client442_characters.guild_member WHERE guildid=%s',(row[0],))
            return row,{r[0] for r in cur.fetchall()}
    return None,set()


def suite(t):
    row,members=guild()
    if not row or row[1]!=t.fixture['guid'] or members!={t.fixture['guid']}:
        raise RuntimeError('disband requires the disposable guild with only its owned leader')
    t.receipt['fixture']={'guild_id':row[0],'original_pre_guild_experiment_state':'guild absent'};t.persist()
    try:
        t.clean_panels()
        require(command(t,'guild.disband_open','Disband the disposable test guild.','/gdisband','open guild disband confirmation',
            lambda b,a,s:{'status':'panel_open_pass' if s=='command' and 'StaticPopup1' in a['panels'] else
                ('controller_failure' if s!='command' else 'client_or_protocol_failure')}),'panel_open_pass')
        require(click_case(t,'guild.disband','Confirm disbanding the disposable test guild.',
            lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Yes','Accept','Okay'],
            lambda b,a,s:{'status':'guild_disband_pass' if s and not guild()[0] and not a['guild_ui']['in_guild'] else
                ('controller_failure' if not s else 'client_or_protocol_failure'),
                'oracle':{'native_guild':guild()[0],'in_guild':a['guild_ui']['in_guild'],'blocked_actions':a.get('blocked_actions')}}),'guild_disband_pass')
        t.receipt['completed']=True
    finally:
        t.clean_panels();row,members=guild()
        if row:
            if row[1]!=t.fixture['guid'] or members!={t.fixture['guid']}:
                raise RuntimeError('unrelated guild cleanup refused')
            lab.server_command('guild delete "Harness Ui Test"');time.sleep(1)
            t.receipt.setdefault('cleanup',[]).append({'source':'code_fixture_cleanup','purpose':'restore original guild absence'})
        state,frame=t.observe('restored')
        t.receipt['restoration']={'native_guild':guild()[0],'guild_ui':state['guild_ui'],'frame':frame}
        if guild()[0] or state['guild_ui']['in_guild']:raise RuntimeError('disposable guild removal did not settle')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    t=Trial(p.parse_args().output)
    try:suite(t)
    except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
