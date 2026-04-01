"""
Celery-friendly email tasks for Django Forms Workflows.

- Uses Celery if available (shared_task). If Celery isn't installed/running,
  tasks still import and `.delay(...)` will call synchronously as a graceful fallback.
- Emails use the package's generic templates under django_forms_workflows/templates/emails/.
- Absolute URLs are built from settings.FORMS_WORKFLOWS_BASE_URL (or SITE_BASE_URL) if set;
  otherwise fall back to relative paths.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from calendar import monthrange
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from datetime import time as dt_time

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from .models import (
    ApprovalTask,
    FormSubmission,
    NotificationLog,
    NotificationRule,
    PendingNotification,
    WebhookDeliveryLog,
    WebhookEndpoint,
    WorkflowStage,
)

logger = logging.getLogger(__name__)

# Provide a no-op shared_task decorator if Celery isn't installed
try:  # pragma: no cover
    from celery import shared_task  # type: ignore
except Exception:  # pragma: no cover

    def shared_task(*dargs, **dkwargs):  # type: ignore
        def _decorator(fn):
            def _wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            # mimic celery Task API for `.delay`
            _wrapper.delay = _wrapper  # type: ignore[attr-defined]
            return _wrapper

        return _decorator


def _base_url() -> str:
    """Return the base URL (scheme + domain) for building absolute links in emails.

    Checks, in order:
    1. ``settings.FORMS_WORKFLOWS_BASE_URL``
    2. ``settings.SITE_BASE_URL``
    3. First entry in ``settings.CSRF_TRUSTED_ORIGINS``
    """
    url = getattr(settings, "FORMS_WORKFLOWS_BASE_URL", None) or getattr(
        settings, "SITE_BASE_URL", None
    )
    if url:
        return url
    origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", None)
    if origins:
        return origins[0]
    return ""


def _abs(url_path: str) -> str:
    base = _base_url().rstrip("/")
    if base:
        return f"{base}{url_path}"
    return url_path  # relative fallback


def _site_name() -> str:
    """Return the configured site name, defaulting to 'Django Forms Workflows'."""
    cfg = getattr(settings, "FORMS_WORKFLOWS", {})
    return cfg.get("SITE_NAME", "Django Forms Workflows")


def _send_html_email(
    subject: str,
    to: Iterable[str],
    template: str,
    context: dict,
    from_email: str | None = None,
    *,
    notification_type: str = "other",
    submission_id: int | None = None,
) -> None:
    to_list = [e for e in to if e]
    if not to_list:
        logger.info("Skipping email '%s' (no recipients)", subject)
        _write_notification_log(
            notification_type=notification_type,
            submission_id=submission_id,
            recipient_email="(none)",
            subject=subject,
            status="skipped",
        )
        return

    # Inject site_name so all email templates can reference {{ site_name }}
    context.setdefault("site_name", _site_name())

    html_body = render_to_string(template, context)
    text_body = strip_tags(html_body)
    from_addr = from_email or getattr(
        settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost"
    )

    msg = EmailMultiAlternatives(
        subject=subject, body=text_body, from_email=from_addr, to=to_list
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=False)
        logger.info("Sent email '%s' to %s", subject, to_list)
        for recipient in to_list:
            _write_notification_log(
                notification_type=notification_type,
                submission_id=submission_id,
                recipient_email=recipient,
                subject=subject,
                status="sent",
            )
    except Exception as e:  # pragma: no cover
        logger.exception("Failed sending email '%s' to %s: %s", subject, to_list, e)
        for recipient in to_list:
            _write_notification_log(
                notification_type=notification_type,
                submission_id=submission_id,
                recipient_email=recipient,
                subject=subject,
                status="failed",
                error_message=str(e),
            )


def _write_notification_log(
    *,
    notification_type: str,
    submission_id: int | None,
    recipient_email: str,
    subject: str,
    status: str,
    error_message: str = "",
) -> None:
    """Write a NotificationLog row; never raises so it cannot break email delivery."""
    try:
        NotificationLog.objects.create(
            notification_type=notification_type,
            submission_id=submission_id,
            recipient_email=recipient_email,
            subject=subject,
            status=status,
            error_message=error_message,
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to write NotificationLog (ignored)")


def _serialize_webhook_user(user) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.get_username(),
        "email": getattr(user, "email", ""),
        "full_name": getattr(user, "get_full_name", lambda: "")(),
    }


def _serialize_webhook_stage(stage: WorkflowStage | None) -> dict | None:
    if not stage:
        return None
    return {
        "id": stage.id,
        "name": stage.name,
        "order": stage.order,
    }


def _build_webhook_payload(
    submission: FormSubmission,
    event: str,
    *,
    workflow=None,
    approval_task: ApprovalTask | None = None,
    target_stage: WorkflowStage | None = None,
) -> dict:
    workflow_obj = workflow
    if workflow_obj is None and approval_task and approval_task.workflow_stage_id:
        workflow_obj = approval_task.workflow_stage.workflow
    if workflow_obj is None and target_stage is not None:
        workflow_obj = target_stage.workflow

    payload = {
        "event": event,
        "timestamp": timezone.now().isoformat(),
        "submission": {
            "id": submission.id,
            "status": submission.status,
            "created_at": submission.created_at.isoformat()
            if submission.created_at
            else None,
            "submitted_at": submission.submitted_at.isoformat()
            if submission.submitted_at
            else None,
            "completed_at": submission.completed_at.isoformat()
            if submission.completed_at
            else None,
        },
        "form": {
            "id": submission.form_definition_id,
            "name": submission.form_definition.name,
            "slug": submission.form_definition.slug,
        },
        "submitter": _serialize_webhook_user(submission.submitter),
        "workflow": None,
        "task": None,
        "target_stage": _serialize_webhook_stage(target_stage),
    }

    if workflow_obj is not None:
        payload["workflow"] = {
            "id": workflow_obj.id,
            "name_label": workflow_obj.name_label,
            "requires_approval": workflow_obj.requires_approval,
        }

    if approval_task is not None:
        payload["task"] = {
            "id": approval_task.id,
            "status": approval_task.status,
            "stage_number": approval_task.stage_number,
            "step_name": approval_task.step_name,
            "assigned_to": _serialize_webhook_user(approval_task.assigned_to),
            "assigned_group": (
                {
                    "id": approval_task.assigned_group.id,
                    "name": approval_task.assigned_group.name,
                }
                if approval_task.assigned_group_id
                else None
            ),
            "workflow_stage": _serialize_webhook_stage(approval_task.workflow_stage),
            "approved_by": _serialize_webhook_user(approval_task.completed_by),
        }

    return payload


def _sign_webhook_payload(secret: str, payload_text: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _schedule_webhook_retry(
    *,
    endpoint_id: int,
    event: str,
    payload: dict,
    submission_id: int | None,
    task_id: int | None,
    attempt: int,
) -> None:
    countdown = min(300, 2 ** max(0, attempt - 1))
    kwargs = {
        "endpoint_id": endpoint_id,
        "event": event,
        "payload": payload,
        "submission_id": submission_id,
        "task_id": task_id,
        "attempt": attempt,
    }
    if hasattr(deliver_workflow_webhook, "apply_async"):
        deliver_workflow_webhook.apply_async(kwargs=kwargs, countdown=countdown)
    else:  # pragma: no cover
        logger.warning(
            "Celery apply_async unavailable; retrying webhook %s synchronously",
            endpoint_id,
        )
        deliver_workflow_webhook(**kwargs)


@shared_task(name="django_forms_workflows.dispatch_workflow_webhooks")
def dispatch_workflow_webhooks(
    submission_id: int,
    event: str,
    task_id: int | None = None,
    workflow_id: int | None = None,
    target_stage_id: int | None = None,
) -> None:
    submission = FormSubmission.objects.select_related(
        "form_definition", "submitter"
    ).get(id=submission_id)
    approval_task = None
    if task_id is not None:
        approval_task = ApprovalTask.objects.select_related(
            "assigned_to",
            "assigned_group",
            "completed_by",
            "workflow_stage__workflow",
        ).get(id=task_id)
    target_stage = None
    if target_stage_id is not None:
        target_stage = WorkflowStage.objects.select_related("workflow").get(
            id=target_stage_id
        )

    if workflow_id is not None:
        workflow_ids = [workflow_id]
    elif approval_task is not None and approval_task.workflow_stage_id:
        workflow_ids = [approval_task.workflow_stage.workflow_id]
    elif target_stage is not None:
        workflow_ids = [target_stage.workflow_id]
    else:
        workflow_ids = list(
            submission.form_definition.workflows.values_list("id", flat=True)
        )

    if not workflow_ids:
        return

    endpoints = WebhookEndpoint.objects.select_related(
        "workflow", "workflow__form_definition"
    ).filter(workflow_id__in=workflow_ids, is_active=True)
    for endpoint in endpoints:
        if not endpoint.subscribes_to(event):
            continue
        payload = _build_webhook_payload(
            submission,
            event,
            workflow=endpoint.workflow,
            approval_task=approval_task,
            target_stage=target_stage,
        )
        try:
            deliver_workflow_webhook.delay(
                endpoint.id,
                event,
                payload,
                submission.id,
                approval_task.id if approval_task else None,
                1,
            )
        except Exception:  # pragma: no cover
            logger.warning(
                "Webhook delivery fell back to synchronous execution for endpoint %s",
                endpoint.id,
            )
            deliver_workflow_webhook(
                endpoint.id,
                event,
                payload,
                submission.id,
                approval_task.id if approval_task else None,
                1,
            )


@shared_task(name="django_forms_workflows.deliver_workflow_webhook")
def deliver_workflow_webhook(
    endpoint_id: int,
    event: str,
    payload: dict,
    submission_id: int | None = None,
    task_id: int | None = None,
    attempt: int = 1,
) -> None:
    try:
        endpoint = WebhookEndpoint.objects.select_related("workflow").get(
            id=endpoint_id
        )
    except WebhookEndpoint.DoesNotExist:
        logger.warning(
            "Webhook endpoint %s no longer exists; skipping delivery", endpoint_id
        )
        return

    if not endpoint.subscribes_to(event):
        return

    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "django-forms-workflows/webhooks",
        "X-Forms-Workflows-Event": event,
    }
    if endpoint.custom_headers:
        request_headers.update(
            {str(k): str(v) for k, v in endpoint.custom_headers.items()}
        )

    payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    request_headers["X-Forms-Workflows-Signature"] = _sign_webhook_payload(
        endpoint.secret,
        payload_text,
    )

    log_data = {
        "endpoint": endpoint,
        "workflow": endpoint.workflow,
        "submission_id": submission_id,
        "approval_task_id": task_id,
        "event": event,
        "endpoint_name": endpoint.name,
        "delivery_url": endpoint.url,
        "attempt_number": attempt,
        "request_headers": request_headers,
        "payload": payload,
    }
    max_attempts = 1 + max(0, endpoint.max_retries)

    try:
        response = requests.request(
            "POST",
            endpoint.url,
            data=payload_text,
            headers=request_headers,
            timeout=endpoint.timeout_seconds,
        )
        success = 200 <= response.status_code < 300
        WebhookDeliveryLog.objects.create(
            success=success,
            status_code=response.status_code,
            response_body=(response.text or "")[:5000],
            error_message="" if success else f"HTTP {response.status_code}",
            **log_data,
        )
        if not success and endpoint.retry_on_failure and attempt < max_attempts:
            _schedule_webhook_retry(
                endpoint_id=endpoint.id,
                event=event,
                payload=payload,
                submission_id=submission_id,
                task_id=task_id,
                attempt=attempt + 1,
            )
    except Exception as exc:  # pragma: no cover
        WebhookDeliveryLog.objects.create(
            success=False,
            error_message=str(exc),
            **log_data,
        )
        if endpoint.retry_on_failure and attempt < max_attempts:
            _schedule_webhook_retry(
                endpoint_id=endpoint.id,
                event=event,
                payload=payload,
                submission_id=submission_id,
                task_id=task_id,
                attempt=attempt + 1,
            )


# ---------------------------------------------------------------------------
# Notification Batching Helpers
# ---------------------------------------------------------------------------


def _compute_scheduled_for(workflow, submission=None):
    """
    Return a timezone-aware datetime indicating when the next batch for the
    given workflow should go out, based on its notification_cadence setting.
    """
    now = timezone.now()
    raw_time = getattr(workflow, "notification_cadence_time", None) or dt_time(8, 0)
    cadence = getattr(workflow, "notification_cadence", "immediate")

    def _at_time(base_dt):
        """Replace h/m on *base_dt* (already tz-aware) with the send time."""
        return base_dt.replace(
            hour=raw_time.hour, minute=raw_time.minute, second=0, microsecond=0
        )

    if cadence == "daily":
        candidate = _at_time(now)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if cadence == "weekly":
        target_dow = getattr(workflow, "notification_cadence_day", None) or 0  # 0=Mon
        days_ahead = (target_dow - now.weekday()) % 7
        candidate = _at_time(now + timedelta(days=days_ahead))
        if days_ahead == 0 and candidate <= now:
            candidate += timedelta(weeks=1)
        return candidate

    if cadence == "monthly":
        target_day = getattr(workflow, "notification_cadence_day", None) or 1
        year, month = now.year, now.month
        actual_day = min(target_day, monthrange(year, month)[1])
        candidate = _at_time(now.replace(day=actual_day))
        if candidate <= now:
            month += 1
            if month > 12:
                year, month = year + 1, 1
            actual_day = min(target_day, monthrange(year, month)[1])
            candidate = _at_time(now.replace(year=year, month=month, day=actual_day))
        return candidate

    if cadence == "form_field_date" and submission is not None:
        field_name = getattr(workflow, "notification_cadence_form_field", "")
        form_data = getattr(submission, "form_data", None) or {}
        date_str = form_data.get(field_name, "")
        if date_str:
            try:
                parsed = datetime.fromisoformat(str(date_str)).date()
                candidate = timezone.make_aware(datetime.combine(parsed, raw_time))
                if candidate > now:
                    return candidate
            except (ValueError, TypeError):
                logger.debug(
                    "Could not parse date string %r for reminder schedule", date_str
                )
        # Fallback: send tomorrow
        return _at_time(now + timedelta(days=1))

    # Fallback for unknown cadences
    return _at_time(now + timedelta(days=1))


@shared_task(name="django_forms_workflows.send_approval_request")
def send_approval_request(task_id: int) -> None:
    """Request approval from the assigned approver for a task.
    - If assigned_to is set, email that user.
    - If assigned_group is set, email all users in the group.
    """
    task = ApprovalTask.objects.select_related(
        "submission__form_definition",
        "submission__submitter",
        "assigned_to",
        "assigned_group",
        "workflow_stage",
    ).get(id=task_id)
    approval_url = _abs(reverse("forms_workflows:approve_submission", args=[task.id]))
    subject = f"Approval Request: {task.submission.form_definition.name} (ID {task.submission.id})"
    template = "emails/approval_request.html"

    # Build stage / parallel context so email templates can show progress info
    stage_context: dict = {}
    if task.workflow_stage:
        stage = task.workflow_stage
        workflow = getattr(task.submission.form_definition, "workflow", None)
        total_stages = workflow.stages.count() if workflow else 1
        # Count sibling tasks in the same stage
        sibling_tasks = task.submission.approval_tasks.filter(
            workflow_stage=stage
        ).count()
        stage_context = {
            "stage_name": stage.name,
            "stage_number": task.stage_number or 1,
            "total_stages": total_stages,
            "stage_approval_logic": stage.approval_logic,
            "stage_total_approvers": sibling_tasks,
        }
    elif task.step_number:
        # Legacy sequential tasks (pre-staged)
        stage_context = {
            "stage_number": task.step_number,
            "total_stages": task.step_number,
            "stage_approval_logic": "sequence",
            "stage_total_approvers": 1,
        }

    def _build_context(approver):
        ctx = {
            "task": task,
            "submission": task.submission,
            "approver": approver,
            "approval_url": approval_url,
        }
        ctx.update(stage_context)
        return ctx

    if task.assigned_to and getattr(task.assigned_to, "email", None):
        _send_html_email(
            subject,
            [task.assigned_to.email],
            template,
            _build_context(task.assigned_to),
            notification_type="approval_request",
            submission_id=task.submission_id,
        )
        return

    if task.assigned_group:
        recipients = []
        for user in task.assigned_group.user_set.all():
            email = getattr(user, "email", None)
            if not email:
                continue
            _send_html_email(
                subject,
                [email],
                template,
                _build_context(user),
                notification_type="approval_request",
                submission_id=task.submission_id,
            )
            recipients.append(email)
        if not recipients:
            logger.info(
                "Group %s has no users with email to notify for task %s",
                task.assigned_group,
                task.id,
            )
        return

    logger.info("No assigned user or group to notify for task %s", task_id)


@shared_task(name="django_forms_workflows.send_approval_reminder")
def send_approval_reminder(task_id: int) -> None:
    task = ApprovalTask.objects.select_related(
        "submission__form_definition", "assigned_to"
    ).get(id=task_id)
    if not task.assigned_to or not getattr(task.assigned_to, "email", None):
        return
    approval_url = _abs(reverse("forms_workflows:approve_submission", args=[task.id]))
    context = {
        "task": task,
        "submission": task.submission,
        "approver": task.assigned_to,
        "approval_url": approval_url,
    }
    subject = f"Reminder: Approval Pending for {task.submission.form_definition.name} (ID {task.submission.id})"
    _send_html_email(
        subject,
        [task.assigned_to.email],
        "emails/approval_reminder.html",
        context,
        notification_type="approval_reminder",
        submission_id=task.submission_id,
    )


@shared_task(name="django_forms_workflows.check_approval_deadlines")
def check_approval_deadlines() -> str:
    """Periodic task to send reminders, expire tasks, and optionally auto-approve.

    This operates purely on configured workflow timeouts and does not create audit log entries
    (no user context available).
    """
    now = timezone.now()
    pending = ApprovalTask.objects.select_related("submission__form_definition").filter(
        status="pending"
    )

    expired_count = 0
    reminder_count = 0
    auto_approved_count = 0

    for task in pending:
        submission = task.submission
        workflow = getattr(submission.form_definition, "workflow", None)
        if not workflow:
            continue

        # Expire tasks after deadline
        if workflow.approval_deadline_days and task.created_at:
            deadline = task.created_at + timedelta(days=workflow.approval_deadline_days)
            if now > deadline:
                task.status = "expired"
                task.save(update_fields=["status"])  # mark expired
                expired_count += 1

                # Escalation groups have been removed.
                # Escalation should now be modelled as conditional stages.

                # Optional auto-approve after grace period
                if (
                    workflow.auto_approve_after_days
                    and submission.status == "pending_approval"
                ):
                    auto_deadline = task.created_at + timedelta(
                        days=workflow.auto_approve_after_days
                    )
                    if now > auto_deadline:
                        submission.status = "approved"
                        submission.completed_at = now
                        submission.save(update_fields=["status", "completed_at"])
                        # cancel remaining tasks
                        submission.approval_tasks.filter(status="pending").update(
                            status="skipped"
                        )
                        try:
                            send_notification_rules.delay(
                                submission.id, "workflow_approved"
                            )
                        except Exception:
                            logger.debug(
                                "Could not enqueue approval notification for submission %s",
                                submission.id,
                                exc_info=True,
                            )
                        auto_approved_count += 1

        # Send reminder if configured and not yet sent
        if (
            workflow.send_reminder_after_days
            and task.created_at
            and task.status == "pending"
            and not task.reminder_sent_at
        ):
            reminder_time = task.created_at + timedelta(
                days=workflow.send_reminder_after_days
            )
            if now > reminder_time:
                try:
                    send_approval_reminder.delay(task.id)
                except Exception:
                    logger.debug(
                        "Could not enqueue send_approval_reminder for task %s",
                        task.id,
                        exc_info=True,
                    )
                task.reminder_sent_at = now
                task.save(update_fields=["reminder_sent_at"])
                reminder_count += 1

    return f"expired={expired_count}, reminders={reminder_count}, auto_approved={auto_approved_count}"


@shared_task(name="django_forms_workflows.send_escalation_notification")
def send_escalation_notification(task_id: int, to_email: str | None = None) -> None:
    task = ApprovalTask.objects.select_related(
        "submission__form_definition", "assigned_to"
    ).get(id=task_id)
    recipient = to_email or getattr(getattr(task, "assigned_to", None), "email", None)
    if not recipient:
        return
    submission_url = _abs(
        reverse("forms_workflows:submission_detail", args=[task.submission.id])
    )
    context = {
        "task": task,
        "submission": task.submission,
        "submission_url": submission_url,
    }
    subject = (
        f"Escalation: {task.submission.form_definition.name} (ID {task.submission.id})"
    )
    _send_html_email(
        subject,
        [recipient],
        "emails/escalation_notification.html",
        context,
        notification_type="escalation",
        submission_id=task.submission_id,
    )


# ---------------------------------------------------------------------------
# Batched Notification Dispatch
# ---------------------------------------------------------------------------


@shared_task(name="django_forms_workflows.send_batched_notifications")
def send_batched_notifications() -> str:
    """
    Periodic task: find all PendingNotification records that are due and send
    one digest email per (recipient, notification_type, workflow) group.

    Schedule this via Celery Beat, e.g. every hour, so batches are dispatched
    promptly once their scheduled_for time has passed.
    """
    now = timezone.now()
    due_qs = (
        PendingNotification.objects.filter(sent=False, scheduled_for__lte=now)
        .select_related(
            "workflow__form_definition",
            "submission__form_definition",
            "submission__submitter",
            "approval_task",
        )
        .order_by("recipient_email", "notification_type", "workflow_id")
    )

    groups: dict[tuple, list] = defaultdict(list)
    for pn in due_qs:
        key = (pn.recipient_email, pn.notification_type, pn.workflow_id)
        groups[key].append(pn)

    sent_count = 0
    for (
        recipient_email,
        notification_type,
        _workflow_id,
    ), notifications in groups.items():
        try:
            if notification_type == "submission_received":
                _dispatch_submission_digest(recipient_email, notifications)
            elif notification_type == "approval_request":
                _dispatch_approval_digest(recipient_email, notifications)
            elif notification_type in (
                "approval_notification",
                "rejection_notification",
                "withdrawal_notification",
            ):
                _dispatch_conclusion_digest(
                    recipient_email, notifications, notification_type
                )
            else:
                logger.warning(
                    "send_batched_notifications: unknown type %r for %s; skipping.",
                    notification_type,
                    recipient_email,
                )
                continue
            ids = [n.id for n in notifications]
            PendingNotification.objects.filter(id__in=ids).update(sent=True)
            sent_count += len(ids)
        except Exception as exc:
            logger.exception(
                "Failed dispatching batched %s digest to %s: %s",
                notification_type,
                recipient_email,
                exc,
            )

    return f"sent={sent_count}"


def _dispatch_submission_digest(recipient_email: str, notifications: list) -> None:
    """Send a digest of submission_received notifications to one recipient."""
    sample = notifications[0]
    workflow = sample.workflow
    form_name = workflow.form_definition.name
    count = len(notifications)
    submissions = [
        {
            "submission": n.submission,
            "submission_url": _abs(
                reverse("forms_workflows:submission_detail", args=[n.submission.id])
            ),
        }
        for n in notifications
        if n.submission
    ]
    subject = (
        f"{count} new submission{'s' if count != 1 else ''} received — {form_name}"
    )
    context = {
        "form_name": form_name,
        "count": count,
        "submissions": submissions,
        "notification_type": "submission_received",
    }
    _send_html_email(
        subject,
        [recipient_email],
        "emails/notification_digest.html",
        context,
        notification_type="batched",
    )


def _dispatch_approval_digest(recipient_email: str, notifications: list) -> None:
    """Send a digest of approval_request notifications to one recipient."""
    sample = notifications[0]
    workflow = sample.workflow
    form_name = workflow.form_definition.name
    count = len(notifications)
    items = []
    for n in notifications:
        if n.submission:
            items.append(
                {
                    "submission": n.submission,
                    "approval_task": n.approval_task,
                    "approval_url": _abs(
                        reverse(
                            "forms_workflows:approve_submission",
                            args=[n.approval_task.id],
                        )
                    )
                    if n.approval_task
                    else None,
                }
            )
    subject = (
        f"{count} item{'s' if count != 1 else ''} pending your approval — {form_name}"
    )
    context = {
        "form_name": form_name,
        "count": count,
        "items": items,
        "notification_type": "approval_request",
    }
    _send_html_email(
        subject,
        [recipient_email],
        "emails/notification_digest.html",
        context,
        notification_type="batched",
    )


_CONCLUSION_VERB: dict[str, tuple[str, str]] = {
    "approval_notification": ("approved", "Approvals"),
    "rejection_notification": ("rejected", "Rejections"),
    "withdrawal_notification": ("withdrawn", "Withdrawals"),
}


def _dispatch_conclusion_digest(
    recipient_email: str, notifications: list, notification_type: str
) -> None:
    """Send a digest of approval/rejection/withdrawal events to one recipient."""
    sample = notifications[0]
    workflow = sample.workflow
    form_name = workflow.form_definition.name
    count = len(notifications)
    verb, label = _CONCLUSION_VERB.get(notification_type, ("processed", "Updates"))
    submissions = [
        {
            "submission": n.submission,
            "submission_url": _abs(
                reverse("forms_workflows:submission_detail", args=[n.submission.id])
            ),
        }
        for n in notifications
        if n.submission
    ]
    subject = f"{count} submission{'s' if count != 1 else ''} {verb} — {form_name}"
    context = {
        "form_name": form_name,
        "count": count,
        "submissions": submissions,
        "notification_type": notification_type,
        "verb": verb,
        "label": label,
    }
    _send_html_email(
        subject,
        [recipient_email],
        "emails/notification_digest.html",
        context,
        notification_type="batched",
    )


# ---------------------------------------------------------------------------
# Form-Field Conditional Notification Tasks
# ---------------------------------------------------------------------------


def _get_form_field_email(form_data: dict, email_field: str) -> str | None:
    """Extract and validate an email address from form_data by field slug."""
    value = str(form_data.get(email_field, "")).strip()
    return value if value and "@" in value else None


def _collect_notification_recipients(
    notif, form_data: dict, submission=None
) -> list[str]:
    """Return the deduplicated list of recipient emails for a notification rule.

    Combines all recipient sources from a NotificationRule additively:

    1. notify_submitter  → submission.submitter.email
    2. email_field       → form_data[slug] (dynamic per submission)
    3. static_emails     → comma-separated fixed addresses
    4. notify_stage_assignees → ApprovalTask.assigned_to.email
    5. notify_stage_groups    → all users in the stage's approval groups
    6. notify_groups (M2M)    → all users in explicitly-listed groups
    """
    recipients: list[str] = []

    def _add(email: str | None) -> None:
        if email and email not in recipients:
            recipients.append(email)

    # 1. Submitter
    if getattr(notif, "notify_submitter", False) and submission is not None:
        _add(getattr(getattr(submission, "submitter", None), "email", None))

    # 2. Email field (dynamic from form_data)
    if notif.email_field:
        _add(_get_form_field_email(form_data, notif.email_field))

    # 3. Static emails
    for addr in (notif.static_emails or "").split(","):
        addr = addr.strip()
        if addr and "@" in addr:
            _add(addr)

    # 4. Stage assignees (NotificationRule only)
    if getattr(notif, "notify_stage_assignees", False) and submission is not None:
        qs = (
            submission.approval_tasks.select_related("assigned_to", "workflow_stage")
            .filter(assigned_to__isnull=False)
            .exclude(workflow_stage__assignee_form_field__isnull=True)
            .exclude(workflow_stage__assignee_form_field="")
        )
        # If rule is stage-scoped, limit to that stage
        if getattr(notif, "stage_id", None):
            qs = qs.filter(workflow_stage_id=notif.stage_id)
        for email in qs.values_list("assigned_to__email", flat=True):
            _add(email)

    # 5. Stage approval groups (NotificationRule only)
    if getattr(notif, "notify_stage_groups", False) and submission is not None:
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        # Determine which stages to include
        if getattr(notif, "stage_id", None):
            stage_ids = [notif.stage_id]
        else:
            # All stages in this workflow
            from .models import WorkflowStage

            stage_ids = list(
                WorkflowStage.objects.filter(workflow_id=notif.workflow_id).values_list(
                    "id", flat=True
                )
            )
        from .models import StageApprovalGroup

        group_ids = list(
            StageApprovalGroup.objects.filter(stage_id__in=stage_ids).values_list(
                "group_id", flat=True
            )
        )
        if group_ids:
            for email in (
                user_model.objects.filter(groups__id__in=group_ids)
                .exclude(email="")
                .values_list("email", flat=True)
                .distinct()
            ):
                _add(email)

    # 6. Explicit notify_groups M2M (NotificationRule only)
    if hasattr(notif, "notify_groups"):
        try:
            from django.contrib.auth import get_user_model

            user_model = get_user_model()
            group_ids = list(notif.notify_groups.values_list("id", flat=True))
            if group_ids:
                for email in (
                    user_model.objects.filter(groups__id__in=group_ids)
                    .exclude(email="")
                    .values_list("email", flat=True)
                    .distinct()
                ):
                    _add(email)
        except ValueError:
            # M2M not available (unsaved instance)
            pass

    return recipients


def _build_form_field_notification_context(
    submission: FormSubmission,
    task: ApprovalTask | None = None,
) -> tuple[str, str]:
    """Return (submission_url, approval_url) for notification templates."""
    submission_url = _abs(
        reverse("forms_workflows:submission_detail", args=[submission.id])
    )
    approval_url = (
        _abs(reverse("forms_workflows:approve_submission", args=[task.id]))
        if task
        else submission_url
    )
    return submission_url, approval_url


# ---------------------------------------------------------------------------
# Unified NotificationRule dispatch
# ---------------------------------------------------------------------------

# Maps NotificationRule event types to email templates
_EVENT_TEMPLATE_MAP: dict[str, str] = {
    "submission_received": "emails/submission_notification.html",
    "approval_request": "emails/approval_request.html",
    "stage_decision": "emails/approval_notification.html",
    "workflow_approved": "emails/approval_notification.html",
    "workflow_denied": "emails/rejection_notification.html",
    "form_withdrawn": "emails/withdrawal_notification.html",
}

_EVENT_DEFAULT_SUBJECTS: dict[str, str] = {
    "submission_received": "Submission Received: {form_name} (ID {submission_id})",
    "approval_request": "Action Required: {form_name} (ID {submission_id})",
    "stage_decision": "Stage Decision: {form_name} (ID {submission_id})",
    "workflow_approved": "Submission Approved: {form_name} (ID {submission_id})",
    "workflow_denied": "Submission Rejected: {form_name} (ID {submission_id})",
    "form_withdrawn": "Submission Withdrawn: {form_name} (ID {submission_id})",
}


@shared_task(name="django_forms_workflows.send_notification_rules")
def send_notification_rules(
    submission_id: int,
    event: str,
    task_id: int | None = None,
) -> None:
    """Unified notification dispatch for all NotificationRule records.

    Queries all ``NotificationRule`` records matching the given ``event`` for
    workflows attached to the submission's form definition.  For each rule:

    1. Evaluates optional ``conditions`` against ``form_data``.
    2. Resolves all recipient sources (submitter, email field, static,
       stage assignees, stage groups, explicit groups).
    3. Sends one email per recipient using the event's template.

    Args:
        submission_id: The FormSubmission to notify about.
        event: The NotificationRule event type (e.g. ``workflow_approved``).
        task_id: Optional ApprovalTask ID (used for approval_request context).
    """
    template = _EVENT_TEMPLATE_MAP.get(event)
    if not template:
        logger.warning("send_notification_rules: unknown event '%s'", event)
        return

    submission = FormSubmission.objects.select_related(
        "form_definition", "submitter"
    ).get(id=submission_id)
    form_data = submission.form_data or {}
    form_name = submission.form_definition.name
    submission_url, approval_url = _build_form_field_notification_context(
        submission,
        ApprovalTask.objects.get(id=task_id) if task_id else None,
    )

    workflow = getattr(submission.form_definition, "workflow", None)
    hide_approval_history = bool(getattr(workflow, "hide_approval_history", False))

    rules = (
        NotificationRule.objects.filter(
            workflow__form_definition=submission.form_definition,
            event=event,
        )
        .select_related("workflow", "stage")
        .prefetch_related("notify_groups")
    )

    default_subject_tpl = _EVENT_DEFAULT_SUBJECTS.get(
        event, "{form_name} (ID {submission_id})"
    )

    for rule in rules:
        # Evaluate optional conditions
        if rule.conditions:
            try:
                from .conditions import evaluate_conditions

                if not evaluate_conditions(rule.conditions, form_data):
                    logger.info(
                        "NotificationRule %s skipped: conditions not met "
                        "(submission %s, event %s)",
                        rule.id,
                        submission.id,
                        event,
                    )
                    continue
            except Exception:
                logger.warning(
                    "NotificationRule %s: error evaluating conditions; skipping.",
                    rule.id,
                    exc_info=True,
                )
                continue

        # Resolve recipients
        recipients = _collect_notification_recipients(
            rule, form_data, submission=submission
        )
        if not recipients:
            logger.info(
                "NotificationRule %s: no recipients resolved for submission %s; skipping.",
                rule.id,
                submission.id,
            )
            continue

        # Build subject with answer piping — {field_name} tokens are
        # resolved from form_data alongside the built-in {form_name} and
        # {submission_id} placeholders.
        _pipe_vars = {
            "form_name": form_name,
            "submission_id": submission.id,
            **{
                k: (", ".join(v) if isinstance(v, list) else str(v))
                for k, v in form_data.items()
            },
        }
        subject_tpl = rule.subject_template or default_subject_tpl
        try:
            subject = subject_tpl.format_map(defaultdict(str, _pipe_vars))
        except Exception:
            subject = subject_tpl.format(
                form_name=form_name, submission_id=submission.id
            )

        context = {
            "submission": submission,
            "form_data": form_data,
            "submission_url": submission_url,
            "approval_url": approval_url,
            "hide_approval_history": hide_approval_history,
        }
        if task_id:
            try:
                context["task"] = ApprovalTask.objects.get(id=task_id)
            except ApprovalTask.DoesNotExist:
                pass

        # Check cadence — batch or send immediately
        cadence = (
            getattr(workflow, "notification_cadence", "immediate")
            if workflow
            else "immediate"
        )
        if cadence != "immediate" and workflow is not None:
            scheduled_for = _compute_scheduled_for(workflow, submission)
            for recipient in recipients:
                PendingNotification.objects.create(
                    workflow=workflow,
                    notification_type=event,
                    submission=submission,
                    approval_task_id=task_id,
                    recipient_email=recipient,
                    scheduled_for=scheduled_for,
                )
            logger.info(
                "Queued %d %s notification(s) for submission %s (due %s)",
                len(recipients),
                event,
                submission.id,
                scheduled_for,
            )
        else:
            for recipient in recipients:
                _send_html_email(
                    subject,
                    [recipient],
                    template,
                    context,
                    notification_type=event,
                    submission_id=submission_id,
                )
