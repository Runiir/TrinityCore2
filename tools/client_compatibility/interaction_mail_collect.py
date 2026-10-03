"""Collect one disposable native mail resource, delete its letter and restore the fixture."""
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
from .interaction_mail_actions import letter,open_mailbox
from .mailbox_fixture import MailboxFixture
from .observation.inventory import Inventory
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import item_fixture_permission,money_fixture_permission


def suite(t,point,resource):
    actors.session_entry(t.fixture);t.clean_panels();fixture=MailboxFixture(t.out,t.fixture)
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    baseline=mailbox_state();money=oracle.money();t.receipt['mailbox_baseline']=baseline;t.persist()
    subject='442 UI resource '+resource+' '+uuid.uuid4().hex[:8]
    body='Disposable mail collection trial. Take the resource, then delete this letter.'
    amount=5 if resource=='item' else 12345;before=None
    if oracle.count(159):raise RuntimeError('mail collection requires no pre-existing owned water')
    try:
        with lab.connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client442_characters.mail WHERE receiver=1 AND subject LIKE '442 UI resource %%'")
            if cursor.fetchone():raise RuntimeError('an earlier resource letter needs cleanup')
        fixture.prepare();state,frame=t.observe('mailbox_staged')
        t.receipt['staging']={'frame':frame,'world_position':state['world_position']};t.persist()
        command='items' if resource=='item' else 'money';argument='159:5' if resource=='item' else str(amount)
        lab.server_command(f'send {command} Harnessone "{subject}" "{body}" {argument}');time.sleep(2)
        before=letter(subject)
        if (not before or before[1:6]!=(0,0,1,subject,body) or before[7] or before[8]&1 or
                before[9]!=(resource=='item') or before[6]!=(amount if resource=='money' else 0) or before[10]):
            raise RuntimeError('disposable native resource mail differs from fixture')
        t.receipt['disposable_letter']={'source':'code_fixture_native_console','before':before,
                                      'resource':resource,'amount':amount};t.persist()
        open_mailbox(t,point);state,frame=t.observe('inbox_with_resource')
        row=next((r for r in state.get('mail',{}).get('inbox',[]) if r['subject']==subject),None)
        if not row:raise RuntimeError('resource letter is outside the observed inbox')
        require(click_case(t,'mail.read_resource','Read the disposable resource letter '+subject+'.',
            lambda c:c['name']=='MailItem'+str(row['index'])+'Button',
            lambda b,a,s:{'status':'mail_read_pass' if s and a.get('mail',{}).get('open',{}).get('subject')==subject
                        and letter(subject)[8]&1 else ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_read_pass')
        state,frame=t.observe('resource_letter_open');opened=state['mail']['open']
        if resource=='item' and opened.get('attachments')!=[{'index':1,'name':'Refreshing Spring Water','id':159,'count':5}]:
            raise RuntimeError('visible attachment identity/count differs from native fixture')
        if resource=='money' and opened.get('money')!=amount:raise RuntimeError('visible attached money differs')
        t.receipt['resource_open']={'state':opened,'frame':frame};t.persist()
        def collect_oracle(b,a,correct):
            oracle.poll();native=letter(subject);opened=a.get('mail',{}).get('open',{})
            visible_count=sum(r['count'] for r in a.get('bag_items',[]) if r['id']==159)
            if resource=='item':
                passed=(oracle.count(159)==amount and visible_count==amount and oracle.money()==money
                        and native and not native[9] and not opened.get('attachments'))
            else:
                passed=(oracle.money()==money+amount and a.get('money')==money+amount and native
                        and native[6]==0 and not opened.get('money'))
            return {'status':'mail_collect_pass' if correct and passed else
                    ('controller_failure' if not correct else 'client_or_protocol_failure'),
                    'oracle':{'resource':resource,'native_mail':native,'visible_open':opened,
                              'native_count':oracle.count(159),'visible_count':visible_count,
                              'native_money':oracle.money(),'visible_money':a.get('money')}}
        control='OpenMailAttachmentButton1' if resource=='item' else 'OpenMailMoneyButton'
        require(click_case(t,'mail.collect_'+resource,'Take the '+('five Refreshing Spring Water items' if resource=='item' else 'attached money')+'.',
            lambda c:c['name']==control,collect_oracle),'mail_collect_pass')
        require(click_case(t,'mail.delete_empty_resource','Delete the now-empty disposable resource letter.',
            lambda c:c['name']=='OpenMailDeleteButton' and c['text']=='Delete',
            lambda b,a,s:{'status':'mail_delete_pass' if s and letter(subject) is None else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_delete_pass')
        require(t.step('mail.close','Close the mailbox.',{
            'close':{'kind':'key','value':'Escape','description':'Close the mailbox with Escape.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your equipment.'}},
            lambda b,a,s:{'status':'mailbox_close_pass' if s=='close' and 'MailFrame' not in a['panels'] else
                        ('controller_failure' if s!='close' else 'client_or_protocol_failure')},
            diagnostic_action='close'),'mailbox_close_pass')
    finally:
        try:
            t.clean_panels();oracle.poll();count=oracle.count(159);delta=oracle.money()-money
            if count not in [0,amount if resource=='item' else 0] or delta not in [0,amount if resource=='money' else 0]:
                raise RuntimeError('unexpected collection resources; preserve fixture for diagnosis')
            if count or delta:
                fixture_command(t,'/cleartarget','restore resources only on the owned collection actor')
                if count:
                    with item_fixture_permission(t):fixture_command(t,f'.additem 159 {-count}','remove only the collected disposable water')
                if delta:
                    with money_fixture_permission(t):fixture_command(t,f'.modify money {-delta}','remove only the collected disposable money')
        finally:fixture.restore()
        after=mailbox_state();state,frame=t.observe('mail_collection_restored')
        t.receipt['mailbox_restoration']={'mail_inventory_money_unchanged':after==baseline,
                                        'disposable_remaining':letter(subject),'after':after,'frame':frame};t.persist()
        if after!=baseline:raise RuntimeError('collection trial needs fixture cleanup; original mail/inventory/money must remain')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--point',type=int,nargs=2,required=True);parser.add_argument('--resource',choices=['item','money'],required=True)
    args=parser.parse_args()
    if any(not 0<=v<bound for v,bound in zip(args.point,[1280,720])):parser.error('mailbox point is outside the owned window')
    t=Trial(args.output,controller='code')
    try:suite(t,args.point,args.resource);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
