"""Attribute ordinary party messages in both owned clients and restore the cohort."""
import argparse,hashlib,time
from pathlib import Path
from .interaction_ground_movement import suite
from .interaction_chat import packets
from .interaction_social import actor
from .interaction_macros import require


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
    suite(p.parse_args().output,work=phase,separated=True)
