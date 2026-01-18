"""
Workflow engine for Django Forms Workflows.

Creates approval tasks based on the workflow definition and advances the
workflow when approvals are processed.

Email notifications are delegated to django_forms_workflows.tasks where they
will run asynchronously if Celery is available or synchronously otherwise.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ApprovalTask, FormSubmission, WorkflowDefinition

logger = logging.getLogger(__name__)


# --- Internal helpers -------------------------------------------------------


def _notify_submission_created(submission: FormSubmission) -> None:
    try:  # defer import to avoid hard Celery dependency at import time
        from .tasks import send_submission_notification

        send_submission_notification.delay(submission.id)
    except Exception:  # ImportError or other
        logger.warning("Notification tasks not available for submission_created")


def _notify_task_request(task: ApprovalTask) -> None:
    try:
        from .tasks import send_approval_request

        send_approval_request.delay(task.id)
    except Exception:
        logger.warning("Notification tasks not available for approval_request")


def _notify_final_approval(submission: FormSubmission) -> None:
    try:
        from .tasks import send_approval_notification

        send_approval_notification.delay(submission.id)
    except Exception:
        logger.warning("Notification tasks not available for approval_notification")


def _due_date_for(workflow: WorkflowDefinition):
    if getattr(workflow, "approval_deadline_days", None):
        return timezone.now() + timedelta(days=workflow.approval_deadline_days)  # type: ignore[arg-type]
    return None


def _finalize_submission(submission: FormSubmission) -> None:
    submission.status = "approved"
    submission.completed_at = timezone.now()
    submission.save(update_fields=["status", "completed_at"])

    # Cancel any remaining pending tasks
    submission.approval_tasks.filter(status="pending").update(status="skipped")

    execute_post_approval_updates(submission)
    execute_post_submission_actions(submission, "on_complete")
    execute_file_workflow_hooks(submission, "on_approve")
    _notify_final_approval(submission)


def _reject_submission(submission: FormSubmission, reason: str = "") -> None:
    """Mark submission as rejected and execute rejection hooks."""
    submission.status = "rejected"
    submission.completed_at = timezone.now()
    submission.save(update_fields=["status", "completed_at"])

    # Cancel any remaining pending tasks
    submission.approval_tasks.filter(status="pending").update(status="skipped")

    # Execute rejection actions
    execute_post_submission_actions(submission, "on_reject")
    execute_file_workflow_hooks(submission, "on_reject")

    # Mark all managed files as rejected
    for managed_file in submission.managed_files.filter(
        is_current=True, status="pending"
    ):
        managed_file.mark_rejected(notes=reason)


# --- Public API -------------------------------------------------------------


@transaction.atomic
def create_workflow_tasks(submission: FormSubmission) -> None:
    """Create approval tasks for a newly submitted form and send notifications.

    Behavior:
    - If no workflow or approval not required: finalize immediately and notify.
    - If manager approval is required: create only the manager task first.
    - Otherwise: create group tasks according to approval_logic.
    - In all cases: notify submitter that submission was received (respecting flags).
    """
    workflow: WorkflowDefinition | None = getattr(
        submission.form_definition, "workflow", None
    )

    # Always notify submission was received (task respects notify_on_submission)
    _notify_submission_created(submission)

    # Execute on_submit actions
    execute_post_submission_actions(submission, "on_submit")

    # Execute file workflow hooks for submission
    execute_file_workflow_hooks(submission, "on_submit")

    if not workflow or not workflow.requires_approval:
        _finalize_submission(submission)
        return

    # Pending approval state
    if submission.status != "pending_approval":
        submission.status = "pending_approval"
        submission.save(update_fields=["status"])

    due_date = _due_date_for(workflow)

    # 1) Manager approval (first step if required)
    manager_task_created = False
    if getattr(workflow, "requires_manager_approval", False):
        try:
            from .ldap_backend import get_user_manager
        except Exception:
            get_user_manager = None  # type: ignore
        manager = get_user_manager(submission.submitter) if get_user_manager else None
        if manager:
            task = ApprovalTask.objects.create(
                submission=submission,
                assigned_to=manager,
                step_name="Manager Approval",
                status="pending",
                due_date=due_date,
            )
            manager_task_created = True
            _notify_task_request(task)
        else:
            logger.info(
                "Manager approval required but manager not found for user %s",
                submission.submitter,
            )

    # If manager approval was created, we stop here and wait for that to complete
    if manager_task_created:
        return

    # 2) Group approvals
    groups = list(workflow.approval_groups.all().order_by("id"))

    if not groups:
        # No groups and no manager: finalize immediately
        _finalize_submission(submission)
        return

    if workflow.approval_logic == "sequence":
        g = groups[0]
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=g,
            step_name=f"{g.name} Approval (Step 1 of {len(groups)})",
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
    else:
        # 'all' or 'any' -> create all tasks in parallel
        for g in groups:
            task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=g,
                step_name=f"{g.name} Approval",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(task)


@transaction.atomic
def handle_approval(
    submission: FormSubmission, task: ApprovalTask, workflow: WorkflowDefinition
) -> None:
    """Advance the workflow after an approval event on a task."""
    # If this was the manager approval task, create the group tasks next
    is_manager_task = (
        task.assigned_to_id is not None and task.step_name.lower().startswith("manager")
    )

    if is_manager_task:
        groups = list(workflow.approval_groups.all().order_by("id"))
        if not groups:
            _finalize_submission(submission)
            return

        due_date = _due_date_for(workflow)
        if workflow.approval_logic == "sequence":
            g = groups[0]
            new_task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=g,
                step_name=f"{g.name} Approval (Step 1 of {len(groups)})",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(new_task)
        else:
            for g in groups:
                new_task = ApprovalTask.objects.create(
                    submission=submission,
                    assigned_group=g,
                    step_name=f"{g.name} Approval",
                    status="pending",
                    due_date=due_date,
                )
                _notify_task_request(new_task)
        return

    # Otherwise this is a group approval task
    logic = workflow.approval_logic

    if logic == "any":
        # First approval wins; skip the rest and finalize
        submission.approval_tasks.filter(
            status="pending", assigned_group__isnull=False
        ).exclude(id=task.id).update(status="skipped")
        _finalize_submission(submission)
        return

    if logic == "all":
        # When no pending group tasks remain, finalize
        if not submission.approval_tasks.filter(
            status="pending", assigned_group__isnull=False
        ).exists():
            _finalize_submission(submission)
        return

    if logic == "sequence":
        groups = list(workflow.approval_groups.all().order_by("id"))
        if not groups:
            _finalize_submission(submission)
            return

        # Find current group position
        ids = [g.id for g in groups]
        try:
            idx = ids.index(task.assigned_group_id)  # type: ignore[arg-type]
        except ValueError:
            idx = -1

        if idx == -1:
            # Unknown group; if nothing pending, finalize safely
            if not submission.approval_tasks.filter(
                status="pending", assigned_group__isnull=False
            ).exists():
                _finalize_submission(submission)
            return

        # If there is a next step, create it; otherwise finalize
        if idx + 1 < len(groups):
            next_group = groups[idx + 1]
            due_date = _due_date_for(workflow)
            new_task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=next_group,
                step_name=f"{next_group.name} Approval (Step {idx + 2} of {len(groups)})",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(new_task)
        else:
            _finalize_submission(submission)


# --- Post-submission actions ------------------------------------------------


def execute_post_submission_actions(submission: FormSubmission, trigger: str) -> None:
    """Execute post-submission actions for the given trigger.

    Args:
        submission: FormSubmission instance
        trigger: Trigger type ('on_submit', 'on_approve', 'on_reject', 'on_complete')
    """
    try:
        from .handlers.executor import PostSubmissionActionExecutor

        executor = PostSubmissionActionExecutor(submission, trigger)
        results = executor.execute_all()

        if results["failed"] > 0:
            logger.warning(
                f"Some post-submission actions failed for submission {submission.id}: "
                f"{results['failed']} failed, {results['succeeded']} succeeded"
            )
        elif results["executed"] > 0:
            logger.info(
                f"Post-submission actions completed for submission {submission.id}: "
                f"{results['succeeded']} succeeded"
            )
    except Exception as e:
        logger.error(
            f"Error executing post-submission actions for submission {submission.id}: {e}",
            exc_info=True,
        )


def execute_post_approval_updates(submission: FormSubmission) -> None:
    """Perform post-approval updates if configured.

    Executes post-submission actions with 'on_approve' trigger.
    Also supports legacy db_update_mappings for backward compatibility.
    """
    # Execute new post-submission actions
    execute_post_submission_actions(submission, "on_approve")

    # Execute file workflow hooks for approval
    execute_file_workflow_hooks(submission, "on_approve")

    # Legacy support for db_update_mappings
    workflow: WorkflowDefinition | None = getattr(
        submission.form_definition, "workflow", None
    )
    if workflow and getattr(workflow, "enable_db_updates", False):
        mappings = getattr(workflow, "db_update_mappings", None)
        if mappings:
            logger.info(
                "Legacy db_update_mappings detected. "
                "Consider migrating to PostSubmissionAction model for better configurability."
            )


def execute_file_workflow_hooks(submission: FormSubmission, trigger: str) -> None:
    """Execute file workflow hooks for all managed files in a submission.

    Args:
        submission: FormSubmission instance
        trigger: Trigger type ('on_upload', 'on_submit', 'on_approve', 'on_reject', 'on_supersede')
    """
    try:
        from .handlers.file_handler import execute_file_hooks

        # Get all managed files for this submission
        managed_files = submission.managed_files.filter(is_current=True)

        for managed_file in managed_files:
            try:
                results = execute_file_hooks(managed_file, trigger)

                if results["failed"] > 0:
                    logger.warning(
                        f"Some file hooks failed for file {managed_file.id}: "
                        f"{results['failed']} failed, {results['succeeded']} succeeded"
                    )
            except Exception as e:
                logger.error(
                    f"Error executing file hooks for file {managed_file.id}: {e}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            f"Error executing file workflow hooks for submission {submission.id}: {e}",
            exc_info=True,
        )
