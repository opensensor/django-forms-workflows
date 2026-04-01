from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
    WebhookDeliveryLog,
    WebhookEndpoint,
)
from django_forms_workflows.tasks import (
    deliver_workflow_webhook,
    dispatch_workflow_webhooks,
)


def _make_submission(workflow, user):
    return FormSubmission.objects.create(
        form_definition=workflow.form_definition,
        submitter=user,
        form_data={"field": "value"},
        status="submitted",
    )


@pytest.mark.django_db
def test_webhook_endpoint_generates_secret_and_validates_events(workflow):
    endpoint = WebhookEndpoint(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
    )

    endpoint.full_clean()
    endpoint.save()

    assert endpoint.secret

    invalid = WebhookEndpoint(
        workflow=workflow,
        name="Bad",
        url="https://example.com/hooks/bad",
        events=["not-a-real-event"],
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()


@pytest.mark.django_db
def test_dispatch_workflow_webhooks_enqueues_matching_endpoints(workflow, user):
    submission = _make_submission(workflow, user)
    matching = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Created Hook",
        url="https://example.com/hooks/created",
        events=["submission.created"],
    )
    WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Task Hook",
        url="https://example.com/hooks/task",
        events=["task.created"],
    )
    WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Inactive Hook",
        url="https://example.com/hooks/inactive",
        events=["submission.created"],
        is_active=False,
    )

    with patch(
        "django_forms_workflows.tasks.deliver_workflow_webhook.delay"
    ) as mock_delay:
        dispatch_workflow_webhooks(submission.id, "submission.created")

    mock_delay.assert_called_once()
    endpoint_id, event, payload, submission_id, task_id, attempt = (
        mock_delay.call_args.args
    )
    assert endpoint_id == matching.id
    assert event == "submission.created"
    assert submission_id == submission.id
    assert task_id is None
    assert attempt == 1
    assert payload["form"]["slug"] == workflow.form_definition.slug
    assert payload["workflow"]["id"] == workflow.id


@pytest.mark.django_db
def test_dispatch_workflow_webhooks_loads_task_context_for_task_created(
    workflow, user, approval_group
):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Task Hook",
        url="https://example.com/hooks/task",
        events=["task.created"],
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        assigned_group=approval_group,
        workflow_stage=workflow.stages.first(),
        stage_number=1,
        step_name="Approval",
        status="approved",
        completed_by=user,
    )

    with patch(
        "django_forms_workflows.tasks.deliver_workflow_webhook.delay"
    ) as mock_delay:
        dispatch_workflow_webhooks(
            submission.id,
            "task.created",
            task_id=task.id,
            workflow_id=workflow.id,
        )

    mock_delay.assert_called_once()
    endpoint_id, event, payload, submission_id, task_id, attempt = (
        mock_delay.call_args.args
    )
    assert endpoint_id == endpoint.id
    assert event == "task.created"
    assert submission_id == submission.id
    assert task_id == task.id
    assert attempt == 1
    assert payload["task"]["id"] == task.id
    assert payload["task"]["workflow_stage"]["id"] == task.workflow_stage_id
    assert payload["task"]["approved_by"]["id"] == user.id


@pytest.mark.django_db
def test_deliver_workflow_webhook_signs_request_and_logs_success(workflow, user):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
        custom_headers={"Authorization": "Bearer abc"},
    )
    payload = {"event": "submission.created", "submission": {"id": submission.id}}

    with patch("django_forms_workflows.tasks.requests.request") as mock_request:
        mock_request.return_value = Mock(status_code=202, text="accepted")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id
        )

    headers = mock_request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer abc"
    assert headers["X-Forms-Workflows-Signature"].startswith("sha256=")

    log = WebhookDeliveryLog.objects.get()
    assert log.success is True
    assert log.status_code == 202
    assert log.endpoint_name == "ERP"


@pytest.mark.django_db
def test_deliver_workflow_webhook_retries_failed_delivery(workflow, user):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
        max_retries=2,
    )
    payload = {"event": "submission.created", "submission": {"id": submission.id}}

    with (
        patch("django_forms_workflows.tasks.requests.request") as mock_request,
        patch("django_forms_workflows.tasks._schedule_webhook_retry") as mock_retry,
    ):
        mock_request.return_value = Mock(status_code=500, text="server error")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id
        )

    mock_retry.assert_called_once_with(
        endpoint_id=endpoint.id,
        event="submission.created",
        payload=payload,
        submission_id=submission.id,
        task_id=None,
        attempt=2,
    )
    log = WebhookDeliveryLog.objects.get()
    assert log.success is False
    assert log.status_code == 500
