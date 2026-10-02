"""Owned guild promotion, demotion, peer chat and removal through normal inputs."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .interaction_guild_membership import membership
from .interaction_chat import packets


def command(trial,case,goal,value,purpose,oracle):
    return trial.step(case,goal,{
        'command':{'kind':'chat','value':value,'description':'Type '+value+' to '+purpose+'.'},
        'friends':{'kind':'key','value':'o','description':'Open friends with O.'},
        'map':{'kind':'key','value':'m','description':'Open the world map with M.'}},oracle,diagnostic_action='command')


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};baselines={}
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);actors.session_entry(t.fixture);t.clean_panels()
                state,_=t.observe('fixture');baselines[name]=state['guild_ui']['classic']
        primary,scout=trials['primary'],trials['scout'];own=membership(primary.fixture['guid'])
        if not own or own[1]!=0:raise RuntimeError('requires an owned guild leader')
        with lab.connection() as con,con.cursor() as cur:
            cur.execute('SELECT name,leaderguid FROM client442_characters.guild WHERE guildid=%s',(own[0],));guild=cur.fetchone()
            cur.execute('SELECT guid FROM client442_characters.guild_member WHERE guildid=%s',(own[0],));members=cur.fetchall()
        if guild!=('Harness Ui Test',primary.fixture['guid']) or membership(scout.fixture['guid']) or {m[0] for m in members}!={primary.fixture['guid']}:
            raise RuntimeError('requires disposable owned guild leader and unguilded peer')
        cohort['guild_id']=own[0]
        # Invitation was qualified separately; this is explicit fixture input.
        with actor('primary'):primary.execute({'kind':'chat','value':'/ginvite Harnesstwo'})
        with actor('scout'):
            button=next(c for c in controls(scout) if c['name']=='StaticPopup1Button1' and c['enabled'])
            scout.execute({'kind':'click','value':point(button)})
            cohort['peer_initial_rank']=membership(scout.fixture['guid'])[1]
            scout.receipt['fixture_inputs']=[{'source':'code_fixture','purpose':'accept already-qualified guild invitation'}]
        for name in trials:
            with actor(name):
                t=trials[name];t.execute({'kind':'chat','value':'/console useClassicGuildUI 1'});t.execute({'kind':'key','value':'j'})
                t.receipt.setdefault('fixture_inputs',[]).append({'source':'code_fixture','purpose':'show Classic guild roster'});t.persist()
        with actor('primary'):
            require(click_case(primary,'guild.peer_details','Open Harnesstwo\'s guild member details.',
                lambda c:c['name'].startswith('GuildFrameButton') and c['text'].startswith('Harnesstwo'),
                lambda b,a,s:{'status':'guild_details_pass' if s and 'GuildMemberDetailFrame' in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure')}),'guild_details_pass')
        for label,delta in [('promote',-1),('demote',1)]:
            before_rank=membership(scout.fixture['guid'])[1];expected=before_rank+delta
            with actor('primary'):
                def outcome(b,a,s):
                    rank=membership(scout.fixture['guid'])[1]
                    visible=next((m['index'] for m in a['guild_ui'].get('members',[]) if m['name'].split('-',1)[0]=='Harnesstwo'),None)
                    blocked=a.get('blocked_actions') or []
                    return {'status':'guild_rank_pass' if s and rank==expected and visible==expected and not blocked else
                        ('controller_failure' if not s else 'client_or_protocol_failure'),
                        'oracle':{'before_rank':before_rank,'expected_rank':expected,'native_rank':rank,'visible_rank':visible,
                            'blocked_actions':blocked,'lua_errors':a.get('lua_errors')}}
                require(click_case(primary,'guild.rank_'+label,label.title()+' Harnesstwo by one guild rank.',
                    lambda c:c['name']=='GuildFrame'+label.title()+'Button',outcome),'guild_rank_pass')
            with actor('scout'):
                state,frame=scout.observe(label+'_received')
                row={'id':'guild.rank_'+label+'_peer','time':time.time(),'selection_source':'read_only_owned_peer_oracle',
                    'status':'guild_rank_peer_pass' if state['guild_ui'].get('rank_index')==expected else 'client_or_protocol_failure',
                    'oracle':{'expected_rank':expected,'visible_rank':state['guild_ui'].get('rank_index')},'frame':frame}
                scout.receipt['cases'].append(row);scout.persist();require(row,'guild_rank_peer_pass')
        with actor('primary'):
            token='TC442UI:guild_peer';since=time.time();session=actors.session_entry(primary.fixture)['session']
            require(command(primary,'guild.chat_peer_send','Send the test message to guild chat.','/g '+token,'send a guild message',
                lambda b,a,s:{'status':'guild_chat_pass' if s=='command' and any(x['name']=='SMSG_MESSAGECHAT' and x['direction']=='from_native'
                    for x in packets(session,since,token)) and any(x['text']==token and x['event']=='CHAT_MSG_GUILD' for x in a['chat_probes'])
                    else ('controller_failure' if s!='command' else 'client_or_protocol_failure')}),'guild_chat_pass')
        with actor('scout'):
            state,frame=scout.observe('guild_chat_received');session=actors.session_entry(scout.fixture)['session']
            visible=any(x['text']==token and x['event']=='CHAT_MSG_GUILD' for x in state['chat_probes'])
            delivered=any(x['name']=='SMSG_MESSAGECHAT' and x['direction']=='from_native' for x in packets(session,since,token))
            row={'id':'guild.chat_peer_receive','time':time.time(),'selection_source':'read_only_owned_peer_oracle',
                'status':'guild_chat_peer_pass' if visible and delivered else 'client_or_protocol_failure',
                'oracle':{'visible':visible,'native':delivered},'frame':frame}
            scout.receipt['cases'].append(row);scout.persist();require(row,'guild_chat_peer_pass')
        with actor('primary'):
            require(click_case(primary,'guild.remove_member_open','Remove Harnesstwo from the test guild.',lambda c:c['name']=='GuildMemberRemoveButton',
                lambda b,a,s:{'status':'panel_open_pass' if s and 'StaticPopup1' in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
            require(click_case(primary,'guild.remove_member','Confirm removing Harnesstwo from the test guild.',
                lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Accept','Okay','Remove'],
                lambda b,a,s:{'status':'guild_remove_pass' if s and not membership(scout.fixture['guid']) and
                    all(m['name'].split('-',1)[0]!='Harnesstwo' for m in a['guild_ui'].get('members',[])) else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),
                    'oracle':{'native_membership':membership(scout.fixture['guid']),'visible_members':a['guild_ui'].get('members')}}),'guild_remove_pass')
        with actor('scout'):
            state,frame=scout.observe('removed');row={'id':'guild.remove_member_peer','time':time.time(),
                'selection_source':'read_only_owned_peer_oracle','status':'guild_remove_peer_pass' if not state['guild_ui']['in_guild'] else 'client_or_protocol_failure',
                'oracle':{'in_guild':state['guild_ui']['in_guild']},'frame':frame}
            scout.receipt['cases'].append(row);scout.persist();require(row,'guild_remove_peer_pass')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        for name,t in trials.items():
            with actor(name):
                try:
                    t.clean_panels()
                    if name=='scout' and membership(t.fixture['guid']):
                        if membership(t.fixture['guid'])[0]!=cohort.get('guild_id'):raise RuntimeError('unrelated guild cleanup refused')
                        t.execute({'kind':'chat','value':'/gquit'})
                        if membership(t.fixture['guid']):raise RuntimeError('peer membership cleanup failed')
                    if name in baselines:t.execute({'kind':'chat','value':'/console useClassicGuildUI '+str(int(baselines[name]))})
                    state,frame=t.observe('restored');t.receipt['restoration']={'frame':frame,'guild':state['guild_ui']}
                    cohort.setdefault('client_diagnostics',{})[name]={
                        'blocked_actions':state.get('blocked_actions'),'lua_errors':state.get('lua_errors')}
                    if state['guild_ui']['classic']!=baselines[name]:raise RuntimeError('guild preference restoration failed')
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
        cohort['ui_clean']=all(not d['blocked_actions'] and not d['lua_errors'] for d in cohort.get('client_diagnostics',{}).values())
        for t in trials.values():t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
