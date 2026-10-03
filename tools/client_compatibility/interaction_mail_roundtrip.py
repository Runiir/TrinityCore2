"""Owned player mail composition, delivery, reply/return and reversible cleanup."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import time
import uuid
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import click_case,controls,point
from .interaction_macros import require,edit_case
from .interaction_mail import mailbox_state
from .interaction_mail_actions import letter,open_mailbox
from .interaction_trade import inventory
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import money_fixture_permission
from .mailbox_fixture import MailboxFixture


@contextmanager
def at_mailbox(t,point):
    t.clean_panels();fixture=MailboxFixture(t.out,t.fixture)
    try:
        fixture.prepare();s,f=t.observe('mailbox_staged_'+str(len(t.receipt['cases'])))
        t.receipt.setdefault('mailbox_visits',[]).append({'frame':f,'world_position':s['world_position'],'point':point});t.persist()
        open_mailbox(t,point);yield
    finally:
        try:t.clean_panels()
        finally:fixture.restore()


def read_letter(t,subject):
    state,_=t.observe('inbox_'+str(len(t.receipt['cases'])))
    row=next((r for r in state.get('mail',{}).get('inbox',[]) if r['subject']==subject),None)
    native=letter(subject,t.fixture['guid'])
    if not row or not native or native[2] not in [1,2]:raise RuntimeError('owned letter is absent from the observed inbox')
    expected_sender={1:'Harnessone',2:'Harnesstwo'}[native[2]]
    if row['sender']!=expected_sender:raise RuntimeError('visible player sender disagrees with native mail')
    def outcome(b,a,correct):
        current=letter(subject,t.fixture['guid']);opened=a.get('mail',{}).get('open',{})
        matches=current and current[:8]==native[:8] and current[9:]==native[9:] and current[8]==(native[8]|1)
        return {'status':'mail_read_pass' if correct and matches and opened.get('subject')==subject else
                ('controller_failure' if not correct else 'client_or_protocol_failure'),
                'oracle':{'native':current,'visible_open':opened,'expected_body_for_visual_review':native[5]}}
    require(click_case(t,'mail.read_owned','Read the letter '+subject+'.',
        lambda c:c['name']=='MailItem'+str(row['index'])+'Button',outcome),'mail_read_pass')


def compose(t,recipient,subject,body,amount=0,reply=False):
    if not reply:
        require(click_case(t,'mail.compose','Open the Send Mail tab.',lambda c:c['name']=='MailFrameTab2',
            lambda b,a,s:{'status':'mail_compose_open_pass' if s and a.get('mail',{}).get('compose') is not None else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_compose_open_pass')
    # The stock tab opens every bag. Hide those unrelated panels through their
    # observed ordinary close buttons to keep subsequent observer pages small.
    for _ in range(6):
        rows=controls(t)
        c=next((c for c in rows if c['enabled'] and c['name'].startswith('ContainerFrame') and c['name'].endswith('CloseButton')),None)
        if c is None:break
        t.receipt['cleanup'].append({'source':'code_fixture_panel_cleanup','control':c,'input':'click'})
        t.execute({'kind':'click','value':point(c)});t.persist()
    else:raise RuntimeError('compose bag cleanup did not settle')
    if not reply:
        require(edit_case(t,'mail.recipient','Address this letter to '+recipient+'.',
            lambda c:c['name']=='SendMailNameEditBox',recipient),'ui_edit_pass')
        require(edit_case(t,'mail.subject','Set the letter subject to '+subject+'.',
            lambda c:c['name']=='SendMailSubjectEditBox',subject),'ui_edit_pass')
    fields=[c for c in controls(t) if c['kind']=='EditBox' and not c['name']]
    if len(fields)!=1:raise RuntimeError('stock compose body is not one unambiguous anonymous EditBox')
    require(edit_case(t,'mail.body','Write the letter body: '+body,
        lambda c:not c['name'],body),'ui_edit_pass')
    if amount:
        require(edit_case(t,'mail.attach_money','Attach one copper to this return trial.',
            lambda c:c['name']=='SendMailMoneyCopper',str(amount)),'ui_edit_pass')
    s,f=t.observe('letter_composed_'+str(len(t.receipt['cases'])))
    expected={'recipient':recipient,'subject':subject,'body':body}
    if s.get('mail',{}).get('compose')!=expected:raise RuntimeError('visible compose fields differ before sending')
    t.receipt.setdefault('composed_letters',[]).append({'expected':expected,'money':amount,'frame':f});t.persist()


def send(t,recipient_guid,subject,body,amount=0):
    before=inventory();sender=t.fixture['guid'];money=dict(before['money'])[sender]
    if letter(subject,recipient_guid):raise RuntimeError('owned letter already exists before sending')
    def outcome(b,a,correct):
        native=letter(subject,recipient_guid);after=inventory()
        expected=(0,sender,recipient_guid,subject,body,amount,0)
        delivered=native and native[1:8]==expected and not native[9] and not native[10]
        charged=dict(after['money'])[sender]==money-30-amount and a.get('money')==money-30-amount
        return {'status':'mail_send_pass' if correct and delivered and charged and after['items']==before['items'] else
                ('controller_failure' if not correct else 'client_or_protocol_failure'),
                'oracle':{'native':native,'postage':30,'attached_money':amount,'money_before':money,
                          'native_money':dict(after['money'])[sender],'visible_money':a.get('money'),
                          'inventory_unchanged':after['items']==before['items']}}
    require(click_case(t,'mail.send','Send this letter to the owned test character.',
        lambda c:c['name']=='SendMailMailButton',outcome),'mail_send_pass')


def take_money(t,subject):
    native=letter(subject,t.fixture['guid']);before=dict(inventory()['money'])[t.fixture['guid']]
    if not native or native[6]!=1 or native[7] or native[9]:raise RuntimeError('return collection requires exactly one disposable copper')
    def outcome(b,a,correct):
        current=letter(subject,t.fixture['guid']);money=dict(inventory()['money'])[t.fixture['guid']]
        passed=current and current[6]==0 and money==before+1 and a.get('money')==money
        return {'status':'mail_collect_pass' if correct and passed else
                ('controller_failure' if not correct else 'client_or_protocol_failure'),
                'oracle':{'native_mail':current,'native_money':money,'visible_money':a.get('money')}}
    require(click_case(t,'mail.take_returned_money','Take the returned one copper.',
        lambda c:c['name']=='OpenMailMoneyButton',outcome),'mail_collect_pass')


def delete_letter(t,subject):
    require(click_case(t,'mail.delete_owned','Delete the empty owned test letter.',
        lambda c:c['name']=='OpenMailDeleteButton' and c['text']=='Delete',
        lambda b,a,s:{'status':'mail_delete_pass' if s and letter(subject,t.fixture['guid']) is None else
                    ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_delete_pass')


def money_adjust(t,amount,reason):
    fixture_command(t,'/cleartarget','apply the disposable mail money adjustment to the owned actor')
    before=dict(inventory()['money'])[t.fixture['guid']]
    with money_fixture_permission(t):fixture_command(t,'.modify money '+str(amount),reason)
    lab.server_command('saveall');time.sleep(1)
    state,frame=t.observe('money_fixture_'+str(len(t.receipt.get('fixture_inputs',[]))))
    after=dict(inventory()['money'])[t.fixture['guid']]
    if after!=before+amount or state.get('money')!=after:raise RuntimeError('mail fixture money adjustment did not match native/client state')
    t.receipt.setdefault('money_adjustments',[]).append({'before':before,'amount':amount,'after':after,'frame':frame});t.persist()


def cleanup_letters(out,trials,subjects,points):
    for name,t in trials.items():
        with actor(name):
            remaining=[s for s in subjects if letter(s,t.fixture['guid'])]
            if not remaining:continue
            cleanup=Trial(out/'cleanup'/name,controller='code')
            try:
                with at_mailbox(cleanup,points[name]):
                    for subject in remaining:
                        native=letter(subject,t.fixture['guid'])
                        if native[2] not in [1,2] or native[6] not in [0,1] or native[7] or native[9]:
                            raise RuntimeError('cleanup letter differs from the empty/one-copper owned fixture')
                        read_letter(cleanup,subject)
                        if native[6]:take_money(cleanup,subject)
                        delete_letter(cleanup,subject)
                cleanup.receipt['completed']=True
            except Exception as error:cleanup.receipt['failure']=str(error);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()


def suite(out,mode,points):
    out.mkdir(exist_ok=False,parents=True,mode=0o700);trials={};baseline={}
    cohort={'schema':'client442_owned_mail_roundtrip_v1','started_at':time.time(),'mode':mode,'completed':False,'failure':None}
    subject='442 UI '+mode+' '+uuid.uuid4().hex[:8];reply_subject='RE: '+subject
    body='Owned compatibility letter. '+mode.capitalize()+' trial.';reply_body='Owned reply received. Mail controls verified.'
    cohort.update(subject=subject,reply_subject=reply_subject,body=body,reply_body=reply_body)
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);actors.session_entry(t.fixture);t.clean_panels()
                baseline[name]=mailbox_state(t.fixture['guid']);t.receipt['mailbox_baseline']=baseline[name];t.persist()
        with lab.connection() as c,c.cursor() as q:
            q.execute("SELECT id FROM client442_characters.mail WHERE receiver IN (1,2) AND subject LIKE '%%442 UI %%'")
            if q.fetchone():raise RuntimeError('an earlier disposable letter needs cleanup')
        if baseline['primary']['inventory']!=baseline['scout']['inventory']:raise RuntimeError('cohort inventory baseline changed between observations')
        if mode=='reply':
            with actor('scout'):money_adjust(trials['scout'],30,'fund exactly one owned reply postage')
        with actor('primary'):
            t=trials['primary']
            with at_mailbox(t,points['primary']):
                compose(t,'Harnesstwo-Client442Lab',subject,body,amount=1 if mode=='return' else 0)
                send(t,2,subject,body,amount=1 if mode=='return' else 0)
        with actor('scout'):
            t=trials['scout']
            with at_mailbox(t,points['scout']):
                read_letter(t,subject)
                if mode=='return':
                    def returned(b,a,correct):
                        native=letter(subject,1);gone=letter(subject,2) is None
                        matches=native and native[1:8]==(0,2,1,subject,body,1,0) and not native[9]
                        return {'status':'mail_return_pass' if correct and gone and matches else
                                ('controller_failure' if not correct else 'client_or_protocol_failure'),
                                'oracle':{'original_absent':gone,'returned_native':native}}
                    require(click_case(t,'mail.return','Return the one-copper letter to its sender.',
                        lambda c:c['name']=='OpenMailDeleteButton' and c['text']=='Return',returned),'mail_return_pass')
                else:
                    require(click_case(t,'mail.reply','Reply to this owned letter.',lambda c:c['name']=='OpenMailReplyButton',
                        lambda b,a,s:{'status':'mail_reply_open_pass' if s and a.get('mail',{}).get('compose',{}).get('recipient')=='Harnessone'
                                    and a['mail']['compose'].get('subject')==reply_subject else
                                    ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_reply_open_pass')
                    compose(t,'Harnessone',reply_subject,reply_body,reply=True);send(t,1,reply_subject,reply_body)
                    t.clean_panels();open_mailbox(t,points['scout']);read_letter(t,subject);delete_letter(t,subject)
        with actor('primary'):
            t=trials['primary'];received=subject if mode=='return' else reply_subject
            with at_mailbox(t,points['primary']):
                read_letter(t,received)
                if mode=='return':take_money(t,received)
                delete_letter(t,received)
        cohort['completed']=True
    except Exception as error:cohort['failure']=f'{type(error).__name__}: {error}'
    finally:
        try:
            cleanup_letters(out,trials,[subject,reply_subject],points)
            for name,t in trials.items():
                with actor(name):
                    t.clean_panels()
                    if name not in baseline:continue
                    expected=dict(baseline[name]['inventory']['money'])[t.fixture['guid']]
                    lab.server_command('saveall');time.sleep(1)
                    delta=dict(inventory()['money'])[t.fixture['guid']]-expected
                    if delta not in ([0,-30,-31] if name=='primary' else [0,30,1]):
                        raise RuntimeError('unexpected owned mail money delta; preserve evidence for diagnosis')
                    if delta:money_adjust(t,-delta,'restore only owned mail postage/disposable copper')
            for name,t in trials.items():
                with actor(name):
                    after=mailbox_state(t.fixture['guid']);state,frame=t.observe('mail_roundtrip_restored')
                    matches=after==baseline.get(name)
                    t.receipt['mailbox_restoration']={'matches':matches,'after':after,'frame':frame};t.persist()
                    if not matches:raise RuntimeError(name+' original mail/inventory/money differs after cleanup')
            cohort['restored']=True
        except Exception as error:cohort.update(completed=False,cleanup_failure=f'{type(error).__name__}: {error}')
        for t in trials.values():t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['return','reply'],required=True)
    p.add_argument('--primary-point',type=int,nargs=2,required=True);p.add_argument('--scout-point',type=int,nargs=2,required=True);a=p.parse_args()
    points={'primary':a.primary_point,'scout':a.scout_point}
    if any(not 0<=v<bound for point in points.values() for v,bound in zip(point,[1280,720])):p.error('mailbox point is outside the owned window')
    suite(a.output,a.mode,points)
