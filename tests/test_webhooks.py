import hashlib
import hmac
import json
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.exceptions import ValidationError

from django_forms_workflows import tasks as tasks_module
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


def _mock_response(status_code, body):
    response = Mock(status_code=status_code, encoding="utf-8")
    response.iter_content.return_value = [body.encode("utf-8")]
    return response


def test_synchronous_webhook_retry_fallback_returns_delay():
    fallback = Mock(spec=lambda **kwargs: None)
    with (
        patch.object(tasks_module, "deliver_workflow_webhook", fallback),
        patch("time.sleep") as sleep,
    ):
        delay = tasks_module._schedule_webhook_retry(
            endpoint_id=7,
            event="submission.created",
            payload={"event": "submission.created"},
            submission_id=11,
            task_id=None,
            attempt=3,
        )

    sleep.assert_not_called()
    fallback.assert_not_called()
    assert delay == 4


def test_webhook_retry_uses_iterative_fallback_when_enqueue_fails():
    task = Mock()
    task.apply_async.side_effect = RuntimeError("broker unavailable")
    with patch.object(tasks_module, "deliver_workflow_webhook", task):
        delay = tasks_module._schedule_webhook_retry(
            endpoint_id=7,
            event="submission.created",
            payload={},
            submission_id=11,
            task_id=None,
            attempt=3,
        )

    assert delay == 4
    task.assert_not_called()


def test_synchronous_webhook_retries_iteratively():
    with (
        patch.object(tasks_module, "deliver_workflow_webhook", Mock(spec=lambda: None)),
        patch.object(
            tasks_module,
            "_deliver_workflow_webhook_attempt",
            side_effect=[1] * 1100 + [None],
        ) as attempt,
        patch("django_forms_workflows.tasks.time.sleep") as sleep,
    ):
        deliver_workflow_webhook(7, "submission.created", {})

    assert attempt.call_count == 1101
    assert sleep.call_count == 1100


@pytest.mark.django_db
def test_synchronous_webhook_retries_with_backoff(workflow, user):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
        max_retries=2,
    )
    with (
        patch.object(tasks_module, "deliver_workflow_webhook", Mock(spec=lambda: None)),
        patch("django_forms_workflows.tasks.requests.request") as request,
        patch("django_forms_workflows.tasks.time.sleep") as sleep,
    ):
        request.side_effect = [
            _mock_response(503, "unavailable"),
            _mock_response(503, "unavailable"),
            _mock_response(200, "ok"),
        ]
        deliver_workflow_webhook(endpoint.id, "submission.created", {}, submission.id)

    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]
    assert request.call_count == 3
    assert list(
        WebhookDeliveryLog.objects.filter(endpoint=endpoint)
        .order_by("attempt_number")
        .values_list("success", flat=True)
    ) == [False, False, True]


@pytest.mark.django_db
def test_webhook_attempt_explicitly_finishes_when_endpoint_is_unavailable(workflow):
    assert (
        tasks_module._deliver_workflow_webhook_attempt(999999, "submission.created", {})
        is None
    )
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["task.created"],
    )
    assert (
        tasks_module._deliver_workflow_webhook_attempt(
            endpoint.id, "submission.created", {}
        )
        is None
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
    other_workflow = workflow.__class__.objects.create(
        form_definition=workflow.form_definition,
        name_label="Other track",
    )
    WebhookEndpoint.objects.create(
        workflow=other_workflow,
        name="Other Workflow Created Hook",
        url="https://example.com/hooks/other-created",
        events=["submission.created"],
        is_active=True,
    )

    with patch(
        "django_forms_workflows.tasks.deliver_workflow_webhook.delay"
    ) as mock_delay:
        dispatch_workflow_webhooks(
            submission.id, "submission.created", workflow_id=workflow.id
        )

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
def test_dispatch_ignores_task_from_another_submission(workflow, user, approval_group):
    submission = _make_submission(workflow, user)
    other_submission = _make_submission(workflow, user)
    WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Task Hook",
        url="https://example.com/hooks/task",
        events=["task.created"],
    )
    task = ApprovalTask.objects.create(
        submission=other_submission,
        assigned_group=approval_group,
        workflow_stage=workflow.stages.first(),
        step_name="Approval",
        status="pending",
    )

    with patch(
        "django_forms_workflows.tasks.deliver_workflow_webhook.delay"
    ) as mock_delay:
        dispatch_workflow_webhooks(submission.id, "task.created", task_id=task.id)

    mock_delay.assert_not_called()


