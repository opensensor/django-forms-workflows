"""
Tests for django_forms_workflows.views.
"""

import pytest
from django.test import Client
from django.urls import reverse

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
)


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def simple_form(form_with_fields):
    """Form with fields, no workflow (auto-approve)."""
    return form_with_fields


# ── form_list ─────────────────────────────────────────────────────────────


class TestFormListView:
    def test_login_required(self, client, simple_form):
        url = reverse("forms_workflows:form_list")
        resp = client.get(url)
        assert resp.status_code == 302  # redirect to login

    def test_lists_active_forms(self, auth_client, simple_form):
        url = reverse("forms_workflows:form_list")
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert simple_form.name.encode() in resp.content

    def test_excludes_inactive_forms(self, auth_client, simple_form, db):
        simple_form.is_active = False
        simple_form.save()
        url = reverse("forms_workflows:form_list")
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert simple_form.name.encode() not in resp.content


# ── form_submit ───────────────────────────────────────────────────────────


class TestFormSubmitView:
    def test_get_form(self, auth_client, simple_form):
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert b"Full Name" in resp.content

    def test_submit_form(self, auth_client, simple_form):
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        data = {
            "full_name": "John Doe",
            "email": "john@example.com",
            "department": "it",
            "amount": "500.00",
            "notes": "Test notes",
        }
        resp = auth_client.post(url, data)
        assert resp.status_code in (200, 302)
        # Submission should exist
        sub = FormSubmission.objects.filter(form_definition=simple_form).first()
        assert sub is not None
        assert sub.form_data["full_name"] == "John Doe"
        # No workflow, so auto-approved
        assert sub.status == "approved"

    def test_submit_invalid_form(self, auth_client, simple_form):
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        data = {
            # Missing required fields
            "notes": "Test notes",
        }
        resp = auth_client.post(url, data)
        assert resp.status_code == 200  # Re-renders form with errors


# ── my_submissions ────────────────────────────────────────────────────────


class TestMySubmissionsView:
    def test_lists_user_submissions(self, auth_client, submission):
        url = reverse("forms_workflows:my_submissions")
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_no_submissions(self, auth_client):
        url = reverse("forms_workflows:my_submissions")
        resp = auth_client.get(url)
        assert resp.status_code == 200


# ── approval_inbox ────────────────────────────────────────────────────────


class TestApprovalInboxView:
    def test_approval_inbox(self, auth_client, user, submission, approval_group):
        user.groups.add(approval_group)
        ApprovalTask.objects.create(
            submission=submission,
            assigned_group=approval_group,
            step_name="Review",
            status="pending",
        )
        url = reverse("forms_workflows:approval_inbox")
        resp = auth_client.get(url)
        assert resp.status_code == 200


# ── withdraw_submission ──────────────────────────────────────────────────


class TestWithdrawSubmission:
    def test_withdraw(self, auth_client, form_with_fields, user):
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Test"},
            status="pending_approval",
        )
        url = reverse("forms_workflows:withdraw_submission", args=[sub.pk])
        resp = auth_client.post(url)
        assert resp.status_code in (200, 302)
        sub.refresh_from_db()
        assert sub.status == "withdrawn"

    def test_cannot_withdraw_approved(self, auth_client, form_with_fields, user):
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Test"},
            status="approved",
        )
        url = reverse("forms_workflows:withdraw_submission", args=[sub.pk])
        auth_client.post(url)
        sub.refresh_from_db()
        assert sub.status == "approved"  # Should not change


# ── submission_detail ────────────────────────────────────────────────────


class TestSubmissionDetail:
    def test_view_own_submission(self, auth_client, submission):
        url = reverse("forms_workflows:submission_detail", args=[submission.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
