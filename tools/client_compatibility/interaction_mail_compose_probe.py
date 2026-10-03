"""Observe stock compose controls without sending mail or changing resources."""
import argparse
import json
from pathlib import Path
import time
from . import actors
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .interaction_mail import mailbox_state
from .interaction_mail_actions import open_mailbox
from .mailbox_fixture import MailboxFixture


def suite(t,point):
    actors.session_entry(t.fixture);t.clean_panels();fixture=MailboxFixture(t.out,t.fixture)
    baseline=mailbox_state(t.fixture['guid']);t.receipt['mailbox_baseline']=baseline;t.persist()
    try:
        fixture.prepare();state,frame=t.observe('mailbox_staged')
        t.receipt['staging']={'state':state,'frame':frame};t.persist()
        open_mailbox(t,point)
        require(click_case(t,'mail.compose_probe','Open the Send Mail tab.',lambda c:c['name']=='MailFrameTab2',
            lambda b,a,s:{'status':'mail_compose_open_pass' if s and 'SendMailFrame' in a['panels'] else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'mail_compose_open_pass')
        state,frame=t.observe('compose_controls');rows=controls(t)
        t.receipt['compose_probe']={'state':state,'frame':frame,'controls':rows};t.persist()
    finally:
        try:t.clean_panels()
        finally:fixture.restore()
        after=mailbox_state(t.fixture['guid'])
        t.receipt['restored']=after==baseline;t.persist()
        if after!=baseline:raise RuntimeError('compose-only probe changed native mail or resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2,required=True);a=p.parse_args()
    if any(not 0<=v<bound for v,bound in zip(a.point,[1280,720])):p.error('mailbox point is outside the owned window')
    t=Trial(a.output,controller='code')
    try:suite(t,a.point);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
