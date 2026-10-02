import struct
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_interaction_packets import call

# Actual 4.4.2 ground click reported by the user. Includes orientation, map=-1,
# FROM_CLIENT send flag and an owned movement update.
CAPTURE=bytes.fromhex('018709020153bc0000000000000000044c0100ebf905000000000000000000000000000000000000000000000000440000000407000000000000005345c8c50d2351c5abaa714300000000ffffffff01a0010408000000000002000000000000350f57058672c8c56b1951c5d6aa7143c16ece3e0000000000000000000000000000000000')


def test_reported_ground_marker_forwards_native_destination(codec):
    answer=result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,
        gameobjects=[],units=[],actions=[{'fn':'cast_request','name':'CMSG_CAST_SPELL','body':CAPTURE.hex()}])
    assert len(answer)==2 and answer[0][0]=='MSG_MOVE_HEARTBEAT'
    expected=struct.pack('<BiiBI',1,84996,0,0,64)+b'\0'+struct.pack('<3f',-6408.66552734375,-3346.190673828125,241.6666717529297)
    assert answer[1]==['CMSG_CAST_SPELL',expected.hex()]
    offset=CAPTURE.index(b'\xff'*4)
    for body in [CAPTURE[:-1],CAPTURE[:offset]+struct.pack('<i',530)+CAPTURE[offset+4:]]:
        response=result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,
            gameobjects=[],units=[],actions=[{'fn':'cast_request','name':'CMSG_CAST_SPELL','body':body.hex()}])
        assert 'error' in response[-1]


def test_marker_snapshots_wait_for_positions_and_clear_without_stale_locations(codec):
    empty='000000000000'
    point={'map':0,'position':[1.5,-2.0,80.0]}
    expected=Writer().pack('BI',0,1).bits(1,4).flush().guid().pack('I3f',0,*point['position']).finish().hex()
    actions=[{'fn':'mask','value':1},{'fn':'location','slot':0,'value':point},
        {'fn':'mask','value':0},{'fn':'mask','value':1}]
    assert result(codec,op='raid_markers',actions=actions)==[None,expected,empty,None]
    assert 'error' in codec(op='raid_markers',actions=[{'fn':'mask','value':32}])
    assert 'error' in codec(op='raid_markers',actions=[{'fn':'location','slot':0,'value':{'map':0,'position':[18000,0,0]}}])


def test_individual_and_clear_all_use_native_five_marker_contract(codec):
    for i in range(5):assert result(codec,op='marker_clear',body=bytes([i]).hex())==[['CMSG_CLEAR_RAID_MARKER',bytes([i]).hex()]]
    assert result(codec,op='marker_clear',body='08')==[['CMSG_CLEAR_RAID_MARKER',bytes([i]).hex()] for i in range(5)]
    for body in ['05','09','0000','']:assert 'error' in codec(op='marker_clear',body=body)
