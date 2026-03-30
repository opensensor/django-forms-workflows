"""
Tests for django_forms_workflows.templatetags.forms_workflows_tags.
"""

from django_forms_workflows.templatetags.forms_workflows_tags import (
    get_item,
    is_signature,
)


class TestIsSignatureFilter:
    VALID_SIG = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
        "FcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    def test_valid_signature_data_uri(self):
        assert is_signature(self.VALID_SIG) is True

    def test_plain_text(self):
        assert is_signature("Hello World") is False

    def test_empty_string(self):
        assert is_signature("") is False

    def test_none(self):
        assert is_signature(None) is False

    def test_integer(self):
        assert is_signature(42) is False

    def test_dict_value(self):
        assert is_signature({"url": "https://example.com"}) is False

    def test_partial_prefix(self):
        """Must match the full data-URI prefix."""
        assert is_signature("data:image/png;base64") is False

    def test_jpeg_data_uri(self):
        """Only PNG data URIs are considered signatures."""
        assert is_signature("data:image/jpeg;base64,/9j/4AAQ") is False


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
