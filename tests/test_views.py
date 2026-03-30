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

    def test_approve_comment_help_text_keeps_public_warning_only(
        self, client, approver_user, approval_setup
    ):
        sub, task, _ = approval_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)

        assert b"visible to the submitter" in resp.content
        assert b"add a private field to this approval step" not in resp.content

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

    def test_send_back_option_shown_for_prior_send_back_stage(
        self,
        client,
        form_with_fields,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage1 = WorkflowStage.objects.create(
            workflow=wf,
            name="Manager Review",
            order=1,
            approval_logic="all",
            allow_send_back=True,
        )
        stage1.approval_groups.add(approval_group)
        stage2 = WorkflowStage.objects.create(
            workflow=wf,
            name="Finance Review",
            order=2,
            approval_logic="all",
        )
        stage2.approval_groups.add(second_approval_group)

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

        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Manager Review",
            status="approved",
            stage_number=1,
            workflow_stage=stage1,
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=second_approval_group,
            step_name="Finance Review",
            status="pending",
            stage_number=2,
            workflow_stage=stage2,
        )

        approver_user.groups.add(second_approval_group)
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)

        assert resp.status_code == 200
        assert "send_back_stages" in resp.context
        assert [stage.name for stage in resp.context["send_back_stages"]] == [
            "Manager Review"
        ]
        assert b"Send Back for Correction" in resp.content


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


# ── Signature field integration ────────────────────────────────────────

SAMPLE_SIGNATURE = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
    "FcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class TestSignatureFieldSubmission:
    """End-to-end: submit a form with a signature field and view it."""

    @pytest.fixture
    def sig_form(self, form_definition):
        from django_forms_workflows.models import FormField

        FormField.objects.create(
            form_definition=form_definition,
            field_name="full_name",
            field_label="Full Name",
            field_type="text",
            order=1,
            required=True,
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="sig",
            field_label="Your Signature",
            field_type="signature",
            order=2,
            required=True,
        )
        return form_definition

    def test_submit_with_signature(self, auth_client, sig_form):
        url = reverse("forms_workflows:form_submit", args=[sig_form.slug])
        data = {"full_name": "Jane Doe", "sig": SAMPLE_SIGNATURE}
        resp = auth_client.post(url, data)
        assert resp.status_code in (200, 302)
        sub = FormSubmission.objects.filter(form_definition=sig_form).first()
        assert sub is not None
        assert sub.form_data["sig"].startswith("data:image/png;base64,")

    def test_submission_detail_shows_signature(self, auth_client, sig_form, user):
        sub = FormSubmission.objects.create(
            form_definition=sig_form,
            submitter=user,
            form_data={"full_name": "Jane Doe", "sig": SAMPLE_SIGNATURE},
            status="submitted",
        )
        url = reverse("forms_workflows:submission_detail", args=[sub.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # The signature should render as an <img> tag with the data URI
        assert 'src="data:image/png;base64,' in content
        assert 'alt="Signature"' in content


class TestSerializeSignatureData:
    """serialize_form_data should pass signature data URI strings through."""

    def test_signature_passthrough(self):
        from django_forms_workflows.views import serialize_form_data

        data = {"name": "Test", "sig": SAMPLE_SIGNATURE}
        result = serialize_form_data(data)
        assert result["sig"] == SAMPLE_SIGNATURE
        assert result["name"] == "Test"


class TestResolveSignatureData:
    """_resolve_form_data_urls should leave signature data URIs untouched."""

    def test_signature_not_resolved_as_file(self):
        from django_forms_workflows.views import _resolve_form_data_urls

        data = {"sig": SAMPLE_SIGNATURE, "name": "Alice"}
        result = _resolve_form_data_urls(data)
        assert result["sig"] == SAMPLE_SIGNATURE


class TestBuildPdfRowsSignature:
    """_build_pdf_rows should include signature fields."""

    def test_signature_in_pdf_rows(self, form_definition, user):
        from django_forms_workflows.models import FormField
        from django_forms_workflows.views import _build_pdf_rows

        FormField.objects.create(
            form_definition=form_definition,
            field_name="name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="sig",
            field_label="Signature",
            field_type="signature",
            order=2,
        )
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"name": "Bob", "sig": SAMPLE_SIGNATURE},
            status="submitted",
        )
        rows = _build_pdf_rows(sub)
        sig_values = [
            f["value"]
            for row in rows
            if row.get("fields")
            for f in row["fields"]
            if f["key"] == "sig"
        ]
        assert len(sig_values) == 1
        assert sig_values[0] == SAMPLE_SIGNATURE


class TestSignatureExcludedFromExportSearch:
    """Signature fields should be excluded from search and batch exports."""

    def test_excluded_from_nonsearchable(self):
        from django_forms_workflows.views import _NONSEARCHABLE_FIELD_TYPES

        assert "signature" in _NONSEARCHABLE_FIELD_TYPES

    def test_excluded_from_batch(self):
        from django_forms_workflows.views import _BATCH_EXCLUDED_TYPES

        assert "signature" in _BATCH_EXCLUDED_TYPES


