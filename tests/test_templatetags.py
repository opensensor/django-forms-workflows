"""
Tests for django_forms_workflows.templatetags.forms_workflows_tags.
"""

from django_forms_workflows.templatetags.forms_workflows_tags import get_item


class TestGetItemFilter:
    def test_basic_lookup(self):
        d = {"a": 1, "b": 2}
        assert get_item(d, "a") == 1

    def test_missing_key(self):
        d = {"a": 1}
        assert get_item(d, "z") is None

    def test_none_dict(self):
        assert get_item(None, "key") is None

    def test_non_dict(self):
        assert get_item("not a dict", "key") is None

    def test_nested_dict(self):
        d = {"inner": {"x": 10}}
        inner = get_item(d, "inner")
        assert inner == {"x": 10}
