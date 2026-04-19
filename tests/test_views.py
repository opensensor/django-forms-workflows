"""
Tests for django_forms_workflows.views.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from django_forms_workflows.models import (
    ApprovalTask,
    FormDefinition,
    FormField,
    FormSubmission,
)
from django_forms_workflows.views import _pipe_answer_tokens


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
    def test_anonymous_access_shows_public_forms_only(self, client, simple_form):
        """Anonymous users can access the form list and see only public forms."""
        url = reverse("forms_workflows:form_list")
        resp = client.get(url)
        assert resp.status_code == 200
        # simple_form has requires_login=True by default, so not visible
        assert simple_form.name.encode() not in resp.content

    def test_anonymous_sees_public_form(self, client, simple_form):
        """Anonymous users see forms with requires_login=False."""
        simple_form.requires_login = False
        simple_form.save()
        url = reverse("forms_workflows:form_list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert simple_form.name.encode() in resp.content

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

    def test_approval_inbox_ajax_handles_anonymous_submitter(
        self, auth_client, user, form_with_fields, approval_group
    ):
        user.groups.add(approval_group)
        anon_sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=None,
            form_data={"full_name": "Walk-in"},
            status="submitted",
        )
        ApprovalTask.objects.create(
            submission=anon_sub,
            assigned_group=approval_group,
            step_name="Review",
            status="pending",
        )
        url = reverse("forms_workflows:approval_inbox_ajax")
        resp = auth_client.post(url, {"draw": 1, "start": 0, "length": 10})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["recordsTotal"] >= 1
        assert any("Anonymous" in row["submitter"] for row in payload["data"])


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

    def test_withdraw_dispatches_form_withdrawn_notification(
        self, auth_client, form_with_fields, user
    ):
        """Withdrawal must call _dispatch_notification_rules with 'form_withdrawn'."""
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Test"},
            status="pending_approval",
        )
        url = reverse("forms_workflows:withdraw_submission", args=[sub.pk])
        with mock.patch(
            "django_forms_workflows.workflow_engine._dispatch_notification_rules"
        ) as mock_dispatch:
            auth_client.post(url)
        mock_dispatch.assert_called_once_with(mock.ANY, "form_withdrawn")
        # Verify it was called with the right submission
        assert mock_dispatch.call_args[0][0].id == sub.id


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
        # Rows are structured dicts; extract labels from field entries
        labels = []
        for row in ordered:
            for field in row.get("fields", []):
                labels.append(field["label"])
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


# ── form_qr_code ──────────────────────────────────────────────────────────


class TestFormQrCodeView:
    """Tests for the form_qr_code view that generates QR codes."""

    def test_qr_svg_default(self, client, simple_form):
        """Default format returns an SVG QR code."""
        url = reverse("forms_workflows:form_qr_code", args=[simple_form.slug])
        resp = client.get(url)
        try:
            import segno  # noqa: F401

            assert resp.status_code == 200
            assert resp["Content-Type"] == "image/svg+xml"
            assert b"<svg" in resp.content
        except ImportError:
            assert resp.status_code == 501

    def test_qr_png_format(self, client, simple_form):
        """Requesting format=png returns a PNG QR code."""
        url = reverse("forms_workflows:form_qr_code", args=[simple_form.slug])
        resp = client.get(url, {"format": "png"})
        try:
            import segno  # noqa: F401

            assert resp.status_code == 200
            assert resp["Content-Type"] == "image/png"
            # PNG magic bytes
            assert resp.content[:4] == b"\x89PNG"
        except ImportError:
            assert resp.status_code == 501

    def test_qr_inactive_form_404(self, client, simple_form):
        """QR code for an inactive form returns 404."""
        simple_form.is_active = False
        simple_form.save()
        url = reverse("forms_workflows:form_qr_code", args=[simple_form.slug])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_qr_nonexistent_slug_404(self, client, db):
        """QR code for a non-existent slug returns 404."""
        url = reverse("forms_workflows:form_qr_code", args=["does-not-exist"])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_qr_anonymous_access(self, client, simple_form):
        """QR code endpoint is accessible without authentication."""
        url = reverse("forms_workflows:form_qr_code", args=[simple_form.slug])
        resp = client.get(url)
        # Should not redirect to login
        assert resp.status_code != 302


# ── submission controls ────────────────────────────────────────────────────


class TestSubmissionControls:
    """Tests for close_date, max_submissions, and one_per_user enforcement."""

    # ── close_date ────────────────────────────────────────────────────────

    def test_close_date_past_blocks_get(self, auth_client, simple_form):
        """Form with a past close_date redirects on GET."""
        simple_form.close_date = timezone.now() - timedelta(hours=1)
        simple_form.save()
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("forms_workflows:form_list"))

    def test_close_date_future_allows_get(self, auth_client, simple_form):
        """Form with a future close_date renders normally."""
        simple_form.close_date = timezone.now() + timedelta(days=7)
        simple_form.save()
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_close_date_none_allows_get(self, auth_client, simple_form):
        """Form with no close_date is always open."""
        simple_form.close_date = None
        simple_form.save()
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    # ── max_submissions ───────────────────────────────────────────────────

    def test_max_submissions_at_limit_blocks_get(self, auth_client, simple_form, user):
        """Form at its submission limit redirects on GET."""
        simple_form.max_submissions = 2
        simple_form.save()
        for _ in range(2):
            FormSubmission.objects.create(
                form_definition=simple_form,
                submitter=user,
                form_data={},
                status="submitted",
            )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 302

    def test_max_submissions_under_limit_allows_get(
        self, auth_client, simple_form, user
    ):
        """Form below its submission limit renders normally."""
        simple_form.max_submissions = 5
        simple_form.save()
        FormSubmission.objects.create(
            form_definition=simple_form,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_max_submissions_drafts_not_counted(self, auth_client, simple_form, user):
        """Draft submissions don't count toward the max_submissions limit."""
        simple_form.max_submissions = 1
        simple_form.save()
        FormSubmission.objects.create(
            form_definition=simple_form,
            submitter=user,
            form_data={},
            status="draft",
        )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    # ── one_per_user ──────────────────────────────────────────────────────

    def test_one_per_user_blocks_second_submission(
        self, auth_client, simple_form, user
    ):
        """Second submission by the same user is redirected to my_submissions."""
        simple_form.one_per_user = True
        simple_form.save()
        FormSubmission.objects.create(
            form_definition=simple_form,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("forms_workflows:my_submissions"))

    def test_one_per_user_allows_first_submission(self, auth_client, simple_form):
        """First submission is allowed when one_per_user is set."""
        simple_form.one_per_user = True
        simple_form.save()
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_one_per_user_ignores_draft_submissions(
        self, auth_client, simple_form, user
    ):
        """A draft doesn't count as a previous submission for one_per_user."""
        simple_form.one_per_user = True
        simple_form.save()
        FormSubmission.objects.create(
            form_definition=simple_form,
            submitter=user,
            form_data={},
            status="draft",
        )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_one_per_user_ignores_withdrawn_submissions(
        self, auth_client, simple_form, user
    ):
        """A withdrawn submission doesn't count for one_per_user."""
        simple_form.one_per_user = True
        simple_form.save()
        FormSubmission.objects.create(
            form_definition=simple_form,
            submitter=user,
            form_data={},
            status="withdrawn",
        )
        url = reverse("forms_workflows:form_submit", args=[simple_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200


# ── analytics dashboard ────────────────────────────────────────────────────


class TestAnalyticsDashboard:
    """Tests for the analytics dashboard view."""

    def test_requires_login(self, client):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = client.get(url)
        assert resp.status_code == 302

    def test_accessible_to_authenticated_user(self, auth_client):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_context_contains_summary_keys(self, auth_client, submission):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url)
        for key in (
            "total_submissions",
            "approved_count",
            "rejected_count",
            "pending_count",
            "withdrawn_count",
        ):
            assert key in resp.context, f"Missing context key: {key}"

    def test_context_contains_period_comparison_keys(self, auth_client):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url)
        for key in ("total_change", "approved_change", "approval_rate"):
            assert key in resp.context, f"Missing period-comparison key: {key}"

    def test_filter_by_form_slug(self, auth_client, submission, simple_form):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url, {"form": simple_form.slug})
        assert resp.status_code == 200
        assert resp.context["total_submissions"] >= 0

    def test_custom_day_range(self, auth_client, submission):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url, {"days": "30"})
        assert resp.status_code == 200

    def test_no_submissions_produces_zero_counts(self, auth_client):
        url = reverse("forms_workflows:analytics_dashboard")
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert resp.context["total_submissions"] == 0


