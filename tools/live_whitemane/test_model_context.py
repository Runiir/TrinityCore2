import json
from types import SimpleNamespace
import urllib.error
import pytest
from . import model,laya_ui,runtime


def test_expanded_budget_respects_real_encoder_capacity():
    agent=SimpleNamespace(cfg={'max_len':1024},model=SimpleNamespace(
        encoder=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=8192))))
    limits=model.context_limits(agent)
    assert agent.cfg=={'max_len':2048,'head_max_len':512}
    assert limits['encoder_context_limit']==8192
    with pytest.raises(ValueError):model.context_limits(agent,9000)
    with pytest.raises(ValueError):model.context_limits(agent,1024,2048)


def test_temporary_decision_service_reload_retries_the_same_request(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    calls=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self):return json.dumps({'status':'ready'}).encode()
    def open_(request,**kwargs):
        calls.append(request)
        if len(calls)==1:raise urllib.error.URLError('Connection refused')
        return Reply()
    monkeypatch.setattr(laya_ui.urllib.request,'urlopen',open_)
    monkeypatch.setattr(laya_ui.time,'sleep',lambda _:None)
    assert laya_ui.read_json('http://127.0.0.1:8004/health',timeout=5)=={'status':'ready'}
    assert len(calls)==2 and calls[0]==calls[1]


def test_invalid_model_request_is_not_retried(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    def open_(*_,**__):raise urllib.error.HTTPError('localhost',422,'invalid context',{},None)
    monkeypatch.setattr(laya_ui.urllib.request,'urlopen',open_)
    monkeypatch.setattr(laya_ui.time,'sleep',lambda _:pytest.fail('422 must not retry'))
    with pytest.raises(urllib.error.HTTPError):laya_ui.read_json('localhost',timeout=5)
