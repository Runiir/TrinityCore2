import pytest
from . import inputs,resources,farm_actions,controller_updates,runtime
from .test_farm_loop import row


@pytest.mark.parametrize('action',['command','type','edit_text'])
def test_text_box_inputs_are_rejected_before_focus_or_device_creation(monkeypatch,action):
    monkeypatch.setattr(inputs,'focus',lambda *_:pytest.fail('disabled input must not focus the game'))
    monkeypatch.setattr(resources,'check',lambda *_:pytest.fail('disabled input must stop before controller work'))
    with pytest.raises(RuntimeError,match='text-box input is disabled'):
        inputs.execute('World of Warcraft',action,{'text':'/run ResetView(3)'})


def test_legacy_command_helper_has_no_model_command_choice_or_input(monkeypatch,tmp_path):
    monkeypatch.setattr(farm_actions.laya_ui,'choose',lambda *_:pytest.fail('commands must not be offered'))
    monkeypatch.setattr(inputs,'execute',lambda *_:pytest.fail('legacy helper cannot type'))
    result=farm_actions.command_choice(tmp_path/'legacy',row(),'/reload','Load addon','Reload')
    assert not result['executed'] and result['choice']=='wait'


def test_addon_reload_request_waits_for_public_confirmation_without_typing(monkeypatch,tmp_path):
    import json
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    path=tmp_path/'run/addon_reload_request.json'
    runtime.write(path,{'expected':{'test_schema':'new'},'receipt':str(tmp_path/'receipt.json')})
    monkeypatch.setattr(controller_updates.pending_find,'load',lambda _:None)
    monkeypatch.setattr(inputs,'execute',lambda *_:pytest.fail('cannot issue reload through chat'))
    r=row();r['archaeology']['falling']=False
    assert not controller_updates.apply_addon_request(tmp_path/'step',r)
    assert 'text-box input is disabled' in json.loads(path.read_text())['reason']
    r['farm_ui']['test_schema']='new'
    assert not controller_updates.apply_addon_request(tmp_path/'next',r) and not path.exists()