# ── analytics CSV export ───────────────────────────────────────────────────


class TestAnalyticsExportCSV:
    """Tests for the analytics CSV export endpoint."""

    def test_requires_login(self, client):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = client.get(url)
        assert resp.status_code == 302

    def test_returns_csv_content_type(self, auth_client, submission):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert "text/csv" in resp["Content-Type"]

    def test_response_has_attachment_disposition(self, auth_client):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url)
        assert "attachment" in resp["Content-Disposition"]

    def test_header_row_present(self, auth_client):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url)
        assert b"Date,Form,Status,Submitter,Submission ID" in resp.content

    def test_submission_appears_in_export(self, auth_client, submission):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url)
        assert str(submission.id).encode() in resp.content

    def test_filter_by_form_includes_matching(
        self, auth_client, submission, simple_form
    ):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url, {"form": simple_form.slug})
        assert str(submission.id).encode() in resp.content

    def test_filter_by_form_excludes_other_forms(
        self, auth_client, submission, simple_form, category, user
    ):
        other = FormDefinition.objects.create(
            name="ZZZZ Other Form Unique",
            slug="other-form",
            category=category,
            is_active=True,
        )
        FormSubmission.objects.create(
            form_definition=other,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url, {"form": simple_form.slug})
        content = resp.content.decode()
        # The submission for simple_form is present; the other form's name is not.
        assert str(submission.id) in content
        assert "ZZZZ Other Form Unique" not in content

    def test_default_filename_uses_90_days(self, auth_client):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url)
        assert "90d.csv" in resp["Content-Disposition"]

    def test_custom_day_range_in_filename(self, auth_client):
        url = reverse("forms_workflows:analytics_export_csv")
        resp = auth_client.get(url, {"days": "30"})
        assert "30d.csv" in resp["Content-Disposition"]


