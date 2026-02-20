"""
Celery-friendly email tasks for Django Forms Workflows.

- Uses Celery if available (shared_task). If Celery isn't installed/running,
  tasks still import and `.delay(...)` will call synchronously as a graceful fallback.
- Emails use the package's generic templates under django_forms_workflows/templates/emails/.
- Absolute URLs are built from settings.FORMS_WORKFLOWS_BASE_URL (or SITE_BASE_URL) if set;
  otherwise fall back to relative paths.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, time as dt_time, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from .models import ApprovalTask, FormSubmission, PendingNotification

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
    return (
        getattr(settings, "FORMS_WORKFLOWS_BASE_URL", None)
        or getattr(settings, "SITE_BASE_URL", None)
        or ""
    )


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
) -> None:
    to_list = [e for e in to if e]
    if not to_list:
        logger.info("Skipping email '%s' (no recipients)", subject)
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
    except Exception as e:  # pragma: no cover
        logger.exception("Failed sending email '%s' to %s: %s", subject, to_list, e)


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
                candidate = timezone.make_aware(
                    datetime.combine(parsed, raw_time)
                )
                if candidate > now:
                    return candidate
            except (ValueError, TypeError):
                pass
        # Fallback: send tomorrow
        return _at_time(now + timedelta(days=1))

    # Fallback for unknown cadences
    return _at_time(now + timedelta(days=1))


def _queue_submission_notifications(submission, workflow) -> None:
    """Queue a submission_received PendingNotification for each recipient."""
    if not getattr(workflow, "notify_on_submission", True):
        return
    scheduled_for = _compute_scheduled_for(workflow, submission)
    recipients: list[str] = []
    submitter_email = getattr(getattr(submission, "submitter", None), "email", "")
    if submitter_email:
        recipients.append(submitter_email)
    extra = getattr(workflow, "additional_notify_emails", "") or ""
    for e in extra.split(","):
        e = e.strip()
        if e:
            recipients.append(e)
    for email in recipients:
        PendingNotification.objects.create(
            workflow=workflow,
            notification_type="submission_received",
            submission=submission,
            recipient_email=email,
            scheduled_for=scheduled_for,
        )
    logger.info(
        "Queued submission_received batch notification for submission %s (due %s)",
        submission.id,
        scheduled_for,
    )


def _queue_approval_request_notifications(task, workflow) -> None:
    """Queue approval_request PendingNotifications for the task's recipients."""
    scheduled_for = _compute_scheduled_for(workflow, task.submission)
    recipients: list[tuple[str, object]] = []  # (email, approver_user_or_None)

    if task.assigned_to and getattr(task.assigned_to, "email", None):
        recipients.append((task.assigned_to.email, task.assigned_to))
    elif task.assigned_group:
        for user in task.assigned_group.user_set.all():
            email = getattr(user, "email", None)
            if email:
                recipients.append((email, user))

    for email, _approver in recipients:
        PendingNotification.objects.create(
            workflow=workflow,
            notification_type="approval_request",
            submission=task.submission,
            approval_task=task,
            recipient_email=email,
            scheduled_for=scheduled_for,
        )
    logger.info(
        "Queued approval_request batch notification for task %s (due %s)",
        task.id,
        scheduled_for,
    )


@shared_task(name="django_forms_workflows.send_rejection_notification")
def send_rejection_notification(submission_id: int) -> None:
    """Notify submitter (and optional additional emails) that their submission was rejected."""
    submission = FormSubmission.objects.select_related(
        "form_definition", "submitter"
    ).get(id=submission_id)
    workflow = getattr(submission.form_definition, "workflow", None)
    if (
        workflow
        and hasattr(workflow, "notify_on_rejection")
        and not workflow.notify_on_rejection
    ):
        return

    task = (
        submission.approval_tasks.filter(status="rejected")
        .order_by("-completed_at")
        .first()
    )
    submission_url = _abs(
        reverse("forms_workflows:submission_detail", args=[submission.id])
    )
    context = {"submission": submission, "task": task, "submission_url": submission_url}
    subject = (
        f"Submission Rejected: {submission.form_definition.name} (ID {submission.id})"
    )

    recipients = [getattr(submission.submitter, "email", "")]
    if workflow and getattr(workflow, "additional_notify_emails", ""):
        recipients.extend(
            [
                e.strip()
                for e in workflow.additional_notify_emails.split(",")
                if e.strip()
            ]
        )

    _send_html_email(
        subject,
        recipients,
        "django_forms_workflows/emails/rejection_notification.html",
        context,
    )


