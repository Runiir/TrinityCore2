"""An empty edit value must use actual text rather than the rendered placeholder."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_macros as module


@pytest.mark.parametrize('actual,expected',[('', 'ui_edit_pass'),('Search','client_or_protocol_failure')])
def test_empty_search_reads_actual_edit_value_with_a_visible_placeholder(monkeypatch,actual,expected):
    field={'kind':'EditBox','enabled':True,'name':'search','text':'Search','x':32768,'y':32768}
    monkeypatch.setattr(module,'controls',lambda trial:[field])
    def step(case,goal,actions,oracle,**kwargs):
        assert actions['field']['value']==''
        state={'edit_fields':[{**field,'text':actual}]}
        return oracle({},state,'field')
    result=module.edit_case(SimpleNamespace(step=step),'search.clear','Clear search.',lambda control:control['name']=='search','')
    assert result['status']==expected
