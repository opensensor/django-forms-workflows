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

    def test_other_user_cannot_view(self, client, submission, staff_user):
        client.force_login(staff_user)
        url = reverse("forms_workflows:submission_detail", args=[submission.pk])
        resp = client.get(url)
        # Should be forbidden or redirect
        assert resp.status_code in (302, 403)


# ── approve_submission ──────────────────────────────────────────────────


class TestApproveSubmissionView:
    @pytest.fixture
    def approval_setup(self, form_with_fields, user, approver_user, approval_group):
        """Create a submission with a pending approval task."""
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        # Create workflow
        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Manager Review", order=1, approval_logic="any"
        )
        stage.approval_groups.add(approval_group)

        # Create submission
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={
                "full_name": "Test User",
                "email": "test@example.com",
                "department": "it",
                "amount": "500.00",
                "notes": "Review please",
            },
            status="pending_approval",
        )

        # Create task
        task = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Manager Review",
            status="pending",
            stage_number=1,
            workflow_stage=stage,
        )
        approver_user.groups.add(approval_group)
        return sub, task, stage

    def test_approve_get(self, client, approver_user, approval_setup):
        sub, task, _ = approval_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Manager Review" in resp.content

    def test_approve_post(self, client, approver_user, approval_setup):
        sub, task, _ = approval_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.post(url, {"decision": "approve", "comments": "Looks good"})
        assert resp.status_code == 302
        task.refresh_from_db()
        assert task.status == "approved"
        assert task.comments == "Looks good"

    def test_reject_post(self, client, approver_user, approval_setup):
        sub, task, _ = approval_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.post(url, {"decision": "reject", "comments": "Not complete"})
        assert resp.status_code == 302
        task.refresh_from_db()
        assert task.status == "rejected"

    def test_non_approver_denied(self, client, user, approval_setup):
        """A non-approver user should be denied."""
        sub, task, _ = approval_setup
        # user is not in approval_group
        client.force_login(user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_approval_step_sections_in_context(
        self, client, approver_user, approval_setup
    ):
        """Stage 2 approvers should see approval_step_sections in context."""
        sub, task, stage = approval_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert "approval_step_sections" in resp.context


# ── save_draft ──────────────────────────────────────────────────────────


class TestSaveDraft:
    def test_save_draft(self, auth_client, simple_form):
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        data = {
            "full_name": "Draft User",
            "email": "draft@example.com",
            "department": "hr",
            "amount": "100.00",
            "notes": "Draft",
            "save_draft": "true",
        }
        resp = auth_client.post(url, data)
        assert resp.status_code in (200, 302)
        sub = FormSubmission.objects.filter(
            form_definition=simple_form, status="draft"
        ).first()
        assert sub is not None
        assert sub.form_data["full_name"] == "Draft User"


# ── view helpers ────────────────────────────────────────────────────────


class TestResolveFormDataUrls:
    def test_non_file_passthrough(self):
        from django_forms_workflows.views import _resolve_form_data_urls

        data = {"name": "Alice", "age": 30}
        result = _resolve_form_data_urls(data)
        assert result["name"] == "Alice"
        assert result["age"] == 30

    def test_empty_data(self):
        from django_forms_workflows.views import _resolve_form_data_urls

        assert _resolve_form_data_urls(None) == {}
        assert _resolve_form_data_urls({}) == {}

    def test_file_dict_gets_url(self):
        from unittest.mock import patch

        from django_forms_workflows.views import _resolve_form_data_urls

        data = {
            "attachment": {
                "path": "uploads/test.pdf",
                "filename": "test.pdf",
                "size": 1024,
            }
        }
        with patch(
            "django_forms_workflows.views.get_file_url",
            return_value="https://example.com/signed/test.pdf",
        ):
            result = _resolve_form_data_urls(data)
        assert result["attachment"]["url"] == "https://example.com/signed/test.pdf"
        assert result["attachment"]["filename"] == "test.pdf"

    def test_multi_file_list(self):
        from unittest.mock import patch

        from django_forms_workflows.views import _resolve_form_data_urls

        data = {
            "photos": [
                {"path": "uploads/a.jpg", "filename": "a.jpg"},
                {"path": "uploads/b.jpg", "filename": "b.jpg"},
            ]
        }
        with patch(
            "django_forms_workflows.views.get_file_url",
            side_effect=["https://ex.com/a.jpg", "https://ex.com/b.jpg"],
        ):
            result = _resolve_form_data_urls(data)
        assert len(result["photos"]) == 2
        assert result["photos"][0]["url"] == "https://ex.com/a.jpg"


class TestBuildOrderedFormData:
    def test_respects_field_order(self, submission):
        from django_forms_workflows.views import _build_ordered_form_data

        ordered = _build_ordered_form_data(submission, submission.form_data)
        labels = [e["label"] for e in ordered]
        assert labels[0] == "Full Name"  # order=1
        assert labels[1] == "Email"  # order=2

    def test_empty_form_data(self, submission):
        from django_forms_workflows.views import _build_ordered_form_data

        assert _build_ordered_form_data(submission, {}) == []
        assert _build_ordered_form_data(submission, None) == []


class TestBuildApprovalStepSections:
    def test_no_tasks_returns_empty(self, submission):
        from django_forms_workflows.views import _build_approval_step_sections

        assert _build_approval_step_sections(submission) == []

    def test_completed_task_produces_section(
        self, form_with_fields, submission, approval_group, approver_user
    ):
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage
        from django_forms_workflows.views import _build_approval_step_sections

        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Review", order=1)
        stage.approval_groups.add(approval_group)

        from django.utils import timezone

        ApprovalTask.objects.create(
            submission=submission,
            assigned_group=approval_group,
            step_name="Review",
            status="approved",
            completed_by=approver_user,
            completed_at=timezone.now(),
            comments="All good",
            workflow_stage=stage,
            stage_number=1,
        )

        sections = _build_approval_step_sections(submission)
        assert len(sections) == 1
        assert sections[0]["status"] == "approved"
        assert sections[0]["comments"] == "All good"
