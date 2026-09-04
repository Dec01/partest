"""pytest plugin helpers."""

from partest.pytest_plugin import _humanize_test_name, _format_param_value


def test_humanize():
    assert _humanize_test_name("test_get_client_by_id") == "Get client by id"


def test_format_param():
    assert _format_param_value("admin") == "admin"
    assert _format_param_value(lambda: 1) == "<callable>"