# ── _pipe_answer_tokens ────────────────────────────────────────────────────


class TestPipeAnswerTokens:
    """Unit tests for the _pipe_answer_tokens() helper."""

    def test_basic_replacement(self):
        assert _pipe_answer_tokens("Hello {name}", {"name": "Alice"}) == "Hello Alice"

    def test_multiple_tokens(self):
        result = _pipe_answer_tokens("{first} {last}", {"first": "John", "last": "Doe"})
        assert result == "John Doe"

    def test_unknown_token_becomes_empty_string(self):
        assert _pipe_answer_tokens("Hi {unknown}!", {}) == "Hi !"

    def test_no_tokens_passes_through_unchanged(self):
        assert _pipe_answer_tokens("No tokens here.", {"x": "y"}) == "No tokens here."

    def test_empty_string(self):
        assert _pipe_answer_tokens("", {"x": "y"}) == ""

    def test_list_value_comma_joined(self):
        result = _pipe_answer_tokens("{choices}", {"choices": ["A", "B", "C"]})
        assert result == "A, B, C"

    def test_token_in_url(self):
        result = _pipe_answer_tokens(
            "https://example.com/?dept={dept}&ref={ref}",
            {"dept": "hr", "ref": "42"},
        )
        assert result == "https://example.com/?dept=hr&ref=42"

    def test_partial_unknown_token(self):
        """Known tokens are replaced; unknown tokens become empty strings."""
        result = _pipe_answer_tokens("{name} from {unknown}", {"name": "Bob"})
        assert result == "Bob from "

    def test_same_token_repeated(self):
        result = _pipe_answer_tokens("{x} and {x}", {"x": "yes"})
        assert result == "yes and yes"


# ── submission_success view ────────────────────────────────────────────────


