"""The input sender must reject a wrong socket peer before any EI traffic."""
import json,os,socket,subprocess
from pathlib import Path
import pytest
from tools.client_compatibility import lab_runtime as lab


@pytest.fixture
def input_binary():
    path=Path(os.environ.get('CLIENT442_NATIVE_INPUT',str(lab.ROOT/'build/native_input/client442_input')))
    if not path.is_file():pytest.skip('build the independent native input sender')
    return path


def test_wrong_private_socket_peer_is_rejected_before_handshake_or_input(input_binary,tmp_path):
    path=tmp_path/'input.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path));server.listen(1)
        owner=subprocess.Popen(['sleep','10'])
        try:
            request=json.dumps({'kind':'key','code':24,'pressed':True})+'\n'
            result=subprocess.run([str(input_binary),str(path),str(owner.pid),lab.proc_start(owner.pid)],
                input=request,text=True,capture_output=True,timeout=3)
            assert result.returncode==1 and 'another process or lifetime' in json.loads(result.stdout)['error']
            connection,_=server.accept()
            with connection:
                connection.settimeout(1)
                assert connection.recv(1024)==b''
        finally:owner.terminate();owner.wait(timeout=2)


def test_reused_owner_lifetime_is_rejected_before_socket_connection(input_binary,tmp_path):
    path=tmp_path/'input.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path));server.listen(1);server.settimeout(.05)
        result=subprocess.run([str(input_binary),str(path),str(os.getpid()),'0'],
            input='',text=True,capture_output=True,timeout=3)
        assert result.returncode==1 and 'lifetime changed' in json.loads(result.stdout)['error']
        with pytest.raises(socket.timeout):server.accept()
