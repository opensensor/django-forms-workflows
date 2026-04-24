"""
Tests for django_forms_workflows.diff_views._build_summary.

Exercises the supplemental diff summary used by the admin side-by-side
form diff viewer — in particular that reviewer_groups and the full set
of PostSubmissionAction fields are compared.
"""

import pytest
from django.contrib.auth.models import Group

from django_forms_workflows.diff_views import _build_summary
from django_forms_workflows.models import (
    FormDefinition,
    FormField,
    PostSubmissionAction,
)
from django_forms_workflows.sync_api import build_export_payload


def _export_two(form_a, form_b):
    payload_a = build_export_payload(FormDefinition.objects.filter(pk=form_a.pk))
    payload_b = build_export_payload(FormDefinition.objects.filter(pk=form_b.pk))
    return [payload_a["forms"][0], payload_b["forms"][0]]


@pytest.fixture
def two_similar_forms(db):
    a = FormDefinition.objects.create(name="Diff A", slug="diff-a", is_active=True)
    b = FormDefinition.objects.create(name="Diff B", slug="diff-b", is_active=True)
    return a, b


class TestReviewerGroupsDiff:
    def test_reviewer_groups_change_surfaces(self, two_similar_forms):
        a, b = two_similar_forms
        a.reviewer_groups.add(Group.objects.create(name="Auditors"))
        b.reviewer_groups.add(Group.objects.create(name="Compliance"))

        summary = _build_summary(_export_two(a, b))

        diffs = summary[0]["diffs"]
        reviewer_lines = [d for d in diffs if "reviewer_groups" in d]
        assert reviewer_lines, f"Expected reviewer_groups diff; got {diffs}"
        line = reviewer_lines[0]
        assert "+Compliance" in line
        assert "-Auditors" in line

    def test_identical_reviewer_groups_no_diff(self, two_similar_forms):
        a, b = two_similar_forms
        g = Group.objects.create(name="Shared Reviewers")
        a.reviewer_groups.add(g)
        b.reviewer_groups.add(g)

        summary = _build_summary(_export_two(a, b))

        assert not any("reviewer_groups" in d for d in summary[0]["diffs"])


class TestPostActionFieldDiff:
    """Every field serialized by sync_api._serialize_post_action should
    also show up in diff_views action_check_keys."""

    def _make_action(self, fd, **overrides):
        defaults = {
            "form_definition": fd,
            "name": "Act",
            "action_type": "email",
            "trigger": "on_approve",
            "email_to": "a@example.com",
        }
        defaults.update(overrides)
        return PostSubmissionAction.objects.create(**defaults)

    @pytest.mark.parametrize(
        "field,a_val,b_val",
        [
            ("api_headers", {"X": "1"}, {"X": "2"}),
            ("api_body_template", "{a}", "{b}"),
            ("email_cc", "cc@a.com", "cc@b.com"),
            ("email_cc_field", "cc_field_a", "cc_field_b"),
            ("email_to_field", "to_a", "to_b"),
            ("email_body_template", "<p>A</p>", "<p>B</p>"),
            ("email_template_name", "tpl_a", "tpl_b"),
            ("db_alias", "default", "warehouse"),
            ("db_table", "users_a", "users_b"),
            ("db_field_mappings", {"x": "a"}, {"x": "b"}),
            ("ldap_dn_template", "cn={a}", "cn={b}"),
            ("ldap_field_mappings", {"mail": "email_a"}, {"mail": "email_b"}),
            ("custom_handler_path", "mod.a", "mod.b"),
            ("custom_handler_config", {"k": "a"}, {"k": "b"}),
            ("fail_silently", True, False),
            ("retry_on_failure", True, False),
            ("max_retries", 3, 5),
            ("description", "desc a", "desc b"),
            ("is_locked", True, False),
        ],
    )
    def test_field_change_surfaces_in_diff(
        self, two_similar_forms, field, a_val, b_val
    ):
        a, b = two_similar_forms
        self._make_action(a, **{field: a_val})
        self._make_action(b, **{field: b_val})

        summary = _build_summary(_export_two(a, b))
        diffs = summary[0]["diffs"]

        assert any(f"Post action 'Act' {field}:" in d for d in diffs), (
            f"Change in '{field}' not surfaced in diff. Got: {diffs}"
        )


class TestShowHelpTextInDetailDiff:
    """A toggle of show_help_text_in_detail on a field should surface as
    a modified-field in the diff summary."""

    def test_flag_change_surfaces(self, two_similar_forms):
        a, b = two_similar_forms
        FormField.objects.create(
            form_definition=a,
            field_name="initials",
            field_label="Initials",
            field_type="text",
            help_text="I agree.",
            show_help_text_in_detail=False,
            order=1,
        )
        FormField.objects.create(
            form_definition=b,
            field_name="initials",
            field_label="Initials",
            field_type="text",
            help_text="I agree.",
            show_help_text_in_detail=True,
            order=1,
        )

        summary = _build_summary(_export_two(a, b))
        diffs = summary[0]["diffs"]
        assert any("Fields modified" in d and "initials" in d for d in diffs), (
            f"show_help_text_in_detail toggle not surfaced. Got: {diffs}"
        )
