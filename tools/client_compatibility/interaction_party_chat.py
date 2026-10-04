"""Attribute ordinary party messages in both owned clients and restore the cohort."""
import argparse,hashlib,re,time
from pathlib import Path
from .interaction_ground_movement import suite
from .interaction_chat import packets
from .interaction_social import actor
from .interaction_macros import require
from .interaction_trial import Trial
from . import owned_input


class PartyTrial(Trial):
    def execute(self,action):
        if action['kind']!='chat' or not action['value'].startswith('/p TC442UI:party_'):
            return super().execute(action)
        token=action['value'][3:]
        if not re.fullmatch(r'TC442UI:party_[0-9a-f]{8}',token):
            raise ValueError('party transport accepts only its exact owned fixture marker')
        with owned_input.lease():
            state,_=self.observe('party_transport_before')
            if state['observer_version']<79 or state.get('chat_edit_open'):
                raise RuntimeError('party transport requires observer79 and a closed chat box')
            self.io.key('Return',hold=.4);time.sleep(.2)
            opened,frame=self.observe('party_transport_open')
            if not opened.get('chat_edit_open'):raise RuntimeError('owned party chat edit did not open')
            self.io.type(action['value']);time.sleep(.2)
            pending,frame=self.observe('party_transport_pending')
            checks={'open':bool(pending.get('chat_edit_open')),
                'party_header':pending.get('chat_edit_type')=='PARTY',
                'exact_marker':pending.get('chat_edit_text')==token}
            row={'selected_command':action['value'],'expected_text':token,'checks':checks,
                'observed_text':pending.get('chat_edit_text'),'observed_type':pending.get('chat_edit_type'),
                'frame':frame,'submitted':False,'normalization':'Stock /p consumed into an observed PARTY header only.'}
            self.receipt.setdefault('party_transport_guards',[]).append(row);self.persist()
            if not all(checks.values()):raise RuntimeError('exact party header or marker differs; refusing submission')
            self.io.key('Return',hold=.4);row['submitted']=True;self.persist();time.sleep(.8)
            after,frame=self.observe('party_transport_submitted');row['after_frame']=frame;self.persist()
            if after.get('chat_edit_open'):
                if after.get('chat_edit_type')!='PARTY' or after.get('chat_edit_text')!=token:
                    raise RuntimeError('party entry changed after submission; refusing replay')
                self.io.key('Return',hold=.4);time.sleep(.8)
                after,frame=self.observe('party_transport_retry');row['retry_frame']=frame;self.persist()
                if after.get('chat_edit_open'):raise RuntimeError('owned party marker remained after bounded submission')
            return []


def phase(t,peer,oracle,session,peer_session):
    token='TC442UI:party_'+hashlib.sha256(str(t.out).encode()).hexdigest()[:8];started=time.time()
    events={'CHAT_MSG_PARTY','CHAT_MSG_PARTY_LEADER'}
    def sent(b,a,selected):
        rows=packets(session,started,token)
        checks={'ordinary_request':any(r['direction']=='from_client' and r['name']=='CMSG_CHAT_MESSAGE_PARTY' for r in rows),
            'native_delivery':any(r['direction']=='from_native' and r['name']=='SMSG_MESSAGECHAT' for r in rows),
            'public_message':any(r['text']==token and r['event'] in events for r in a.get('chat_probes',[]))}
        return {'status':'party_chat_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':rows,'token':token}}
    require(t.step('chat.party','Send a unique local fixture message to the owned temporary party.',
        {'party':{'kind':'chat','value':'/p '+token,'description':'Send the fixture marker to the owned party.'}},
        sent,diagnostic_action='party'),'party_chat_pass')
    with actor(peer.fixture['actor']):
        state,frame=peer.observe('owned_party_message_received')
        rows=packets(peer_session,started,token)
        checks={'native_delivery':any(r['direction']=='from_native' and r['name']=='SMSG_MESSAGECHAT' for r in rows),
            'public_message':any(r['text']==token and r['event'] in events for r in state.get('chat_probes',[])),
            'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
        peer.receipt.setdefault('party_message_receipts',[]).append({'token':token,'checks':checks,'packets':rows,'frame':frame});peer.persist()
        if not all(checks.values()):raise RuntimeError('owned peer party delivery differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True,trial_class=PartyTrial)