# ── Editable form data in workflow stages ──────────────────────────────


class TestEditableFormData:
    """Tests for allow_edit_form_data on WorkflowStage."""

    @pytest.fixture
    def editable_setup(
        self,
        form_with_fields,
        user,
        approver_user,
        approval_group,
    ):
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Edit & Approve",
            order=1,
            approval_logic="all",
            allow_edit_form_data=True,
        )
        stage.approval_groups.add(approval_group)

        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={
                "full_name": "Original Name",
                "email": "orig@example.com",
                "department": "it",
                "amount": "500.00",
                "notes": "Original notes",
            },
            status="pending_approval",
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Edit & Approve",
            status="pending",
            stage_number=1,
            workflow_stage=stage,
        )
        approver_user.groups.add(approval_group)
        return sub, task, stage

    def test_default_is_false(self, db):
        """allow_edit_form_data should default to False."""
        from django_forms_workflows.models import WorkflowStage

        stage = WorkflowStage()
        assert stage.allow_edit_form_data is False

    def test_editable_form_in_context(self, client, approver_user, editable_setup):
        """GET should include editable_form in context when stage allows editing."""
        sub, task, _ = editable_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["allow_edit_form_data"] is True
        assert resp.context["editable_form"] is not None
        # The editable form should contain the original submission fields
        editable_form = resp.context["editable_form"]
        assert "full_name" in editable_form.fields
        assert "email" in editable_form.fields

    def test_editable_form_shows_editable_label(
        self, client, approver_user, editable_setup
    ):
        sub, task, _ = editable_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert b"(Editable)" in resp.content

    def test_no_editable_form_when_disabled(
        self,
        client,
        form_with_fields,
        user,
        approver_user,
        approval_group,
    ):
        """When allow_edit_form_data is False, editable_form should be None."""
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Normal Approve",
            order=1,
            approval_logic="all",
            allow_edit_form_data=False,
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Test", "email": "t@e.com"},
            status="pending_approval",
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Normal Approve",
            status="pending",
            stage_number=1,
            workflow_stage=stage,
        )
        approver_user.groups.add(approval_group)
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["allow_edit_form_data"] is False
        assert resp.context["editable_form"] is None
        assert b"(Editable)" not in resp.content

    def test_approve_with_edited_data(self, client, approver_user, editable_setup):
        """Approving with edited data should update the submission."""
        sub, task, _ = editable_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.post(
            url,
            {
                "decision": "approve",
                "comments": "Edited and approved",
                "full_name": "Edited Name",
                "email": "edited@example.com",
                "department": "hr",
                "amount": "750.00",
                "notes": "Edited notes",
            },
        )
        assert resp.status_code == 302
        sub.refresh_from_db()
        assert sub.form_data["full_name"] == "Edited Name"
        assert sub.form_data["email"] == "edited@example.com"
        assert sub.form_data["notes"] == "Edited notes"
        task.refresh_from_db()
        assert task.status == "approved"

    def test_reject_ignores_edited_data(self, client, approver_user, editable_setup):
        """Rejecting should NOT apply edits from the editable form."""
        sub, task, _ = editable_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        resp = client.post(
            url,
            {
                "decision": "reject",
                "comments": "Rejected",
                "full_name": "Should Not Save",
                "email": "nosave@example.com",
            },
        )
        assert resp.status_code == 302
        sub.refresh_from_db()
        # Original data should be preserved
        assert sub.form_data["full_name"] == "Original Name"
        assert sub.form_data["email"] == "orig@example.com"
        task.refresh_from_db()
        assert task.status == "rejected"


# ── ChangeHistory tracking ─────────────────────────────────────────────


class TestChangeHistoryModel:
    """Test the ChangeHistory model and its convenience methods."""

    def test_log_create(self, form_definition):
        from django_forms_workflows.models import ChangeHistory

        entry = ChangeHistory.log_create(form_definition)
        assert entry is not None
        assert entry.action == "create"
        assert entry.object_id == form_definition.pk
        assert "Created" in entry.summary

    def test_log_update(self, form_definition, user):
        from django_forms_workflows.models import ChangeHistory

        changes = {"name": {"old": "Old Name", "new": "New Name"}}
        entry = ChangeHistory.log_update(form_definition, changes, user=user)
        assert entry.action == "update"
        assert entry.user == user
        assert entry.changes["name"]["old"] == "Old Name"
        assert entry.changes["name"]["new"] == "New Name"

    def test_log_update_no_changes_returns_none(self, form_definition):
        from django_forms_workflows.models import ChangeHistory

        result = ChangeHistory.log_update(form_definition, {})
        assert result is None

    def test_log_delete(self, form_definition):
        from django_forms_workflows.models import ChangeHistory

        entry = ChangeHistory.log_delete(form_definition)
        assert entry.action == "delete"

    def test_log_json_diff(self, form_definition, user):
        from django_forms_workflows.models import ChangeHistory, FormSubmission

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"name": "Alice", "dept": "IT"},
            status="submitted",
        )
        old = {"name": "Alice", "dept": "IT"}
        new = {"name": "Bob", "dept": "IT"}
        entry = ChangeHistory.log_json_diff(sub, "form_data", old, new, user=user)
        assert entry is not None
        assert "name" in entry.changes
        assert "dept" not in entry.changes
        assert entry.changes["name"]["old"] == "Alice"
        assert entry.changes["name"]["new"] == "Bob"

    def test_log_json_diff_no_changes_returns_none(self, form_definition, user):
        from django_forms_workflows.models import ChangeHistory, FormSubmission

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"name": "Alice"},
            status="submitted",
        )
        result = ChangeHistory.log_json_diff(
            sub, "form_data", {"name": "Alice"}, {"name": "Alice"}
        )
        assert result is None

    def test_str_representation(self, form_definition, user):
        from django_forms_workflows.models import ChangeHistory

        entry = ChangeHistory.log_update(
            form_definition,
            {"name": {"old": "A", "new": "B"}},
            user=user,
        )
        s = str(entry)
        assert "Updated" in s
        assert "1 field" in s


