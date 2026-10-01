"""Protocol boundaries and authentication failures, without a live database."""
import asyncio
import hashlib
import http.client
import json
import secrets
import struct
import threading
import time

import pytest

from tools.client_compatibility.auth import realms, rest, rpc, srp, wire


def client_proof(challenge, login, password):
    # Independent client-side SRP equation, including Blizzard's signed x.
    n, g, b = (int(challenge[key], 16) for key in ("modulus", "generator", "public_B"))
    salt = bytes.fromhex(challenge["salt"])
    login_hash = hashlib.sha256(login.upper().encode()).hexdigest().upper()
    raw = hashlib.pbkdf2_hmac("sha512", (login_hash+":"+password).encode(), salt, 15000, 64)
    x = int.from_bytes(raw, "big", signed=True) % (n-1)
    a = secrets.randbelow(n-2)+1
    public_a = pow(g, a, n)
    k = int.from_bytes(hashlib.sha256(n.to_bytes(256,"big")+g.to_bytes(256,"big")).digest(),"big")
    u = int.from_bytes(hashlib.sha256(public_a.to_bytes(256,"big")+b.to_bytes(256,"big")).digest(),"big")
    secret = pow((b-k*pow(g,x,n)) % n, a+u*x, n)
    def proof(*values):
        encoded = b"".join(value.to_bytes((value.bit_length()+8)//8,"big") for value in values)
        return hashlib.sha256(encoded).hexdigest().upper()
    m1 = proof(public_a,b,secret)
    return public_a, m1, proof(public_a,int(m1,16),secret)


@pytest.mark.parametrize("password", ["Uppercase1", "lowerCase-!", "signed-x-check"])
def test_srp_mutual_proof_and_replay(password):
    login, salt = "CLIENTLAB", bytes(range(32))
    challenge = srp.Challenge(login,salt,srp.verifier(login,password,salt))
    a, m1, m2 = client_proof(challenge.json(),login,password)
    assert challenge.verify(a,m1) == m2
    assert challenge.verify(a,m1) is None


def test_srp_wrong_password_and_invalid_public_key():
    salt = bytes(range(32))
    challenge = srp.Challenge("CLIENTLAB",salt,srp.verifier("CLIENTLAB","Correct",salt))
    a,m1,_ = client_proof(challenge.json(),"CLIENTLAB","Wrong")
    assert challenge.verify(a,m1) is None
    challenge = srp.Challenge("CLIENTLAB",salt,srp.verifier("CLIENTLAB","Correct",salt))
    assert challenge.verify(0,"00") is None


def test_fragmented_rpc_and_size_limit():
    async def exercise():
        reader = asyncio.StreamReader()
        packet = wire.request(0x65446991,1,77,wire.message("connection.v1.ConnectRequest",use_bindless_rpc=True))
        task = asyncio.create_task(wire.read(reader))
        for byte in packet:
            reader.feed_data(bytes([byte]))
            await asyncio.sleep(0)
        header,body = await task
        assert header.token == 77
        assert wire.message("connection.v1.ConnectRequest",body).use_bindless_rpc
        invalid = asyncio.StreamReader()
        invalid.feed_data(struct.pack(">H",4097))
        with pytest.raises(ValueError):
            await wire.read(invalid)
        with pytest.raises(ValueError):
            wire.message("Header", b"\xff")
    asyncio.run(exercise())


class Writer:
    def __init__(self): self.packets=[]
    def write(self,data): self.packets.append(data)


def test_invalid_ticket_cannot_authenticate(monkeypatch):
    monkeypatch.setattr(rpc.accounts,"from_ticket",lambda _:None)
    monkeypatch.setattr(rpc,"event",lambda *a,**kw:None)
    writer=Writer()
    session=rpc.Session(None,writer)
    assert session.logon(b"TC-invalid") == 3
    assert session.account is None
    assert writer.packets == []
    request=wire.message("game_utilities.v1.GetAllValuesForAttributeRequest",attribute_key="Command_RealmListRequest_v1_WoW")
    assert session.dispatch("utilities",10,request.SerializeToString())[0] == 3


def test_unsupported_client_build_rejected_before_authentication():
    session=rpc.Session(None,Writer())
    request=wire.message("authentication.v1.LogonRequest", program="WoW", platform="Win",
                         locale="enUS", application_version=15595)
    assert session.dispatch("auth",1,request.SerializeToString())[0] == 0x1C
    assert session.account is None


def test_expired_session_and_foreign_game_account():
    session=rpc.Session(None,Writer())
    session.account={"id":1,"login":"CLIENTLAB","expires":time.time()-1}
    request=wire.message("account.v1.GetAccountStateRequest")
    assert session.dispatch("account",30,request.SerializeToString())[0] == 3
    session.account["expires"]=time.time()+60
    request=wire.message("account.v1.GetGameAccountStateRequest")
    request.game_account_id.high=0x200000200576F57
    request.game_account_id.low=2
    assert session.dispatch("account",31,request.SerializeToString())[0] == 3


def test_classic_command_suffix_and_realm_compression():
    assert realms.command_name("Command_RealmListTicketRequest_v1_WoW") == "Command_RealmListTicketRequest_v1"
    blob=realms.compressed("JSONRealmListUpdates",{"updates":[]})
    import zlib
    raw=zlib.decompress(blob[4:])
    assert len(raw) == struct.unpack("<I",blob[:4])[0]
    assert raw == b'JSONRealmListUpdates:{"updates":[]}\0'


@pytest.fixture
def rest_server(monkeypatch):
    salt=bytes(range(32))
    account={"id":1,"login":"CLIENTLAB","salt":salt,"verifier":srp.verifier("CLIENTLAB","TestPassword",salt)}
    monkeypatch.setattr(rest.accounts,"get",lambda login: account if login and login.upper()=="CLIENTLAB" else None)
    monkeypatch.setattr(rest.accounts,"issue",lambda account,mode:"TC-test-ticket")
    monkeypatch.setattr(rest,"event",lambda *a,**kw:None)
    server=rest.ThreadingHTTPServer(("127.0.0.1",0),rest.Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    rest.STATES.clear()


@pytest.mark.parametrize("new_connection", [False,True])
def test_rest_srp_session_across_http_connections(rest_server,new_connection):
    conn=http.client.HTTPConnection("127.0.0.1",rest_server,timeout=3)
    headers={"Content-Type":"application/json"}
    form={"inputs":[{"input_id":"account_name","value":"CLIENTLAB"}]}
    conn.request("POST","/bnetserver/login/srp/",json.dumps(form),headers)
    response=conn.getresponse()
    assert response.getheader("Content-Type") == "application/json;charset=utf-8"
    cookie=response.getheader("Set-Cookie").split(";",1)[0]
    a,m1,m2=client_proof(json.loads(response.read()),"CLIENTLAB","TestPassword")
    if new_connection:
        conn.close()
        conn=http.client.HTTPConnection("127.0.0.1",rest_server,timeout=3)
        headers["Cookie"]=cookie
    form["inputs"].extend([{"input_id":"public_A","value":format(a,"X")},
                           {"input_id":"client_evidence_M1","value":m1}])
    conn.request("POST","/bnetserver/login/",json.dumps(form),headers)
    result=json.loads(conn.getresponse().read())
    assert result["login_ticket"] == "TC-test-ticket"
    assert result["server_evidence_M2"] == m2
    conn.request("POST","/bnetserver/login/",json.dumps(form),headers)
    assert "login_ticket" not in json.loads(conn.getresponse().read())
    conn.close()


def test_launcher_rejects_foreign_origin_and_missing_csrf(rest_server):
    conn=http.client.HTTPConnection("127.0.0.1",rest_server,timeout=3)
    conn.request("POST","/lab/launch-direct","{}",{"Content-Type":"application/json","Origin":"https://example.com"})
    response=conn.getresponse()
    assert response.status == 400
    response.read()
    conn.request("POST","/lab/launch-direct","{}",{"Content-Type":"application/json"})
    response=conn.getresponse()
    assert response.status == 403
    response.read()
    conn.close()
