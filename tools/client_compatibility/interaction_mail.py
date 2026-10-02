"""Open an existing mailbox with ordinary inputs while preserving its reward mail."""
import argparse
import json
from pathlib import Path
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_macros import require
from .interaction_operations import controls
from .mailbox_fixture import MailboxFixture
from .interaction_trade import inventory


def mailbox_state():
    lab.server_command('saveall'); time.sleep(1)
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT id,messageType,sender,receiver,subject,money,cod,checked,has_items,mailTemplateId '
                       'FROM client442_characters.mail WHERE receiver=1 ORDER BY id')
        mails = cursor.fetchall()
        cursor.execute('SELECT mi.mail_id,mi.item_guid,ii.itemEntry,ii.count FROM client442_characters.mail_items mi '
                       'JOIN client442_characters.item_instance ii ON ii.guid=mi.item_guid '
                       'JOIN client442_characters.mail m ON m.id=mi.mail_id WHERE m.receiver=1 ORDER BY mi.mail_id,mi.item_guid')
        return {'mails':mails, 'attachments':cursor.fetchall(), 'inventory':inventory()}


def suite(t, point, stage_only):
    actors.session_entry(t.fixture); t.clean_panels(); fixture = MailboxFixture(t.out,t.fixture)
    baseline = mailbox_state(); t.receipt['mailbox_baseline'] = baseline; t.persist()
    try:
        fixture.prepare(); state,frame = t.observe('mailbox_staged')
        t.receipt['staging'] = {'frame':frame,'world_position':state['world_position']}; t.persist()
        if stage_only: return
        require(t.step('mail.open','Open the nearby mailbox.',{
            'mailbox':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby mailbox.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your equipment.'}},
            lambda b,a,s: {'status':'mailbox_open_pass' if s=='mailbox' and 'MailFrame' in a['panels'] else
                          ('controller_failure' if s!='mailbox' else 'client_or_protocol_failure'),
                          'oracle':{'panels':a['panels'],'errors':a['errors'],'lua_errors':a.get('lua_errors')}},
            diagnostic_action='mailbox'),'mailbox_open_pass')
        state,frame = t.observe('mailbox_open')
        t.receipt['mailbox_open'] = {'state':state,'frame':frame,'controls':controls(t)}; t.persist()
        require(t.step('mail.close','Close the mailbox.',{
            'close':{'kind':'key','value':'Escape','description':'Press Escape to close the mailbox.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your equipment.'}},
            lambda b,a,s:{'status':'mailbox_close_pass' if s=='close' and 'MailFrame' not in a['panels'] else
                         ('controller_failure' if s!='close' else 'client_or_protocol_failure')},diagnostic_action='close'),'mailbox_close_pass')
    finally:
        try: t.clean_panels()
        finally: fixture.restore()
        after = mailbox_state(); restored = after == baseline
        state,frame = t.observe('mailbox_restored')
        t.receipt['mailbox_restoration'] = {'mail_inventory_money_unchanged':restored,'after':after,'frame':frame}
        t.persist()
        if not restored: raise RuntimeError('mailbox opening changed native mail or inventory resources')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage-only',action='store_true'); parser.add_argument('--point',type=int,nargs=2)
    args = parser.parse_args()
    if not args.stage_only and (not args.point or any(not 0<=v<bound for v,bound in zip(args.point,[1280,720]))):
        parser.error('requires a bounded observed mailbox point')
    t = Trial(args.output,controller='code' if args.stage_only else 'laya')
    try: suite(t,args.point,args.stage_only); t.receipt['completed'] = True
    except Exception as error: t.receipt['failure'] = f'{type(error).__name__}: {error}'
    finally: t.receipt['finished_at'] = time.time(); t.persist(); print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
