"""Read and delete one disposable native letter through stock UI, retaining reward mail."""
import argparse
import json
from pathlib import Path
import time
import uuid
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_macros import require
from .interaction_operations import click_case
from .interaction_mail import mailbox_state
from .mailbox_fixture import MailboxFixture


def letter(subject):
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT id,messageType,sender,receiver,subject,body,money,cod,checked,has_items,mailTemplateId '
                       'FROM client442_characters.mail WHERE receiver=1 AND subject=%s',(subject,))
        rows=cursor.fetchall()
        if len(rows)>1:raise RuntimeError('disposable mail subject is not unique')
        return rows[0] if rows else None


def open_mailbox(t,point):
    require(t.step('mail.open','Open the nearby mailbox.',{
        'mailbox':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby mailbox.'},
        'map':{'kind':'key','value':'m','description':'Open the world map.'},
        'character':{'kind':'key','value':'c','description':'Open your equipment.'}},
        lambda b,a,s:{'status':'mailbox_open_pass' if s=='mailbox' and 'MailFrame' in a['panels'] else
                    ('controller_failure' if s!='mailbox' else 'client_or_protocol_failure')},
        diagnostic_action='mailbox'),'mailbox_open_pass')


def suite(t,point):
    actors.session_entry(t.fixture);t.clean_panels();fixture=MailboxFixture(t.out,t.fixture)
    baseline=mailbox_state();t.receipt['mailbox_baseline']=baseline;t.persist()
    subject='442 UI letter '+uuid.uuid4().hex[:8]
    body='Disposable compatibility letter. Read it, then delete it.'
    try:
        with lab.connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client442_characters.mail WHERE receiver=1 AND subject LIKE '442 UI letter %%'")
            if cursor.fetchone():raise RuntimeError('an earlier disposable letter needs cleanup')
        fixture.prepare();state,frame=t.observe('mailbox_staged')
        t.receipt['staging']={'frame':frame,'world_position':state['world_position']};t.persist()
        lab.server_command(f'send mail Harnessone "{subject}" "{body}"');time.sleep(2)
        before=letter(subject)
        if not before or before[1:8]!=(0,0,1,subject,body,0,0) or before[8]&1 or before[9:]!=(0,0):
            raise RuntimeError('native disposable letter is not the empty unread console fixture')
        t.receipt['disposable_letter']={'source':'code_fixture_native_console','before':before,
                                      'subject':subject,'body':body};t.persist()
        open_mailbox(t,point);state,frame=t.observe('inbox_with_fixture')
        row=next((r for r in state.get('mail',{}).get('inbox',[]) if r['subject']==subject),None)
        if not row or row['read'] or row.get('items') or row['money'] or row['cod']:
            raise RuntimeError('disposable unread letter is not visible in the observed inbox')
        def read_oracle(b,a,correct):
            native=letter(subject);opened=a.get('mail',{}).get('open',{})
            unchanged=native and native[:8]==before[:8] and native[9:]==before[9:]
            passed=correct and opened.get('subject')==subject and unchanged and native[8]==(before[8]|1)
            return {'status':'mail_read_pass' if passed else ('controller_failure' if not correct else 'client_or_protocol_failure'),
                    'oracle':{'open':opened,'native':native,'body_expected_for_visual_review':body,
                              'qualified_scope':'selected letter, native read flag and human-reviewed body screenshot'}}
        require(click_case(t,'mail.read','Read the disposable letter '+subject+'.',
            lambda c:c['name']=='MailItem'+str(row['index'])+'Button',read_oracle),'mail_read_pass')
        state,frame=t.observe('disposable_letter_open');t.receipt['open_letter']={'state':state,'frame':frame};t.persist()
        def delete_oracle(b,a,correct):
            after=mailbox_state();gone=letter(subject) is None
            passed=correct and gone and after==baseline and 'OpenMailFrame' not in a['panels']
            return {'status':'mail_delete_pass' if passed else ('controller_failure' if not correct else 'client_or_protocol_failure'),
                    'oracle':{'fixture_absent':gone,'reward_mail_inventory_money_unchanged':after==baseline,
                              'panels':a['panels']}}
        require(click_case(t,'mail.delete','Delete the disposable letter that is open.',
            lambda c:c['name']=='OpenMailDeleteButton' and c['text']=='Delete',delete_oracle),'mail_delete_pass')
        require(t.step('mail.close','Close the mailbox.',{
            'close':{'kind':'key','value':'Escape','description':'Close the mailbox with Escape.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your equipment.'}},
            lambda b,a,s:{'status':'mailbox_close_pass' if s=='close' and 'MailFrame' not in a['panels'] else
                        ('controller_failure' if s!='close' else 'client_or_protocol_failure')},
            diagnostic_action='close'),'mailbox_close_pass')
    finally:
        try:t.clean_panels()
        finally:fixture.restore()
        after=mailbox_state();state,frame=t.observe('mail_actions_restored')
        t.receipt['mailbox_restoration']={'mail_inventory_money_unchanged':after==baseline,
                                        'disposable_remaining':letter(subject),'after':after,'frame':frame};t.persist()
        if after!=baseline:raise RuntimeError('mail action trial needs disposable-letter cleanup; reward baseline must be retained')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--point',type=int,nargs=2,required=True);args=parser.parse_args()
    if any(not 0<=v<bound for v,bound in zip(args.point,[1280,720])):parser.error('mailbox point is outside the owned window')
    t=Trial(args.output)
    try:suite(t,args.point);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