class TestSubmissionSuccessView:
    """Tests for the /submissions/<id>/success/ view."""

    def test_returns_200(self, auth_client, form_with_fields, user):
        form_with_fields.success_message = "<p>Thank you!</p>"
        form_with_fields.save()
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Alice"},
            status="submitted",
        )
        url = reverse("forms_workflows:submission_success", args=[sub.id])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_tokens_piped_in_rendered_message(
        self, auth_client, form_with_fields, user
    ):
        form_with_fields.success_message = "Thank you {full_name}!"
        form_with_fields.save()
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={"full_name": "Bob"},
            status="submitted",
        )
        url = reverse("forms_workflows:submission_success", args=[sub.id])
        resp = auth_client.get(url)
        assert b"Thank you Bob!" in resp.content

    def test_unknown_token_rendered_as_empty(self, auth_client, form_with_fields, user):
        form_with_fields.success_message = "Hi {missing_field}!"
        form_with_fields.save()
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse("forms_workflows:submission_success", args=[sub.id])
        resp = auth_client.get(url)
        assert b"Hi !" in resp.content

    def test_nonexistent_submission_returns_404(self, auth_client, db):
        url = reverse("forms_workflows:submission_success", args=[999999])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_anonymous_access_allowed(self, client, form_with_fields, user):
        """Success page has no login_required; anonymous users can view it."""
        form_with_fields.success_message = "Done!"
        form_with_fields.save()
        sub = FormSubmission.objects.create(
            form_definition=form_with_fields,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse("forms_workflows:submission_success", args=[sub.id])
        resp = client.get(url)
        assert resp.status_code == 200


# ── success routing in form_submit ─────────────────────────────────────────


class TestSuccessRouting:
    """Tests for the post-submission routing: rules → static URL → message → default."""

    # Valid POST data that satisfies simple_form's required fields
    POST_DATA = {
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "department": "hr",
        "amount": "100.00",
        "notes": "routing test",
    }

    def _post(self, auth_client, form):
        url = reverse("forms_workflows:form_submit", args=[form.slug])
        return auth_client.post(url, self.POST_DATA)

    # ── static redirect URL ────────────────────────────────────────────────

    def test_static_redirect_url_redirects(self, auth_client, simple_form):
        simple_form.success_redirect_url = "https://example.com/thanks/"
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert resp["Location"] == "https://example.com/thanks/"

    def test_static_redirect_url_with_token(self, auth_client, simple_form):
        simple_form.success_redirect_url = "https://example.com/?dept={department}"
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert resp["Location"] == "https://example.com/?dept=hr"

    # ── success message ────────────────────────────────────────────────────

    def test_success_message_redirects_to_success_page(self, auth_client, simple_form):
        simple_form.success_message = "Thank you {full_name}!"
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert "/success/" in resp["Location"]

    def test_success_page_url_contains_submission_id(self, auth_client, simple_form):
        simple_form.success_message = "Done!"
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        sub = FormSubmission.objects.filter(form_definition=simple_form).latest("id")
        expected = reverse(
            "forms_workflows:submission_success",
            kwargs={"submission_id": sub.id},
        )
        assert resp["Location"].endswith(expected)

    # ── conditional redirect rules ─────────────────────────────────────────

    def test_matching_rule_redirects(self, auth_client, simple_form):
        simple_form.success_redirect_rules = [
            {
                "url": "https://example.com/hr/",
                "field": "department",
                "operator": "equals",
                "value": "hr",
            }
        ]
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert resp["Location"] == "https://example.com/hr/"

    def test_non_matching_rule_falls_through_to_static_url(
        self, auth_client, simple_form
    ):
        simple_form.success_redirect_rules = [
            {
                "url": "https://example.com/finance/",
                "field": "department",
                "operator": "equals",
                "value": "finance",
            }
        ]
        simple_form.success_redirect_url = "https://example.com/fallback/"
        simple_form.save()
        # POST_DATA has department=hr, rule expects finance → no match
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert resp["Location"] == "https://example.com/fallback/"

    def test_first_matching_rule_wins(self, auth_client, simple_form):
        simple_form.success_redirect_rules = [
            {
                "url": "https://example.com/first/",
                "field": "department",
                "operator": "equals",
                "value": "hr",
            },
            {
                "url": "https://example.com/second/",
                "field": "department",
                "operator": "equals",
                "value": "hr",
            },
        ]
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp["Location"] == "https://example.com/first/"

    def test_rule_url_token_piped(self, auth_client, simple_form):
        simple_form.success_redirect_rules = [
            {
                "url": "https://example.com/?dept={department}",
                "field": "department",
                "operator": "equals",
                "value": "hr",
            }
        ]
        simple_form.save()
        resp = self._post(auth_client, simple_form)
        assert resp["Location"] == "https://example.com/?dept=hr"

    # ── default behaviour ──────────────────────────────────────────────────

    def test_no_config_redirects_to_my_submissions(self, auth_client, simple_form):
        resp = self._post(auth_client, simple_form)
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("forms_workflows:my_submissions"))


