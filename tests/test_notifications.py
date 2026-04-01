from unittest.mock import patch

import pytest

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
    NotificationRule,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.tasks import send_notification_rules


@pytest.mark.parametrize(
    "event,task_status",
    [
        ("workflow_approved", "approved"),
        ("workflow_denied", "rejected"),
    ],
)
def test_final_decision_notifications_include_dynamic_assignee(
    event,
    task_status,
    form_definition,
    user,
    approver_user,
):
    workflow = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=True,
    )
    stage = WorkflowStage.objects.create(
        workflow=workflow,
        name="Advisor Review",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=workflow,
        event=event,
        notify_submitter=True,
        notify_stage_assignees=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="approved" if event == "workflow_approved" else "rejected",
    )
    ApprovalTask.objects.create(
        submission=submission,
        step_name="Advisor Review",
        status=task_status,
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, event)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert recipients == [user.email, approver_user.email]


# ── Answer piping in notification subjects ─────────────────────────────────


def _make_workflow_with_rule(form_definition, event="workflow_approved", **rule_kwargs):
    """Helper: creates a WorkflowDefinition + NotificationRule for tests."""
    workflow = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=False,
    )
    rule = NotificationRule.objects.create(
        workflow=workflow,
        event=event,
        notify_submitter=True,
        **rule_kwargs,
    )
    return workflow, rule


def test_notification_subject_pipes_form_data_field(form_definition, user):
    """A {field_name} token in subject_template is replaced from form_data."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Application from {full_name} received",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"full_name": "Alice Smith"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    assert mock_send.called
    subject = mock_send.call_args[0][0]
    assert "Alice Smith" in subject


def test_notification_subject_unknown_field_becomes_empty(form_definition, user):
    """An unrecognised {token} is replaced with an empty string (defaultdict)."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Hi {ghost_field}, your form is done",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"full_name": "Bob"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    # {ghost_field} → "" so the subject should not contain a literal brace token
    assert "{ghost_field}" not in subject
    assert "Hi " in subject


def test_notification_subject_builtin_placeholders_still_work(form_definition, user):
    """{form_name} and {submission_id} continue to resolve as before."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="{form_name} submission #{submission_id} approved",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    assert form_definition.name in subject
    assert str(submission.id) in subject


def test_notification_subject_list_field_comma_joined(form_definition, user):
    """List-valued form fields are joined with ', ' in the subject."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Courses: {courses}",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"courses": ["Math", "Science", "History"]},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    assert "Math, Science, History" in subject


def test_notification_context_includes_form_data(form_definition, user):
    """form_data is passed into the email template context."""
    _make_workflow_with_rule(form_definition)
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"dept": "Engineering"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    context = mock_send.call_args[0][3]  # 4th positional arg is the context dict
    assert "form_data" in context
    assert context["form_data"]["dept"] == "Engineering"
