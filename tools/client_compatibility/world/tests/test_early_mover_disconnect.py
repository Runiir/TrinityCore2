"""Only the captured owned login race admits offline registration recovery."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_class_disconnect_recovery import early_mover_proof


@pytest.mark.parametrize('change',[None,'identity','native','ack','channel','account','created','late','cancel','duplicate'])
def test_recovery_binds_owned_login_ack_authenticated_instance_and_closure(change):
    packets=[{'session':'realm','name':'CMSG_PLAYER_LOGIN','direction':'from_client','body':'01a004040800a09f44','time':10},
        {'session':'realm','name':'CMSG_PLAYER_LOGIN','direction':'to_native','body':'2005','time':10.1},
        {'session':'realm','name':'CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE','direction':'from_client','body':'069d7d18','time':10.11}]
    events=[{'session':'instance','event':'instance_authenticated','account_id':2,'time':10.1},
        {'session':'instance','event':'world_connection_closed','error':'gameplay request outside owned active world','time':10.12},
        {'session':'realm','event':'native_stream_closed','error':'Operation canceled [system:125 fixture]','time':10.13}]
    if change=='identity':packets[0]['body']='01a003040800a09f44'
    elif change=='native':packets[1]['body']='2002'
    elif change=='ack':packets[2]['body']='00'
    elif change=='channel':packets[2]['session']='foreign'
    elif change=='account':events[0]['account_id']=3
    elif change=='created':events.append({'session':'realm','event':'native_player_created','guid':4,'time':10.105})
    elif change=='late':events[1]['time']=11
    elif change=='cancel':events[2]['error']='other'
    elif change=='duplicate':packets.append(deepcopy(packets[2]))
    if change:
        with pytest.raises((RuntimeError,ValueError)):early_mover_proof({'guid':4,'account_id':2},events,packets)
    else:assert early_mover_proof({'guid':4,'account_id':2},events,packets)[:2]==('realm','instance')