# ── Payment Provider Registry ────────────────────────────────────────────


class TestPaymentRegistry:
    def test_register_and_get_provider(self):
        from django_forms_workflows.payments.base import PaymentProvider
        from django_forms_workflows.payments.registry import (
            _registry,
            get_provider,
            register_provider,
        )

        class DummyProvider(PaymentProvider):
            def get_name(self):
                return "Dummy"

            def get_flow_type(self):
                from django_forms_workflows.payments.base import PaymentFlow

                return PaymentFlow.INLINE

            def is_available(self):
                return True

            def create_payment(self, *a, **kw):
                pass

            def confirm_payment(self, *a, **kw):
                pass

            def handle_webhook(self, *a, **kw):
                pass

            def get_client_config(self):
                return {}

            def get_receipt_data(self, *a, **kw):
                return {}

            def refund_payment(self, *a, **kw):
                pass

        register_provider("dummy_test", DummyProvider)
        try:
            provider = get_provider("dummy_test")
            assert provider.get_name() == "Dummy"
            assert provider.is_available() is True
        finally:
            _registry.pop("dummy_test", None)

    def test_get_provider_not_registered(self):
        from django_forms_workflows.payments.registry import get_provider

        result = get_provider("nonexistent_provider_xyz")
        assert result is None

    def test_get_available_providers(self):
        from django_forms_workflows.payments.registry import get_available_providers

        providers = get_available_providers()
        # Should at least return a dict (may include stripe if available)
        assert isinstance(providers, dict)

    def test_get_provider_choices(self):
        from django_forms_workflows.payments.registry import get_provider_choices

        choices = get_provider_choices()
        assert isinstance(choices, list)
        # Each choice is a (value, label) tuple
        for value, label in choices:
            assert isinstance(value, str)
            assert isinstance(label, str)

    def test_stripe_auto_registered(self):
        """Stripe provider is auto-registered in AppConfig.ready()."""
        from django_forms_workflows.payments.registry import _registry

        assert "stripe" in _registry


# ── Payment Views ────────────────────────────────────────────────────────


class TestPaymentViews:
    @pytest.fixture
    def paid_form(self, db, category, user):
        fd = FormDefinition.objects.create(
            name="Paid Form",
            slug="paid-form",
            category=category,
            is_active=True,
            payment_enabled=True,
            payment_provider="stripe",
            payment_amount_type="fixed",
            payment_fixed_amount="25.00",
            payment_currency="usd",
            created_by=user,
        )
        return fd

    @pytest.fixture
    def pending_payment_submission(self, paid_form, user):
        return FormSubmission.objects.create(
            form_definition=paid_form,
            submitter=user,
            form_data={"name": "Test User"},
            status="pending_payment",
        )

    def test_initiate_payment_404_on_wrong_status(self, auth_client, paid_form, user):
        sub = FormSubmission.objects.create(
            form_definition=paid_form,
            submitter=user,
            form_data={},
            status="submitted",
        )
        url = reverse(
            "forms_workflows:payment_initiate",
            args=[sub.id],
        )
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_cancel_payment(self, auth_client, paid_form, pending_payment_submission):
        url = reverse(
            "forms_workflows:payment_cancel",
            args=[pending_payment_submission.id],
        )
        resp = auth_client.post(url)
        assert resp.status_code == 302
        pending_payment_submission.refresh_from_db()
        # Cancel sets submission back to draft so user can resubmit
        assert pending_payment_submission.status == "draft"

    def test_cancel_payment_marks_payment_record(
        self, auth_client, paid_form, pending_payment_submission
    ):
        from django_forms_workflows.models import PaymentRecord

        pr = PaymentRecord.objects.create(
            submission=pending_payment_submission,
            form_definition=paid_form,
            provider_name="stripe",
            amount="25.00",
            status="pending",
            idempotency_key="key_cancel_test",
        )
        url = reverse(
            "forms_workflows:payment_cancel",
            args=[pending_payment_submission.id],
        )
        resp = auth_client.post(url)
        assert resp.status_code == 302
        pr.refresh_from_db()
        assert pr.status == "cancelled"


