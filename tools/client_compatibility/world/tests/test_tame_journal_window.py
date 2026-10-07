"""Ambient updates must not consume or substitute the exact Tame proof budget."""
from copy import deepcopy
import pytest
from tools.client_compatibility.hunter_tame_evidence import collect,NAMES
from tools.client_compatibility.review_native_feedback_checkpoint import packet_key


def fixture():
    request={'session':'owned','time':12,'direction':'to_native','name':'CMSG_CAST_SPELL','body':'01eb050000'}
    data={NAMES['cast']:{'native_session':'owned','capture_config':{'created_at':10},'finished_at':20,
        'cast_packets':[request],'capture_packets':[{'name':'MSG_CHANNEL_START'}]},
        NAMES['entry']:{'started_at':1,'finished_at':5}}
    tracking={'raw':set(),'packets':set(),'events':[],'instances':set()}
    return request,data,tracking


def test_many_ambient_updates_do_not_hide_the_exact_request():
    p,d,t=fixture();ambient=[{**p,'time':12+i/1000,'name':'SMSG_ON_MONSTER_MOVE','direction':'from_native',
        'body':str(i)} for i in range(1000)]
    collect('tracking/packets.jsonl',iter([*ambient,p]),d,t)
    assert t['packets']=={packet_key(p)}


@pytest.mark.parametrize('fault',['body','time','session','direction'])
def test_a_nearby_packet_cannot_substitute_the_recorded_request(fault):
    p,d,t=fixture();p=deepcopy(p)
    p[fault]={'body':'02eb050000','time':12.01,'session':'foreign','direction':'from_client'}[fault]
    collect('tracking/packets.jsonl',[p],d,t);assert not t['packets']


def test_the_raw_probe_remains_bounded_even_when_ambient_traffic_is_ignored():
    p,d,t=fixture();rows=[{**p,'time':12+i/1000,'name':'MSG_CHANNEL_START'} for i in range(9)]
    with pytest.raises(RuntimeError,match='journal bound'):
        collect('tracking/owned_tame_request_packets.jsonl',rows,d,t)
