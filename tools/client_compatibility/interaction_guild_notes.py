"""Ordinary guild note, information, chat and control UI with native oracles."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls,point
from .interaction_macros import edit_case,require
from .interaction_chat import packets


def native(trial):
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT g.guildid,g.name,g.leaderguid,g.info,m.pnote,m.offnote FROM client442_characters.guild g '
                    'JOIN client442_characters.guild_member m ON m.guildid=g.guildid WHERE m.guid=%s',(trial.fixture['guid'],))
        return cur.fetchone()


def select_member(trial):
    state,_=trial.observe('member_selection')
    if 'GuildMemberDetailFrame' not in state['panels']:
        require(click_case(trial,'guild.member_details','Open Harnessone\'s guild member details.',
            lambda c:c['name']=='GuildFrameButton1' and c['text'].startswith('Harnessone'),
            lambda b,a,s:{'status':'guild_details_pass' if s and 'GuildMemberDetailFrame' in a['panels'] else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'guild_details_pass')


def note(trial,key,value):
    select_member(trial);officer=key=='officer';name='GuildMemberOfficerNoteBackground' if officer else 'GuildMemberNoteBackground'
    require(click_case(trial,'guild.'+key+'_note_open','Edit Harnessone\'s '+key+' guild note.',lambda c:c['name']==name,
        lambda b,a,s:{'status':'panel_open_pass' if s and 'StaticPopup1' in a['panels'] else
            ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
    require(edit_case(trial,'guild.'+key+'_note_text','Set the '+key+' guild note to '+repr(value)+'.',
        lambda c:c['name']=='StaticPopup1EditBox',value),'ui_edit_pass')
    def outcome(b,a,s):
        row=native(trial);db=row[5 if officer else 4];other=row[4 if officer else 5]
        observed=next((m.get(key if officer else 'note') for m in a['guild_ui'].get('members',[]) if m['name'].split('-',1)[0]=='Harnessone'),None)
        baseline=trial.receipt['guild_baseline'];expected_other=baseline[4 if officer else 5]
        return {'status':'guild_note_pass' if s and db==value and observed==value and other==expected_other else
            ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'native_note':db,'visible_note':observed,'other_note_preserved':other==expected_other}}
    require(click_case(trial,'guild.'+key+'_note_save','Save the '+key+' guild note.',
        lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Accept','Okay'],outcome),'guild_note_pass')
    # Restore before the other note trial so each mutation has an independent baseline.
    restore_note(trial,key,trial.receipt['guild_baseline'][5 if officer else 4])


def restore_note(trial,key,value):
    row=native(trial);column=5 if key=='officer' else 4
    if row[column]==value:return
    name='GuildMemberOfficerNoteBackground' if key=='officer' else 'GuildMemberNoteBackground'
    trial.execute({'kind':'click','value':point(next(c for c in controls(trial) if c['name']==name))})
    field=next(c for c in controls(trial) if c['name']=='StaticPopup1EditBox')
    trial.execute({'kind':'edit','point':point(field),'value':value})
    trial.execute({'kind':'click','value':point(next(c for c in controls(trial) if c['name']=='StaticPopup1Button1'))})
    if native(trial)[column]!=value:raise RuntimeError('native '+key+' note restoration failed')
    trial.receipt['cleanup'].append({'source':'code_fixture_cleanup','time':time.time(),'note':key,'restored':True});trial.persist()


def suite(trial):
    trial.clean_panels();state,_=trial.observe('guild_fixture');baseline=native(trial)
    if not baseline or baseline[1:3]!=('Harness Ui Test',trial.fixture['guid']):raise RuntimeError('requires owned disposable guild leader')
    trial.receipt['guild_baseline']=baseline;trial.receipt['classic_baseline']=state['guild_ui']['classic'];trial.persist()
    trial.execute({'kind':'chat','value':'/console useClassicGuildUI 1'})
    require(trial.step('guild.open','Open the guild roster.',{
        'guild':{'kind':'key','value':'j','description':'Press J to open the guild roster.'},
        'friends':{'kind':'key','value':'o','description':'Open friends with O.'},
        'map':{'kind':'key','value':'m','description':'Open the map with M.'}},
        lambda b,a,s:{'status':'guild_roster_pass' if s=='guild' and 'GuildFrame' in a['panels'] and not a['lua_errors'] else
            ('controller_failure' if s!='guild' else 'client_or_protocol_failure')},diagnostic_action='guild'),'guild_roster_pass')
    for key in ['public','officer']:note(trial,key,'TC442UI:'+key)
    trial.clean_panels();trial.execute({'kind':'key','value':'j'})
    require(click_case(trial,'guild.information','Open guild information.',lambda c:c['name']=='GuildFrameGuildInformationButton',
        lambda b,a,s:{'status':'panel_open_pass' if s and 'GuildInfoFrame' in a['panels'] else
            ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
    require(edit_case(trial,'guild.information_text','Set guild information to TC442UI:info.',
        lambda c:c['name']=='GuildInfoEditBox','TC442UI:info'),'ui_edit_pass')
    require(click_case(trial,'guild.information_save','Save guild information.',lambda c:c['name']=='GuildInfoSaveButton',
        lambda b,a,s:{'status':'guild_info_native_pass' if s and native(trial)[3]=='TC442UI:info' else
            ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'native_info':native(trial)[3],'qualified_scope':'saved information; refreshed visible value checked next'}}),'guild_info_native_pass')
    trial.clean_panels();trial.execute({'kind':'key','value':'j'});state,frame=trial.observe('information_refreshed')
    row={'id':'guild.information_refresh','time':time.time(),'selection_source':'read_only_native_oracle',
         'status':'guild_info_visible_pass' if state['guild_ui']['info']=='TC442UI:info' else 'client_or_protocol_failure',
         'oracle':{'native_info':native(trial)[3],'visible_info':state['guild_ui']['info']},'frame':frame}
    trial.receipt['cases'].append(row);trial.persist();require(row,'guild_info_visible_pass')
    require(click_case(trial,'guild.control','Open guild control.',lambda c:c['name']=='GuildFrameControlButton',
        lambda b,a,s:{'status':'guild_control_open_pass' if s and 'GuildControlPopupFrame' in a['panels'] and not a['lua_errors'] else
            ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'lua_errors':a['lua_errors']}}),'guild_control_open_pass')
    trial.clean_panels();session=actors.session_entry(trial.fixture)['session']
    for kind,command in [('GUILD','/g'),('OFFICER','/o')]:
        token='TC442UI:'+kind.lower();since=time.time()
        def outcome(b,a,s):
            rows=packets(session,since,token);visible=any(m['text']==token and m['event']=='CHAT_MSG_'+kind for m in a['chat_probes'])
            delivered=any(r['name']=='SMSG_MESSAGECHAT' and r['direction']=='from_native' for r in rows)
            return {'status':'guild_chat_pass' if s=='chat' and visible and delivered else
                ('controller_failure' if s!='chat' else 'client_or_protocol_failure'),'oracle':{'visible':visible,'native':delivered,'packets':rows}}
        require(trial.step('guild.chat.'+kind.lower(),'Send the test message to '+kind.lower()+' chat.',{
            'chat':{'kind':'chat','value':command+' '+token,'description':'Type '+command+' '+token+' to send a '+kind.lower()+' chat message.'},
            'friends':{'kind':'key','value':'o','description':'Open friends with O.'},
            'map':{'kind':'key','value':'m','description':'Open the map with M.'}},outcome,diagnostic_action='chat'),'guild_chat_pass')


def cleanup(trial):
    baseline=trial.receipt.get('guild_baseline')
    if not baseline:return
    trial.clean_panels();trial.execute({'kind':'chat','value':'/console useClassicGuildUI 1'});trial.execute({'kind':'key','value':'j'})
    if native(trial)[4:6]!=tuple(baseline[4:6]):
        rows=controls(trial);trial.execute({'kind':'click','value':point(next(c for c in rows if c['name']=='GuildFrameButton1'))})
        restore_note(trial,'public',baseline[4]);restore_note(trial,'officer',baseline[5])
    if native(trial)[3]!=baseline[3]:
        rows=controls(trial);trial.execute({'kind':'click','value':point(next(c for c in rows if c['name']=='GuildFrameGuildInformationButton'))})
        field=next(c for c in controls(trial) if c['name']=='GuildInfoEditBox')
        trial.execute({'kind':'edit','point':point(field),'value':baseline[3]})
        trial.execute({'kind':'click','value':point(next(c for c in controls(trial) if c['name']=='GuildInfoSaveButton'))})
    trial.clean_panels();trial.execute({'kind':'chat','value':'/console useClassicGuildUI '+str(int(trial.receipt['classic_baseline']))})
    state,frame=trial.observe('restored');matches=native(trial)==tuple(baseline) and state['guild_ui']['classic']==trial.receipt['classic_baseline']
    trial.receipt['restoration']={'matches':matches,'guild':state['guild_ui'],'frame':frame};trial.persist()
    if not matches:raise RuntimeError('guild baseline restoration failed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    t=Trial(p.parse_args().output)
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        try:cleanup(t)
        except Exception as e:t.receipt['completed']=False;t.receipt['cleanup_failure']=str(e)
        t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure'],'cleanup_failure':t.receipt.get('cleanup_failure')}),flush=True)
