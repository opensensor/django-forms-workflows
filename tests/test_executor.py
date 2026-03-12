"""
Tests for PostSubmissionActionExecutor.
"""

from unittest.mock import patch

from django_forms_workflows.handlers.executor import PostSubmissionActionExecutor
from django_forms_workflows.models import (
    ActionExecutionLog,
    FormSubmission,
    PostSubmissionAction,
)


class TestExecutorNoActions:
    def test_returns_zero_summary(self, form_definition, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        executor = PostSubmissionActionExecutor(sub, "on_approve")
        result = executor.execute_all()
        assert result["executed"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0


class TestExecutorConditionalSkip:
    def test_skips_when_condition_not_met(self, form_definition, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"department": "it"},
            status="submitted",
        )
        PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="HR Only Email",
            action_type="email",
            trigger="on_approve",
            condition_field="department",
            condition_operator="equals",
            condition_value="hr",
            email_to="hr@example.com",
        )
        executor = PostSubmissionActionExecutor(sub, "on_approve")
        result = executor.execute_all()
        assert result["skipped"] == 1
        assert result["executed"] == 0


class TestExecutorEmailAction:
    @patch("django_forms_workflows.handlers.email_handler.EmailHandler.execute")
    def test_email_action_success(self, mock_execute, form_definition, user):
        mock_execute.return_value = {
            "success": True,
            "message": "Email sent",
        }
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"full_name": "Test User"},
            status="approved",
        )
        PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Approval Email",
            action_type="email",
            trigger="on_approve",
            email_to="admin@example.com",
            email_subject_template="Approved: {form_name}",
            email_body_template="Approved by {submitter}.",
        )
        executor = PostSubmissionActionExecutor(sub, "on_approve")
        result = executor.execute_all()
        assert result["succeeded"] == 1
        mock_execute.assert_called_once()

    @patch("django_forms_workflows.handlers.email_handler.EmailHandler.execute")
    def test_email_action_retry(self, mock_execute, form_definition, user):
        mock_execute.side_effect = [
            {"success": False, "message": "Timeout"},
            {"success": True, "message": "Email sent"},
        ]
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="approved",
        )
        PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Retry Email",
            action_type="email",
            trigger="on_approve",
            email_to="admin@example.com",
            retry_on_failure=True,
            max_retries=2,
        )
        executor = PostSubmissionActionExecutor(sub, "on_approve")
        result = executor.execute_all()
        assert result["succeeded"] == 1
        assert mock_execute.call_count == 2


class TestExecutorLockedAction:
    @patch("django_forms_workflows.handlers.email_handler.EmailHandler.execute")
    def test_locked_action_skips_after_first_success(
        self, mock_execute, form_definition, user
    ):
        mock_execute.return_value = {"success": True, "message": "OK"}
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="approved",
        )
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Once Only",
            action_type="email",
            trigger="on_approve",
            is_locked=True,
            email_to="admin@example.com",
        )
        # First execution succeeds
        executor1 = PostSubmissionActionExecutor(sub, "on_approve")
        r1 = executor1.execute_all()
        assert r1["succeeded"] == 1
        # Second execution should be skipped (already ran and logged)
        ActionExecutionLog.objects.create(
            action=action, submission=sub, trigger="on_approve", success=True
        )
        executor2 = PostSubmissionActionExecutor(sub, "on_approve")
        r2 = executor2.execute_all()
        assert r2["skipped"] == 1


class TestExecutorCustomHandler:
    def test_unknown_action_type_no_handler(self, form_definition, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="approved",
        )
        PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Unknown Type",
            action_type="unknown_xyz",
            trigger="on_approve",
        )
        executor = PostSubmissionActionExecutor(sub, "on_approve")
        result = executor.execute_all()
        assert result["failed"] == 1