class TestChangeHistoryAutoTracking:
    """Signal-based auto-tracking of config model changes."""

    def test_create_tracked(self, db):
        """Creating a FormDefinition should auto-log a create event."""
        from django_forms_workflows.models import ChangeHistory, FormDefinition

        fd = FormDefinition.objects.create(
            name="AutoTracked Form",
            slug="auto-tracked",
            is_active=True,
        )
        entries = ChangeHistory.objects.filter(
            content_type__model="formdefinition",
            object_id=fd.pk,
            action="create",
        )
        assert entries.count() == 1

    def test_update_tracked(self, form_definition):
        """Updating a FormDefinition should log changed fields."""
        from django_forms_workflows.models import ChangeHistory

        form_definition.name = "Renamed Form"
        form_definition.save()
        entries = ChangeHistory.objects.filter(
            content_type__model="formdefinition",
            object_id=form_definition.pk,
            action="update",
        )
        assert entries.count() >= 1
        latest = entries.first()
        assert "name" in latest.changes

    def test_delete_tracked(self, db):
        """Deleting a tracked model should log a delete event."""
        from django_forms_workflows.models import ChangeHistory, FormDefinition

        fd = FormDefinition.objects.create(
            name="To Delete", slug="to-delete", is_active=True
        )
        fd_pk = fd.pk
        fd.delete()
        entries = ChangeHistory.objects.filter(
            content_type__model="formdefinition",
            object_id=fd_pk,
            action="delete",
        )
        assert entries.count() == 1

    def test_no_log_when_nothing_changed(self, form_definition):
        """Saving without changes should not create an update entry."""
        from django_forms_workflows.models import ChangeHistory

        initial_count = ChangeHistory.objects.filter(
            content_type__model="formdefinition",
            object_id=form_definition.pk,
            action="update",
        ).count()
        form_definition.save()  # no changes
        final_count = ChangeHistory.objects.filter(
            content_type__model="formdefinition",
            object_id=form_definition.pk,
            action="update",
        ).count()
        assert final_count == initial_count


class TestChangeHistoryFormDataEdit:
    """form_data edits during approval should be logged."""

    @pytest.fixture
    def editable_setup(self, form_with_fields, user, approver_user, approval_group):
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        wf = WorkflowDefinition.objects.create(
            form_definition=form_with_fields, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Edit Stage",
            order=1,
            approval_logic="all",
            allow_edit_form_data=True,
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={
                "full_name": "Original",
                "email": "orig@example.com",
                "department": "it",
                "amount": "100",
                "notes": "Original notes",
            },
            status="pending_approval",
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Edit Stage",
            status="pending",
            stage_number=1,
            workflow_stage=stage,
        )
        approver_user.groups.add(approval_group)
        return sub, task

    def test_form_data_edit_logged(self, client, approver_user, editable_setup):
        """Approving with edits should create a ChangeHistory entry."""
        from django_forms_workflows.models import ChangeHistory

        sub, task = editable_setup
        client.force_login(approver_user)
        url = reverse("forms_workflows:approve_submission", args=[task.pk])
        client.post(
            url,
            {
                "decision": "approve",
                "comments": "Edited",
                "full_name": "Edited Name",
                "email": "edited@example.com",
                "department": "hr",
                "amount": "200",
                "notes": "Edited notes",
            },
        )
        entries = ChangeHistory.objects.filter(
            content_type__model="formsubmission",
            object_id=sub.pk,
        )
        # Should have at least one json diff entry
        json_entries = [
            e for e in entries if "form_data" in e.summary or "full_name" in e.changes
        ]
        assert len(json_entries) >= 1
        entry = json_entries[0]
        assert entry.changes["full_name"]["old"] == "Original"
        assert entry.changes["full_name"]["new"] == "Edited Name"
        assert entry.user == approver_user
