import pytest

from chronicle.engine.rules import baseline_rule_set


@pytest.fixture
def rules():
	return baseline_rule_set()
