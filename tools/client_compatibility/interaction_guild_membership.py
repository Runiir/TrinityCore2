"""Two owned players qualify native guild membership and visible outcomes."""
import argparse
import json
from pathlib import Path
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_chat import packets


def membership(guid):
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT guildid,rank FROM client442_characters.guild_member WHERE guid=%s',(guid,))
        return cur.fetchone()


def text_command(trial,case,goal,value,oracle):
    return trial.step(case,goal,{
        'target':{'kind':'chat','value':value,'description':'Type '+value+' in normal chat.'},
        'friends':{'kind':'key','value':'o','description':'Open friends.'},
        'map':{'kind':'key','value':'m','description':'Open the map.'}},oracle,diagnostic_action='target')


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};baselines={};guild=None
    try:
        for name in ['primary','scout']:
            with actor(name):
                trial=trials[name]=Trial(out/name);actors.session_entry(trial.fixture);trial.clean_panels()
                state,_=trial.observe('fixture');baselines[name]=state['guild_ui']['classic']
                if state['lua_errors']:raise RuntimeError('fresh client has Lua errors')
        primary,scout=trials['primary'],trials['scout']
        own=membership(primary.fixture['guid'])
        if not own or own[1]!=0 or membership(scout.fixture['guid']):raise RuntimeError('requires leader guild and unguilded owned peer')
        with lab.connection() as con,con.cursor() as cur:
            cur.execute('SELECT name,leaderguid,motd FROM client442_characters.guild WHERE guildid=%s',(own[0],));guild=cur.fetchone()
            cur.execute('SELECT guid FROM client442_characters.guild_member WHERE guildid=%s',(own[0],));members=cur.fetchall()
        if guild[:2]!=('Harness Ui Test',primary.fixture['guid']) or {row[0] for row in members}!={primary.fixture['guid']}:
            raise RuntimeError('guild fixture is not the disposable owned cohort')
        cohort['guild_fixture']={'id':own[0],'name':guild[0],'leader':guild[1],'baseline_motd':guild[2]}
        def invite():
            with actor('primary'):
                since=time.time();session=actors.session_entry(primary.fixture)['session']
                def oracle(b,a,s):
                    rows=packets(session,since,'Harnesstwo')
                    sent=any(r['direction']=='to_native' and r['name']=='CMSG_GUILD_INVITE' for r in rows)
                    return {'status':'guild_invite_submitted' if s=='target' and sent else
                        ('controller_failure' if s!='target' else 'client_or_protocol_failure'),'oracle':{'native_invite_request':sent,'packets':rows}}
                require(text_command(primary,'guild.invite','Invite Harnesstwo to the test guild.','/ginvite Harnesstwo',oracle),'guild_invite_submitted')
        invite()
        with actor('scout'):
            require(click_case(scout,'guild.decline','Decline Harnessone\'s guild invitation.',
                lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Decline',
                lambda b,a,s:{'status':'guild_decline_pass' if s and not membership(scout.fixture['guid']) and
                    'StaticPopup1' not in a['panels'] else ('controller_failure' if not s else 'client_or_protocol_failure'),
                    'oracle':{'membership':membership(scout.fixture['guid']),'panels':a['panels']}}),'guild_decline_pass')
        invite()
        with actor('scout'):
            require(click_case(scout,'guild.accept','Join Harnessone\'s test guild.',
                lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Accept','Join Guild'],
                lambda b,a,s:{'status':'guild_accept_pass' if s and membership(scout.fixture['guid']) and a['guild_ui']['in_guild']
                    and a['guild_ui'].get('name')==guild[0] else ('controller_failure' if not s else 'client_or_protocol_failure'),
                    'oracle':{'membership':membership(scout.fixture['guid']),'visible':a['guild_ui']}}),'guild_accept_pass')
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name];t.execute({'kind':'chat','value':'/console useClassicGuildUI 1'})
                require(t.step('guild.open_roster','Open the guild roster.',{
                    'guild':{'kind':'key','value':'j','description':'Open guild with J.'},
                    'friends':{'kind':'key','value':'o','description':'Open friends with O.'},
                    'map':{'kind':'key','value':'m','description':'Open map with M.'}},
                    lambda b,a,s:{'status':'guild_roster_pass' if s=='guild' and 'GuildFrame' in a['panels'] and
                        {m['name'].split('-',1)[0] for m in a['guild_ui'].get('members',[])}=={'Harnessone','Harnesstwo'}
                        and not a['lua_errors'] else ('controller_failure' if s!='guild' else 'client_or_protocol_failure'),
                        'oracle':{'guild':a['guild_ui'],'lua_errors':a['lua_errors']}},diagnostic_action='guild'),'guild_roster_pass')
        with actor('primary'):
            token='TC442UI:motd'
            def motd(b,a,s):
                with lab.connection() as con,con.cursor() as cur:
                    cur.execute('SELECT motd FROM client442_characters.guild WHERE guildid=%s',(own[0],));native=cur.fetchone()[0]
                return {'status':'guild_motd_pass' if s=='target' and native==token and a['guild_ui'].get('motd')==token else
                    ('controller_failure' if s!='target' else 'client_or_protocol_failure'),'oracle':{'native':native,'visible':a['guild_ui'].get('motd')}}
            require(text_command(primary,'guild.motd','Set the guild message of the day to '+token+'.','/gmotd '+token,motd),'guild_motd_pass')
        with actor('scout'):
            state,frame=scout.observe('peer_motd');row={'id':'guild.motd_peer','time':time.time(),
                'status':'guild_motd_peer_pass' if state['guild_ui'].get('motd')==token else 'client_or_protocol_failure',
                'selection_source':'read_only_owned_peer_oracle','oracle':{'visible':state['guild_ui'].get('motd')},'frame':frame}
            scout.receipt['cases'].append(row);scout.persist();require(row,'guild_motd_peer_pass')
            def leave(b,a,s):
                native=membership(scout.fixture['guid']);visible=a['guild_ui']['in_guild']
                return {'status':'guild_leave_pass' if s=='target' and not native and not visible else
                    ('controller_failure' if s!='target' else 'client_or_protocol_failure'),'oracle':{'membership':native,'in_guild':visible}}
            require(text_command(scout,'guild.leave','Leave the test guild.','/gquit',leave),'guild_leave_pass')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        for name,t in trials.items():
            with actor(name):
                try:
                    t.clean_panels()
                    if name=='scout' and membership(t.fixture['guid']):
                        if membership(t.fixture['guid'])[0]!=cohort.get('guild_fixture',{}).get('id'):raise RuntimeError('unrelated guild cleanup refused')
                        t.execute({'kind':'chat','value':'/gquit'})
                        if membership(t.fixture['guid']):raise RuntimeError('peer guild cleanup failed')
                    if name=='primary' and guild:t.execute({'kind':'chat','value':'/gmotd '+guild[2]})
                    if name in baselines:t.execute({'kind':'chat','value':'/console useClassicGuildUI '+str(int(baselines[name]))})
                    state,frame=t.observe('restored_fixture');t.receipt['restored_fixture']={'frame':frame,'guild':state['guild_ui']}
                    if name in baselines and state['guild_ui']['classic']!=baselines[name]:raise RuntimeError('guild preference restoration failed')
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
        for t in trials.values():
            t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output)