# ── Stripe Provider Unit ─────────────────────────────────────────────────


class TestStripeProvider:
    def test_name(self):
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        p = StripePaymentProvider()
        assert p.get_name() == "Stripe"

    def test_flow_type_inline(self):
        from django_forms_workflows.payments.base import PaymentFlow
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        p = StripePaymentProvider()
        assert p.get_flow_type() == PaymentFlow.INLINE

    def test_not_available_without_keys(self, settings):
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        settings.STRIPE_SECRET_KEY = ""
        settings.STRIPE_PUBLISHABLE_KEY = ""
        p = StripePaymentProvider()
        assert p.is_available() is False

    def test_available_with_keys(self, settings):
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        settings.STRIPE_SECRET_KEY = "sk_test_xxx"
        settings.STRIPE_PUBLISHABLE_KEY = "pk_test_xxx"
        p = StripePaymentProvider()
        assert p.is_available() is True

    def test_client_config(self, settings):
        from django_forms_workflows.payments.base import PaymentResult, PaymentStatus
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        settings.STRIPE_PUBLISHABLE_KEY = "pk_test_abc"
        p = StripePaymentProvider()
        result = PaymentResult(
            success=True,
            status=PaymentStatus.PENDING,
            client_secret="cs_test_xyz",
        )
        config = p.get_client_config(result)
        assert config["publishable_key"] == "pk_test_abc"
        assert config["client_secret"] == "cs_test_xyz"


# ── Payment Data Structures ──────────────────────────────────────────────


class TestPaymentDataStructures:
    def test_payment_flow_enum(self):
        from django_forms_workflows.payments.base import PaymentFlow

        assert PaymentFlow.INLINE.value == "inline"
        assert PaymentFlow.REDIRECT.value == "redirect"

    def test_payment_status_enum(self):
        from django_forms_workflows.payments.base import PaymentStatus

        assert PaymentStatus.PENDING.value == "pending"
        assert PaymentStatus.COMPLETED.value == "completed"
        assert PaymentStatus.FAILED.value == "failed"
        assert PaymentStatus.REFUNDED.value == "refunded"

    def test_payment_result_dataclass(self):
        from django_forms_workflows.payments.base import PaymentResult, PaymentStatus

        result = PaymentResult(
            success=True,
            transaction_id="tx_123",
            status=PaymentStatus.COMPLETED,
        )
        assert result.success is True
        assert result.transaction_id == "tx_123"
        assert result.client_secret == ""
        assert result.redirect_url == ""

    def test_payment_result_with_redirect(self):
        from django_forms_workflows.payments.base import PaymentResult, PaymentStatus

        result = PaymentResult(
            success=True,
            transaction_id="tx_456",
            status=PaymentStatus.PENDING,
            redirect_url="https://pay.example.com/checkout",
        )
        assert result.redirect_url == "https://pay.example.com/checkout"


# ── Embeddable Forms ─────────────────────────────────────────────────────


