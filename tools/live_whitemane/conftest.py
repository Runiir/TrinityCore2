"""Keep unit tests independent of whichever local model the user is running."""
import pytest
from . import decision_backend


@pytest.fixture(autouse=True)
def isolated_decision_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_backend, 'configuration_path',
                        lambda: tmp_path / 'run/decision_backend.json')
