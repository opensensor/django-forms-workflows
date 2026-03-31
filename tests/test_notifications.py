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
