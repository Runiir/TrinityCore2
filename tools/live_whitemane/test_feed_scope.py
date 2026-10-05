from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.live_whitemane import bearing_reader,owned_sockets


def test_endpoint_capture_is_filtered_to_the_owned_process_sockets(monkeypatch,tmp_path):
    process=tmp_path/'123'
    (process/'fd').mkdir(parents=True)
    (process/'net').mkdir()
    (process/'fd/1').symlink_to('socket:[77]')
    rows=['header',
        '0: 0100007F:1000 394AFF33:1F95 01 0 0 0 0 0 77',
        '1: 0100007F:1001 394AFF33:1F95 01 0 0 0 0 0 88',
        '2: 0100007F:1002 394AFF33:1F95 08 0 0 0 0 0 77']
    (process/'net/tcp').write_text('\n'.join(rows)+'\n')
    monkeypatch.setattr(owned_sockets,'Path',lambda _:process)
    assert owned_sockets.ports(123)=={0x1000}


@pytest.mark.parametrize('authenticated',[0,1])
def test_initial_unmatched_channel_is_quarantined_but_authenticated_failure_stops(authenticated):
    def fail(*_):raise ValueError('Initial authentication attempt limit')
    key=(123,'server_to_client')
    flow=SimpleNamespace(segment=fail,authenticated=authenticated,alignment=0,
                         buffer=bytearray(10),checked=set(range(65)))
    flows={key:flow};ignored=set();session={}
    if authenticated:
        with pytest.raises(ValueError):bearing_reader.segment_flow(flows,key,1,b'',0,ignored,session)
        assert key in flows and not ignored
    else:
        bearing_reader.segment_flow(flows,key,1,b'',0,ignored,session)
        assert key not in flows and key in ignored
    assert session['flow_failures'][0]['authenticated']==authenticated
    assert 'body' not in session['flow_failures'][0]