class TestEmbedView:
    @pytest.fixture
    def embed_form(self, db, category, user):
        fd = FormDefinition.objects.create(
            name="Embed Form",
            slug="embed-form",
            category=category,
            is_active=True,
            embed_enabled=True,
            requires_login=False,
            created_by=user,
        )
        FormField.objects.create(
            form_definition=fd,
            field_name="full_name",
            field_label="Full Name",
            field_type="text",
            order=1,
            required=True,
        )
        return fd

    @pytest.fixture
    def non_embed_form(self, db, category, user):
        return FormDefinition.objects.create(
            name="No Embed",
            slug="no-embed",
            category=category,
            is_active=True,
            embed_enabled=False,
            created_by=user,
        )

    def test_get_embed_form(self, client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"embed_base" in resp.content or b"Full Name" in resp.content
        # Should not have X-Frame-Options header (xframe_options_exempt)
        assert "X-Frame-Options" not in resp

    def test_embed_disabled_returns_403(self, client, non_embed_form):
        url = reverse("forms_workflows:form_embed", args=[non_embed_form.slug])
        resp = client.get(url)
        assert resp.status_code == 403

    def test_embed_inactive_form_404(self, db, category, user, client):
        fd = FormDefinition.objects.create(
            name="Inactive",
            slug="inactive-embed",
            category=category,
            is_active=False,
            embed_enabled=True,
            created_by=user,
        )
        url = reverse("forms_workflows:form_embed", args=[fd.slug])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_embed_submit_valid(self, client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.post(url, {"full_name": "Jane Doe"})
        assert resp.status_code == 200
        # Should render success template
        assert (
            b"Submission Received" in resp.content or b"dfw:submitted" in resp.content
        )
        # Verify submission was created (may be auto-approved if no workflow)
        assert FormSubmission.objects.filter(
            form_definition=embed_form,
        ).exists()

    def test_embed_submit_invalid(self, client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.post(url, {"full_name": ""})
        assert resp.status_code == 200
        # Should re-render form with errors
        assert b"attention" in resp.content or b"is-invalid" in resp.content
        assert not FormSubmission.objects.filter(form_definition=embed_form).exists()

    def test_embed_theme_param(self, client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url + "?theme=dark")
        assert resp.status_code == 200
        assert b'data-bs-theme="dark"' in resp.content

    def test_embed_accent_color_valid(self, client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url + "?accent_color=%23ff6600")
        assert resp.status_code == 200
        assert b"#ff6600" in resp.content

    def test_embed_accent_color_invalid_sanitised(self, client, embed_form):
        """CSS injection attempt is sanitised — invalid accent_color is dropped."""
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url + "?accent_color=red%3B+background-image%3A+url(evil)")
        assert resp.status_code == 200
        assert b"background-image" not in resp.content

    def test_embed_closed_form(self, client, embed_form):
        embed_form.close_date = timezone.now() - timedelta(hours=1)
        embed_form.save()
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"no longer accepting" in resp.content

    def test_embed_max_submissions_reached(self, client, embed_form, user):
        embed_form.max_submissions = 1
        embed_form.save()
        FormSubmission.objects.create(
            form_definition=embed_form,
            submitter=user,
            form_data={"full_name": "First"},
            status="submitted",
        )
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"maximum number" in resp.content

    def test_embed_authenticated_user(self, auth_client, embed_form):
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = auth_client.get(url)
        assert resp.status_code == 200

    def test_embed_creates_audit_log(self, client, embed_form):
        from django_forms_workflows.models import AuditLog

        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        client.post(url, {"full_name": "Audit Test"})
        assert AuditLog.objects.filter(
            action="submit", comments__contains="embed"
        ).exists()

    def test_embed_no_redirect_on_submit(self, client, embed_form):
        """Embed submissions render inline success, never redirect."""
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.post(url, {"full_name": "No Redirect"})
        # Should be 200 (rendered), not 302 (redirect)
        assert resp.status_code == 200

    def test_embed_success_message_piping(self, client, embed_form):
        embed_form.success_message = "Thanks {full_name}!"
        embed_form.save()
        url = reverse("forms_workflows:form_embed", args=[embed_form.slug])
        resp = client.post(url, {"full_name": "Alice"})
        assert resp.status_code == 200
        assert b"Thanks Alice!" in resp.content
