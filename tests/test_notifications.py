from unittest.mock import patch

import pytest

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
    WorkflowDefinition,
    WorkflowNotification,
    WorkflowStage,
)
from django_forms_workflows.tasks import send_workflow_definition_notifications


@pytest.mark.parametrize(
    "notification_type,task_status",
    [
        ("approval_notification", "approved"),
        ("rejection_notification", "rejected"),
    ],
)
def test_final_decision_notifications_include_dynamic_assignee(
    notification_type,
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
        notify_assignee_on_final_decision=True,
    )
    WorkflowNotification.objects.create(
        workflow=workflow,
        notification_type=notification_type,
        notify_submitter=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="approved"
        if notification_type == "approval_notification"
        else "rejected",
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
        send_workflow_definition_notifications(submission.id, notification_type)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert recipients == [user.email, approver_user.email]
