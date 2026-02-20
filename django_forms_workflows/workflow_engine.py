"""
Workflow engine for Django Forms Workflows.

Creates approval tasks based on the workflow definition and advances the
workflow when approvals are processed.

Staged / hybrid workflows
--------------------------
When a WorkflowDefinition has one or more WorkflowStage rows the engine runs
in *staged mode*:

  Stage 1 tasks are created on submission.  When a stage completes (according
  to the stage's own approval_logic: all/any/sequence) the engine creates the
  tasks for the next stage.  When the final stage completes the submission is
  finalised.

Legacy (flat) mode
------------------
WorkflowDefinitions with no WorkflowStage rows continue to use the existing
flat approval_logic + approval_groups path unchanged.

Rejection semantics
-------------------
* "all" / "sequence" — one rejection vetoes the whole submission immediately.
* "any"              — a rejection is recorded on that task but the submission
                       survives until every task in the current scope has been
                       resolved.  Only when *all* tasks are rejected (and none
                       are approved) is the submission itself rejected.

Email notifications are delegated to django_forms_workflows.tasks where they
will run asynchronously if Celery is available or synchronously otherwise.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ApprovalTask, FormSubmission, WorkflowDefinition, WorkflowStage

logger = logging.getLogger(__name__)


# --- Internal helpers -------------------------------------------------------

# ---- notification shims ----


def _notify_submission_created(submission: FormSubmission) -> None:
    workflow = getattr(submission.form_definition, "workflow", None)
    cadence = getattr(workflow, "notification_cadence", "immediate") if workflow else "immediate"

    if cadence != "immediate" and workflow is not None:
        try:
            from .tasks import _queue_submission_notifications

            _queue_submission_notifications(submission, workflow)
        except Exception:
            logger.warning("Failed to queue batched submission notification; falling back to immediate")
            _notify_submission_created_immediate(submission)
        return

    _notify_submission_created_immediate(submission)


def _notify_submission_created_immediate(submission: FormSubmission) -> None:
    try:  # defer import to avoid hard Celery dependency at import time
        from .tasks import send_submission_notification

        send_submission_notification.delay(submission.id)
    except Exception:  # ImportError or other
        logger.warning("Notification tasks not available for submission_created")


def _notify_task_request(task: ApprovalTask) -> None:
    workflow = getattr(task.submission.form_definition, "workflow", None)
    cadence = getattr(workflow, "notification_cadence", "immediate") if workflow else "immediate"

    if cadence != "immediate" and workflow is not None:
        try:
            from .tasks import _queue_approval_request_notifications

            _queue_approval_request_notifications(task, workflow)
        except Exception:
            logger.warning("Failed to queue batched approval request; falling back to immediate")
            _notify_task_request_immediate(task)
        return

    _notify_task_request_immediate(task)


def _notify_task_request_immediate(task: ApprovalTask) -> None:
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


def _notify_rejection(submission: FormSubmission) -> None:
    try:
        from .tasks import send_rejection_notification

        send_rejection_notification.delay(submission.id)
    except Exception:
        logger.warning("Notification tasks not available for rejection_notification")


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

    # Execute post-approval actions with exception handling to prevent
    # failures from affecting the submission status update
    try:
        execute_post_approval_updates(submission)
    except Exception as e:
        logger.error("Error in execute_post_approval_updates: %s", e, exc_info=True)

    try:
        execute_post_submission_actions(submission, "on_complete")
    except Exception as e:
        logger.error("Error in execute_post_submission_actions: %s", e, exc_info=True)

    try:
        execute_file_workflow_hooks(submission, "on_approve")
    except Exception as e:
        logger.error("Error in execute_file_workflow_hooks: %s", e, exc_info=True)

    _notify_final_approval(submission)


def _reject_submission(submission: FormSubmission, reason: str = "") -> None:
    """Mark submission as rejected and execute rejection hooks."""
    submission.status = "rejected"
    submission.completed_at = timezone.now()
    submission.save(update_fields=["status", "completed_at"])

    # Cancel any remaining pending tasks
    submission.approval_tasks.filter(status="pending").update(status="skipped")

    # Execute rejection actions with exception handling to prevent
    # failures from affecting the submission status update
    try:
        execute_post_submission_actions(submission, "on_reject")
    except Exception as e:
        logger.error(
            "Error in execute_post_submission_actions (on_reject): %s", e, exc_info=True
        )

    try:
        execute_file_workflow_hooks(submission, "on_reject")
    except Exception as e:
        logger.error(
            "Error in execute_file_workflow_hooks (on_reject): %s", e, exc_info=True
        )

    # Mark all managed files as rejected
    try:
        for managed_file in submission.managed_files.filter(
            is_current=True, status="pending"
        ):
            managed_file.mark_rejected(notes=reason)
    except Exception as e:
        logger.error("Error marking managed files as rejected: %s", e, exc_info=True)

    _notify_rejection(submission)


# ---- staged workflow helpers ----


def _create_stage_tasks(
    submission: FormSubmission,
    stage: WorkflowStage,
    stage_number: int,
    due_date,
) -> None:
    """Create approval tasks for a single workflow stage.

    Handles manager-first ordering within the stage: if ``requires_manager_approval``
    is True, only the manager task is created; group tasks are created later when
    ``handle_approval`` processes that manager task.
    """
    groups = list(stage.approval_groups.all().order_by("id"))

    manager_task_created = False
    if stage.requires_manager_approval:
        try:
            from .ldap_backend import get_user_manager
        except Exception:
            get_user_manager = None  # type: ignore
        manager = get_user_manager(submission.submitter) if get_user_manager else None
        if manager:
            task = ApprovalTask.objects.create(
                submission=submission,
                assigned_to=manager,
                workflow_stage=stage,
                stage_number=stage_number,
                step_name=f"Stage {stage_number}: Manager Approval",
                status="pending",
                due_date=due_date,
            )
            manager_task_created = True
            _notify_task_request(task)
        else:
            logger.info(
                "Manager approval required but manager not found for user %s (stage %d)",
                submission.submitter,
                stage_number,
            )

    # Manager task gates group tasks — create groups later via handle_approval
    if manager_task_created:
        return

    if not groups:
        return  # caller responsible for advancing/finalizing if stage has no tasks

    if stage.approval_logic == "sequence":
        g = groups[0]
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=g,
            workflow_stage=stage,
            stage_number=stage_number,
            step_name=f"Stage {stage_number}: {g.name} (Step 1 of {len(groups)})",
            step_number=1,
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
    else:
        # "all" or "any" → parallel tasks for every group
        for g in groups:
            task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=g,
                workflow_stage=stage,
                stage_number=stage_number,
                step_name=f"Stage {stage_number}: {g.name} Approval",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(task)


def _advance_to_next_stage(
    submission: FormSubmission,
    workflow: WorkflowDefinition,
    stages: list,
    current_stage_number: int,
    due_date,
) -> None:
    """Create tasks for the next stage, or finalize if this was the last stage.

    ``stages`` must be ordered by ``order``; ``current_stage_number`` is 1-indexed.
    """
    if current_stage_number < len(stages):
        next_stage = stages[current_stage_number]  # 0-indexed = current_stage_number
        _create_stage_tasks(
            submission,
            next_stage,
            stage_number=current_stage_number + 1,
            due_date=due_date,
        )
    else:
        _finalize_submission(submission)


# --- Public API -------------------------------------------------------------


@transaction.atomic
def create_workflow_tasks(submission: FormSubmission) -> None:
    """Create approval tasks for a newly submitted form and send notifications.

    Staged mode (workflow has WorkflowStage rows):
      Creates tasks for the first stage only.  Subsequent stages are created
      by ``handle_approval`` as each stage completes.

    Legacy mode (no WorkflowStage rows):
      Manager task first (if required), then group tasks per approval_logic.
    """
    workflow: WorkflowDefinition | None = getattr(
        submission.form_definition, "workflow", None
    )

    # Always notify submission was received (respects notify_on_submission flag)
    _notify_submission_created(submission)

    # Execute on_submit actions
    execute_post_submission_actions(submission, "on_submit")
    execute_file_workflow_hooks(submission, "on_submit")

    if not workflow or not workflow.requires_approval:
        _finalize_submission(submission)
        return

    if submission.status != "pending_approval":
        submission.status = "pending_approval"
        submission.save(update_fields=["status"])

    due_date = _due_date_for(workflow)

    # --- Staged mode ---
    stages = list(workflow.stages.order_by("order"))
    if stages:
        first_stage = stages[0]
        groups = list(first_stage.approval_groups.all())
        if not first_stage.requires_manager_approval and not groups:
            # Stage has no reviewers configured — finalize immediately
            _finalize_submission(submission)
            return
        _create_stage_tasks(submission, first_stage, stage_number=1, due_date=due_date)
        return

    # --- Legacy flat mode ---

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

    if manager_task_created:
        return

    # 2) Group approvals
    groups = list(workflow.approval_groups.all().order_by("id"))
    if not groups:
        _finalize_submission(submission)
        return

    if workflow.approval_logic == "sequence":
        g = groups[0]
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=g,
            step_name=f"{g.name} Approval (Step 1 of {len(groups)})",
            step_number=1,
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
    else:
        # "all" or "any" → parallel tasks for every group
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
    """Advance the workflow after an approval event on a task.

    Dispatches to staged or legacy logic based on whether the task has an
    associated ``workflow_stage``.
    """
    due_date = _due_date_for(workflow)

    # ------------------------------------------------------------------ staged
    if task.workflow_stage:
        stage = task.workflow_stage
        stage_number = task.stage_number or 1
        stages = list(workflow.stages.order_by("order"))

        is_manager_task = (
            task.assigned_to_id is not None and "manager" in task.step_name.lower()
        )

        if is_manager_task:
            # Manager gate passed — now create group tasks for same stage
            groups = list(stage.approval_groups.all().order_by("id"))
            if not groups:
                _advance_to_next_stage(
                    submission, workflow, stages, stage_number, due_date
                )
                return
            if stage.approval_logic == "sequence":
                g = groups[0]
                new_task = ApprovalTask.objects.create(
                    submission=submission,
                    assigned_group=g,
                    workflow_stage=stage,
                    stage_number=stage_number,
                    step_name=f"Stage {stage_number}: {g.name} (Step 1 of {len(groups)})",
                    step_number=1,
                    status="pending",
                    due_date=due_date,
                )
                _notify_task_request(new_task)
            else:
                for g in groups:
                    new_task = ApprovalTask.objects.create(
                        submission=submission,
                        assigned_group=g,
                        workflow_stage=stage,
                        stage_number=stage_number,
                        step_name=f"Stage {stage_number}: {g.name} Approval",
                        status="pending",
                        due_date=due_date,
                    )
                    _notify_task_request(new_task)
            return

        logic = stage.approval_logic

        if logic == "any":
            # First approval in stage wins; skip remaining stage tasks
            submission.approval_tasks.filter(
                workflow_stage=stage, status="pending"
            ).exclude(id=task.id).update(status="skipped")
            _advance_to_next_stage(submission, workflow, stages, stage_number, due_date)

        elif logic == "all":
            # Advance only when all group tasks in this stage are done
            if not submission.approval_tasks.filter(
                workflow_stage=stage,
                status="pending",
                assigned_group__isnull=False,
            ).exists():
                _advance_to_next_stage(
                    submission, workflow, stages, stage_number, due_date
                )

        elif logic == "sequence":
            groups = list(stage.approval_groups.all().order_by("id"))
            ids = [g.id for g in groups]
            try:
                idx = ids.index(task.assigned_group_id)  # type: ignore[arg-type]
            except ValueError:
                idx = len(ids) - 1  # treat unknown as last step

            if idx + 1 < len(groups):
                next_group = groups[idx + 1]
                new_task = ApprovalTask.objects.create(
                    submission=submission,
                    assigned_group=next_group,
                    workflow_stage=stage,
                    stage_number=stage_number,
                    step_name=(
                        f"Stage {stage_number}: {next_group.name}"
                        f" (Step {idx + 2} of {len(groups)})"
                    ),
                    step_number=idx + 2,
                    status="pending",
                    due_date=due_date,
                )
                _notify_task_request(new_task)
            else:
                _advance_to_next_stage(
                    submission, workflow, stages, stage_number, due_date
                )

        return

    # ------------------------------------------------------------------ legacy
    is_manager_task = (
        task.assigned_to_id is not None and task.step_name.lower().startswith("manager")
    )

    if is_manager_task:
        groups = list(workflow.approval_groups.all().order_by("id"))
        if not groups:
            _finalize_submission(submission)
            return
        if workflow.approval_logic == "sequence":
            g = groups[0]
            new_task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=g,
                step_name=f"{g.name} Approval (Step 1 of {len(groups)})",
                step_number=1,
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

    logic = workflow.approval_logic

    if logic == "any":
        submission.approval_tasks.filter(
            status="pending", assigned_group__isnull=False
        ).exclude(id=task.id).update(status="skipped")
        _finalize_submission(submission)
        return

    if logic == "all":
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
        ids = [g.id for g in groups]
        try:
            idx = ids.index(task.assigned_group_id)  # type: ignore[arg-type]
        except ValueError:
            idx = -1

        if idx == -1:
            if not submission.approval_tasks.filter(
                status="pending", assigned_group__isnull=False
            ).exists():
                _finalize_submission(submission)
            return

        if idx + 1 < len(groups):
            next_group = groups[idx + 1]
            new_task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=next_group,
                step_name=f"{next_group.name} Approval (Step {idx + 2} of {len(groups)})",
                step_number=idx + 2,
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(new_task)
        else:
            _finalize_submission(submission)


@transaction.atomic
def handle_rejection(
    submission: FormSubmission, task: ApprovalTask, workflow: WorkflowDefinition
) -> None:
    """Handle a rejection event on an approval task.

    Semantics depend on the active ``approval_logic`` (per-stage or top-level):

    * ``"all"`` / ``"sequence"`` — one rejection immediately vetoes the
      submission and cancels all remaining pending tasks.
    * ``"any"`` — the rejection is recorded on the task but the submission
      survives until every task in scope is resolved.  The submission is only
      rejected when *all* tasks in scope are rejected and *none* are approved.
    """
    # Determine effective logic and task scope
    if task.workflow_stage:
        logic = task.workflow_stage.approval_logic
        scope_qs = submission.approval_tasks.filter(workflow_stage=task.workflow_stage)
    else:
        logic = workflow.approval_logic
        scope_qs = submission.approval_tasks.filter(
            workflow_stage__isnull=True,
            assigned_group__isnull=False,
        )

    if logic == "any":
        # Submission survives unless ALL tasks in scope are rejected
        if scope_qs.filter(status="approved").exists():
            # At least one has already approved — submission already finalised
            return
        if scope_qs.filter(status="pending").exists():
            # Others still outstanding — just wait
            return
        # Every task is rejected (none approved) → veto
        _reject_submission(submission)
    else:
        # "all" or "sequence" — immediate veto
        _reject_submission(submission)


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
