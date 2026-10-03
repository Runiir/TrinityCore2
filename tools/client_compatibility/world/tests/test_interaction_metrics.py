"""DVC tracking must use real persisted controller identities and input facts."""
import pytest
from tools.client_compatibility.interaction_metrics import choice_counts


def test_real_code_receipts_count_inputs_and_keep_unsubmitted_choices_separate():
    counts=choice_counts([{'controller':'code_diagnostic_ordinary_inputs','cases':[
        {'selected':'button_0','input_transport':[]},{'selected':'field','after_frame':{'file':'after.png'}},
        {'selected':'close','status':'infrastructure_failure'},{'status':'started'}]}])
    assert counts=={'code_choices_selected':3,'code_choices_executed':2,'model_choices_selected':0,'model_choices_executed':0}


def test_historical_model_identity_is_attributed_without_relabeling_it():
    counts=choice_counts([{'controller':'laya_candidate_selection','cases':[{'selected':'a','after_frame':{}}]},
        {'controller':'code','cases':[{'selected':'b','input_transport':[]}]}])
    assert counts=={'code_choices_selected':1,'code_choices_executed':1,'model_choices_selected':1,'model_choices_executed':1}


def test_unknown_controllers_cannot_silently_be_counted_as_models():
    with pytest.raises(ValueError,match='unknown persisted'):choice_counts([{'controller':'unknown','cases':[]}])