@shared_task(name="django_forms_workflows.send_approval_notification")
def send_approval_notification(submission_id: int) -> None:
    """Notify submitter (and optional additional emails) that their submission was approved."""
    submission = FormSubmission.objects.select_related(
        "form_definition", "submitter"
    ).get(id=submission_id)
    workflow = getattr(submission.form_definition, "workflow", None)
    if (
        workflow
        and hasattr(workflow, "notify_on_approval")
        and not workflow.notify_on_approval
    ):
        return
    submission_url = _abs(
        reverse("forms_workflows:submission_detail", args=[submission.id])
    )
    context = {"submission": submission, "submission_url": submission_url}
    subject = (
        f"Submission Approved: {submission.form_definition.name} (ID {submission.id})"
    )
    recipients = [getattr(submission.submitter, "email", "")]
    if workflow and getattr(workflow, "additional_notify_emails", ""):
        recipients.extend(
            [
                e.strip()
                for e in workflow.additional_notify_emails.split(",")
                if e.strip()
            ]
        )
    _send_html_email(
        subject,
        recipients,
        "django_forms_workflows/emails/approval_notification.html",
        context,
    )


@shared_task(name="django_forms_workflows.send_submission_notification")
def send_submission_notification(submission_id: int) -> None:
    """Notify submitter (and optional additional emails) that their submission was received."""
    submission = FormSubmission.objects.select_related(
        "form_definition", "submitter"
    ).get(id=submission_id)
    workflow = getattr(submission.form_definition, "workflow", None)
    if (
        workflow
        and hasattr(workflow, "notify_on_submission")
        and not workflow.notify_on_submission
    ):
        return
    submission_url = _abs(
        reverse("forms_workflows:submission_detail", args=[submission.id])
    )
    context = {"submission": submission, "submission_url": submission_url}
    subject = (
        f"Submission Received: {submission.form_definition.name} (ID {submission.id})"
    )
    recipients = [getattr(submission.submitter, "email", "")]
    if workflow and getattr(workflow, "additional_notify_emails", ""):
        recipients.extend(
            [
                e.strip()
                for e in workflow.additional_notify_emails.split(",")
                if e.strip()
            ]
        )
    _send_html_email(
        subject,
        recipients,
        "django_forms_workflows/emails/submission_notification.html",
        context,
    )


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
    template = "django_forms_workflows/emails/approval_request.html"

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
        # Legacy sequential: show step info
        workflow = getattr(task.submission.form_definition, "workflow", None)
        total_steps = workflow.approval_groups.count() if workflow else 1
        stage_context = {
            "stage_number": task.step_number,
            "total_stages": total_steps,
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
        )
        return

    if task.assigned_group:
        recipients = []
        for user in task.assigned_group.user_set.all():
            email = getattr(user, "email", None)
            if not email:
                continue
            _send_html_email(subject, [email], template, _build_context(user))
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
        "django_forms_workflows/emails/approval_reminder.html",
        context,
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

                # Escalate to configured groups upon expiry
                try:
                    groups = list(getattr(workflow, "escalation_groups", []).all())
                except Exception:
                    groups = []
                for g in groups:
                    for user in g.user_set.all():
                        email = getattr(user, "email", None)
                        if not email:
                            continue
                        try:
                            from .tasks import send_escalation_notification

                            send_escalation_notification.delay(task.id, to_email=email)
                        except Exception:
                            pass

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
                            from .tasks import send_approval_notification

                            send_approval_notification.delay(submission.id)
                        except Exception:
                            pass
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
                    from .tasks import send_approval_reminder

                    send_approval_reminder.delay(task.id)
                except Exception:
                    pass
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
        "django_forms_workflows/emails/escalation_notification.html",
        context,
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
    for (recipient_email, notification_type, _workflow_id), notifications in groups.items():
        try:
            if notification_type == "submission_received":
                _dispatch_submission_digest(recipient_email, notifications)
            elif notification_type == "approval_request":
                _dispatch_approval_digest(recipient_email, notifications)
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
        "django_forms_workflows/emails/notification_digest.html",
        context,
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
        "django_forms_workflows/emails/notification_digest.html",
        context,
    )
