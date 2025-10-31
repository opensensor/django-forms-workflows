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
from collections.abc import Iterable
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from .models import ApprovalTask, FormSubmission

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
    ).get(id=task_id)
    approval_url = _abs(reverse("forms_workflows:approve_submission", args=[task.id]))
    subject = f"Approval Request: {task.submission.form_definition.name} (ID {task.submission.id})"
    template = "django_forms_workflows/emails/approval_request.html"

    if task.assigned_to and getattr(task.assigned_to, "email", None):
        context = {
            "task": task,
            "submission": task.submission,
            "approver": task.assigned_to,
            "approval_url": approval_url,
        }
        _send_html_email(subject, [task.assigned_to.email], template, context)
        return

    if task.assigned_group:
        recipients = []
        for user in task.assigned_group.user_set.all():
            email = getattr(user, "email", None)
            if not email:
                continue
            context = {
                "task": task,
                "submission": task.submission,
                "approver": user,
                "approval_url": approval_url,
            }
            _send_html_email(subject, [email], template, context)
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
