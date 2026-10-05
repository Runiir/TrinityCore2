"""Owned note attribution requires one exact request on each protocol side."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friend_notes import wire_checks,GUID,HIGH,NOTE
from tools.client_compatibility.world.buffer import Writer


def trace(note=NOTE,guid=GUID,realm=1):
    modern=Writer().pack('I',realm).guid(guid,HIGH).bits(len(note.encode()),10).raw(note.encode()).finish()
    native=struct.pack('<Q',guid)+note.encode()+b'\0'
    return [{'name':'CMSG_SET_CONTACT_NOTES','direction':d,'body':b.hex()} for d,b in
        [('from_client',modern),('to_native',native)]]


@pytest.mark.parametrize('note',[NOTE,''])
def test_note_and_empty_restoration_have_exact_owned_request(note):
    assert all(wire_checks(trace(note),note).values())


@pytest.mark.parametrize('index',[0,1])
def test_missing_or_duplicate_side_cannot_qualify(index):
    rows=trace();missing=copy.deepcopy(rows);missing.pop(index)
    assert not all(wire_checks(missing,NOTE).values())
    assert not all(wire_checks(rows+[rows[index]],NOTE).values())


@pytest.mark.parametrize('kwargs',[{'note':'different note'},{'guid':3},{'realm':2}])
def test_different_note_actor_or_realm_is_rejected(kwargs):
    assert not all(wire_checks(trace(**kwargs),NOTE).values())


def test_declared_length_does_not_hide_trailing_bytes():
    rows=trace();rows[0]['body']+='00'
    with pytest.raises(ValueError):wire_checks(rows,NOTE)


def test_truncated_native_note_is_not_an_exact_request():
    rows=trace();rows[1]['body']=rows[1]['body'][:-2]
    assert not all(wire_checks(rows,NOTE).values())