@pytest.mark.django_db
def test_dispatch_ignores_stage_from_different_workflow(workflow, user):
    submission = _make_submission(workflow, user)
    other_workflow = workflow.form_definition.workflows.create(name_label="Other")
    other_stage = other_workflow.stages.create(name="Other stage", order=1)
    WebhookEndpoint.objects.create(
        workflow=workflow,
        name="Task Hook",
        url="https://example.com/hooks/task",
        events=["task.created"],
    )

    with patch(
        "django_forms_workflows.tasks.deliver_workflow_webhook.delay"
    ) as mock_delay:
        dispatch_workflow_webhooks(
            submission.id,
            "task.created",
            workflow_id=workflow.id,
            target_stage_id=other_stage.id,
        )

    mock_delay.assert_not_called()


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
    payload = {
        "event": "submission.created",
        "submission": {"id": submission.id, "title": "Café 🚀"},
    }

    with patch("django_forms_workflows.tasks.requests.request") as mock_request:
        mock_request.return_value = _mock_response(202, "accepted")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id
        )

    mock_request.assert_called_once()
    method, url = mock_request.call_args.args
    request_kwargs = mock_request.call_args.kwargs
    assert url == endpoint.url
    assert method.upper() == "POST"
    assert request_kwargs["stream"] is True
    mock_request.return_value.close.assert_called_once()
    headers = request_kwargs["headers"]
    assert headers["Authorization"] == "Bearer abc"
    if "data" in request_kwargs and request_kwargs["data"] is not None:
        body = request_kwargs["data"]
        if isinstance(body, str):
            body_text = body
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = body
            body_text = body.decode("utf-8")
        assert json.loads(body_text) == payload
    else:
        assert request_kwargs["json"] == payload
        body_bytes = json.dumps(request_kwargs["json"]).encode("utf-8")
    expected_signature = (
        "sha256="
        + hmac.new(
            endpoint.secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()
    )
    assert headers["X-Forms-Workflows-Signature"] == expected_signature

    log = WebhookDeliveryLog.objects.get()
    assert log.success is True
    assert log.status_code == 202
    assert log.response_body == "accepted"
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
        mock_request.return_value = _mock_response(500, "server error")
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


@pytest.mark.django_db
def test_deliver_workflow_webhook_retries_on_timeout(workflow, user):
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
        mock_request.side_effect = requests.Timeout("timed out")
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
    log = WebhookDeliveryLog.objects.get(endpoint=endpoint)
    assert log.success is False
    assert log.status_code is None


@pytest.mark.django_db
def test_deliver_workflow_webhook_does_not_retry_on_connection_error_at_max_retries(
    workflow, user
):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
        max_retries=1,
    )
    payload = {"event": "submission.created", "submission": {"id": submission.id}}

    with (
        patch("django_forms_workflows.tasks.requests.request") as mock_request,
        patch("django_forms_workflows.tasks._schedule_webhook_retry") as mock_retry,
    ):
        mock_request.side_effect = requests.ConnectionError("connection failed")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id, attempt=2
        )

    mock_retry.assert_not_called()
    log = WebhookDeliveryLog.objects.get(endpoint=endpoint)
    assert log.success is False
    assert log.status_code is None


@pytest.mark.django_db
def test_deliver_workflow_webhook_retries_failed_delivery_at_max_retry_boundary(
    workflow, user
):
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
        mock_request.return_value = _mock_response(500, "server error")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id, attempt=2
        )

    mock_retry.assert_called_once_with(
        endpoint_id=endpoint.id,
        event="submission.created",
        payload=payload,
        submission_id=submission.id,
        task_id=None,
        attempt=3,
    )
    log = WebhookDeliveryLog.objects.get()
    assert log.success is False
    assert log.status_code == 500


@pytest.mark.django_db
def test_deliver_workflow_webhook_does_not_retry_when_retries_exhausted(workflow, user):
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
        mock_request.return_value = _mock_response(500, "server error")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id, attempt=3
        )

    mock_retry.assert_not_called()
    log = WebhookDeliveryLog.objects.get()
    assert log.success is False
    assert log.status_code == 500


@pytest.mark.django_db
def test_deliver_workflow_webhook_with_zero_max_retries_does_not_retry(workflow, user):
    submission = _make_submission(workflow, user)
    endpoint = WebhookEndpoint.objects.create(
        workflow=workflow,
        name="ERP",
        url="https://example.com/hooks/erp",
        events=["submission.created"],
        max_retries=0,
    )
    payload = {"event": "submission.created", "submission": {"id": submission.id}}

    with (
        patch("django_forms_workflows.tasks.requests.request") as mock_request,
        patch("django_forms_workflows.tasks._schedule_webhook_retry") as mock_retry,
    ):
        mock_request.return_value = _mock_response(500, "server error")
        deliver_workflow_webhook(
            endpoint.id, "submission.created", payload, submission.id
        )

    mock_retry.assert_not_called()
    log = WebhookDeliveryLog.objects.get()
    assert log.success is False
    assert log.status_code == 500
