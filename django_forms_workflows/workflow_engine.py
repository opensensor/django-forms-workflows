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

from .conditions import evaluate_conditions
from .models import (
    ApprovalTask,
    FormSubmission,
    SubWorkflowDefinition,
    SubWorkflowInstance,
    WorkflowDefinition,
    WorkflowStage,
)

logger = logging.getLogger(__name__)


# --- Internal helpers -------------------------------------------------------

# ---- notification shims ----


def _notify_submission_created(submission: FormSubmission) -> None:
    workflow = getattr(submission.form_definition, "workflow", None)
    cadence = (
        getattr(workflow, "notification_cadence", "immediate")
        if workflow
        else "immediate"
    )

    if cadence != "immediate" and workflow is not None:
        try:
            from .tasks import _queue_submission_notifications

            _queue_submission_notifications(submission, workflow)
        except Exception:
            logger.warning(
                "Failed to queue batched submission notification; falling back to immediate"
            )
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
    cadence = (
        getattr(workflow, "notification_cadence", "immediate")
        if workflow
        else "immediate"
    )

    if cadence != "immediate" and workflow is not None:
        try:
            from .tasks import _queue_approval_request_notifications

            _queue_approval_request_notifications(task, workflow)
        except Exception:
            logger.warning(
                "Failed to queue batched approval request; falling back to immediate"
            )
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

    # Spawn any sub-workflows configured to fire after parent approval
    try:
        _spawn_sub_workflows_for_trigger(submission, "on_approval")
    except Exception as e:
        logger.error("Error spawning sub-workflows on approval: %s", e, exc_info=True)

    # If non-detached sub-workflow instances are now pending/in-progress,
    # hold the parent at "approved_pending" until they all complete.
    try:
        _maybe_set_approved_pending(submission)
    except Exception as e:
        logger.error("Error setting approved_pending status: %s", e, exc_info=True)


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
    due_date,
) -> None:
    """Create approval tasks for a single workflow stage.

    Uses ``stage.order`` as the display stage number so that parallel stages
    sharing the same order appear under the same step label.

    Handles manager-first ordering within the stage: if ``requires_manager_approval``
    is True, only the manager task is created; group tasks are created later when
    ``handle_approval`` processes that manager task.
    """
    stage_num = stage.order
    groups = list(stage.approval_groups.all().order_by("stageapprovalgroup__position"))

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
                stage_number=stage_num,
                step_name=f"Stage {stage_num}",
                status="pending",
                due_date=due_date,
            )
            manager_task_created = True
            _notify_task_request(task)
        else:
            logger.info(
                "Manager approval required but manager not found for user %s (stage %d)",
                submission.submitter,
                stage_num,
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
            stage_number=stage_num,
            step_name=f"Stage {stage_num} (Step 1 of {len(groups)})",
            step_number=1,
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
    else:
        # "all" or "any" → parallel tasks for every group in this stage
        for g in groups:
            task = ApprovalTask.objects.create(
                submission=submission,
                assigned_group=g,
                workflow_stage=stage,
                stage_number=stage_num,
                step_name=f"Stage {stage_num}",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(task)


def _try_finalize_all_tracks(submission: FormSubmission) -> None:
    """Finalize the submission only when every workflow track is complete.

    A track is complete when it has no pending approval tasks across any of
    its stages.  For single-workflow forms this is equivalent to the old
    ``_finalize_submission`` call.
    """
    # Collect all stage IDs across every workflow on this form
    all_workflows = list(
        submission.form_definition.workflows.filter(requires_approval=True)
    )
    if not all_workflows:
        _finalize_submission(submission)
        return

    for wf in all_workflows:
        stage_ids = list(wf.stages.values_list("id", flat=True))
        if not stage_ids:
            continue
        if submission.approval_tasks.filter(
            workflow_stage_id__in=stage_ids, status="pending"
        ).exists():
            return  # This track still has pending work

    # All tracks complete
    _finalize_submission(submission)


def _advance_to_next_stage(
    submission: FormSubmission,
    workflow: WorkflowDefinition,
    stages: list,
    current_order: int,
    due_date,
) -> None:
    """Advance to the next order-level of stages, or finalize if none remain.

    Stages sharing the same ``order`` value run in parallel.  This function
    first checks that every sibling stage at ``current_order`` has no pending
    tasks before moving forward — ensuring all parallel branches complete
    before the workflow advances.

    ``stages`` must be pre-sorted by ``order`` (ascending).
    """
    # Wait until ALL parallel stages at the current order are complete.
    for sibling in (s for s in stages if s.order == current_order):
        if submission.approval_tasks.filter(
            workflow_stage=sibling, status="pending"
        ).exists():
            return  # A parallel branch is still in progress

    # Find stages at the next order level within this workflow track,
    # filtering by trigger_conditions against the submission data.
    form_data = submission.form_data or {}
    future_stages = [s for s in stages if s.order > current_order]
    if not future_stages:
        # This workflow track is complete.  Check whether ALL tracks are done
        # before finalizing the submission.
        _try_finalize_all_tracks(submission)
        return

    next_order = future_stages[0].order
    eligible_stages = [
        s
        for s in future_stages
        if s.order == next_order
        and evaluate_conditions(s.trigger_conditions, form_data)
    ]
    if not eligible_stages:
        # No eligible stages at the next order — check further orders
        # or finalize if nothing remains.
        remaining = [
            s
            for s in future_stages
            if s.order > next_order
            and evaluate_conditions(s.trigger_conditions, form_data)
        ]
        if remaining:
            # Jump to the next eligible order level
            jump_order = remaining[0].order
            for stage in (s for s in remaining if s.order == jump_order):
                _create_stage_tasks(submission, stage, due_date=due_date)
        else:
            _try_finalize_all_tracks(submission)
        return

    for stage in eligible_stages:
        _create_stage_tasks(submission, stage, due_date=due_date)


# --- Public API -------------------------------------------------------------


@transaction.atomic
def create_workflow_tasks(submission: FormSubmission) -> None:
    """Create approval tasks for a newly submitted form and send notifications.

    Multi-workflow mode:
      Iterates over ALL workflows attached to the form definition.
      For each workflow that requires approval, creates tasks for the first
      stage(s).  All workflows run in parallel.  The submission is only
      finalized when every workflow track has completed.

    Single-workflow / legacy mode:
      Behaves identically to multi-workflow with one workflow.
    """
    workflows = list(submission.form_definition.workflows.all())

    # Always notify submission was received (respects notify_on_submission flag)
    _notify_submission_created(submission)

    # Execute on_submit actions
    execute_post_submission_actions(submission, "on_submit")
    execute_file_workflow_hooks(submission, "on_submit")

    # Spawn any sub-workflows configured to fire immediately on submission
    try:
        _spawn_sub_workflows_for_trigger(submission, "on_submission")
    except Exception as e:
        logger.error("Error spawning sub-workflows on submission: %s", e, exc_info=True)

    # Filter to workflows that require approval AND whose trigger
    # conditions (if any) match the submission data.
    form_data = submission.form_data or {}
    approval_workflows = [
        w
        for w in workflows
        if w.requires_approval and evaluate_conditions(w.trigger_conditions, form_data)
    ]
    if not approval_workflows:
        _finalize_submission(submission)
        return

    if submission.status != "pending_approval":
        submission.status = "pending_approval"
        submission.save(update_fields=["status"])

    any_created = False
    for workflow in approval_workflows:
        due_date = _due_date_for(workflow)
        stages = list(workflow.stages.order_by("order", "id"))
        if not stages:
            continue  # No stages configured for this track

        first_order = stages[0].order
        first_order_stages = [
            s
            for s in stages
            if s.order == first_order
            and evaluate_conditions(s.trigger_conditions, form_data)
        ]
        for stage in first_order_stages:
            groups = list(stage.approval_groups.all())
            if not stage.requires_manager_approval and not groups:
                continue  # empty stage — skip
            _create_stage_tasks(submission, stage, due_date=due_date)
            any_created = True

    if not any_created:
        _finalize_submission(submission)


@transaction.atomic
def handle_approval(
    submission: FormSubmission, task: ApprovalTask, workflow: WorkflowDefinition
) -> None:
    """Advance the workflow after an approval event on a staged task."""
    # Derive the workflow from the task's stage when available, so that
    # multi-workflow (parallel track) forms advance the correct track.
    if task.workflow_stage and task.workflow_stage.workflow_id:
        workflow = task.workflow_stage.workflow
    due_date = _due_date_for(workflow)

    if task.workflow_stage:
        stage = task.workflow_stage
        stages = list(workflow.stages.order_by("order", "id"))

        is_manager_task = (
            task.assigned_to_id is not None and "manager" in task.step_name.lower()
        )

        if is_manager_task:
            # Manager gate passed — now create group tasks for same stage
            groups = list(
                stage.approval_groups.all().order_by("stageapprovalgroup__position")
            )
            if not groups:
                _advance_to_next_stage(
                    submission, workflow, stages, stage.order, due_date
                )
                return
            if stage.approval_logic == "sequence":
                g = groups[0]
                new_task = ApprovalTask.objects.create(
                    submission=submission,
                    assigned_group=g,
                    workflow_stage=stage,
                    stage_number=stage.order,
                    step_name=f"Stage {stage.order} (Step 1 of {len(groups)})",
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
                        stage_number=stage.order,
                        step_name=f"Stage {stage.order}",
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
            _advance_to_next_stage(submission, workflow, stages, stage.order, due_date)

        elif logic == "all":
            # Advance only when all group tasks in this stage are done;
            # _advance_to_next_stage will also check parallel sibling stages.
            if not submission.approval_tasks.filter(
                workflow_stage=stage,
                status="pending",
                assigned_group__isnull=False,
            ).exists():
                _advance_to_next_stage(
                    submission, workflow, stages, stage.order, due_date
                )

        elif logic == "sequence":
            groups = list(
                stage.approval_groups.all().order_by("stageapprovalgroup__position")
            )
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
                    stage_number=stage.order,
                    step_name=f"Stage {stage.order} (Step {idx + 2} of {len(groups)})",
                    step_number=idx + 2,
                    status="pending",
                    due_date=due_date,
                )
                _notify_task_request(new_task)
            else:
                _advance_to_next_stage(
                    submission, workflow, stages, stage.order, due_date
                )

        return

    # No workflow stage — task has no stage context; just finalize.
    _finalize_submission(submission)


@transaction.atomic
def handle_rejection(
    submission: FormSubmission, task: ApprovalTask, workflow: WorkflowDefinition
) -> None:
    """Handle a rejection event on an approval task.

    Semantics depend on the stage's ``approval_logic``:

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
        logic = "all"
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
    """
    # Execute new post-submission actions
    execute_post_submission_actions(submission, "on_approve")

    # Execute file workflow hooks for approval
    execute_file_workflow_hooks(submission, "on_approve")


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


# ---------------------------------------------------------------------------
# Sub-workflow engine
# ---------------------------------------------------------------------------


def _maybe_set_approved_pending(submission: FormSubmission) -> None:
    """Flip parent to approved_pending if non-detached sub-workflow instances are running."""
    if submission.status != "approved":
        return
    try:
        config = submission.form_definition.workflow.sub_workflow_config
    except Exception:
        return
    if config.detached:
        return
    if submission.sub_workflows.filter(status__in=["pending", "in_progress"]).exists():
        submission.status = "approved_pending"
        submission.save(update_fields=["status"])


def _promote_parent_if_complete(submission: FormSubmission) -> None:
    """Promote parent from approved_pending to approved when all sub-workflows finish."""
    if submission.status != "approved_pending":
        return
    if submission.sub_workflows.filter(status__in=["pending", "in_progress"]).exists():
        return
    submission.status = "approved"
    submission.save(update_fields=["status"])
    logger.info(
        "Submission %s promoted to approved — all sub-workflows complete.",
        submission.id,
    )


def _finalize_sub_workflow(instance: SubWorkflowInstance) -> None:
    """Mark a sub-workflow instance as approved, then promote parent if all complete."""
    instance.status = "approved"
    instance.completed_at = timezone.now()
    instance.save(update_fields=["status", "completed_at"])

    _promote_parent_if_complete(instance.parent_submission)


def _reject_sub_workflow(instance: SubWorkflowInstance) -> None:
    """Mark a sub-workflow instance as rejected and cancel its pending tasks.

    If the sub-workflow config has reject_parent=True, immediately reject the
    parent submission and cancel all sibling sub-workflow instances.
    Otherwise, treat the rejection as a completion and promote the parent to
    'approved' if all other instances are now finished.
    """
    instance.status = "rejected"
    instance.completed_at = timezone.now()
    instance.save(update_fields=["status", "completed_at"])
    instance.approval_tasks.filter(status="pending").update(status="skipped")

    submission = instance.parent_submission

    try:
        config = submission.form_definition.workflow.sub_workflow_config
        reject_parent = config.reject_parent
    except Exception:
        reject_parent = False

    if reject_parent:
        # Cancel all sibling sub-workflow instances that are still running
        siblings = submission.sub_workflows.exclude(pk=instance.pk).filter(
            status__in=["pending", "in_progress"]
        )
        for sibling in siblings:
            sibling.status = "rejected"
            sibling.completed_at = timezone.now()
            sibling.save(update_fields=["status", "completed_at"])
            sibling.approval_tasks.filter(status="pending").update(status="skipped")

        if submission.status in ("approved_pending", "approved"):
            submission.status = "rejected"
            submission.save(update_fields=["status"])
            logger.info(
                "Submission %s rejected — sub-workflow %s rejection propagated to parent.",
                submission.id,
                instance.id,
            )
    else:
        # Rejection counts as completion — promote parent if nothing else is pending.
        _promote_parent_if_complete(submission)


def _create_sub_workflow_stage_tasks(
    instance: SubWorkflowInstance,
    stage: WorkflowStage,
    due_date,
) -> None:
    """Create ApprovalTask rows for one stage of a sub-workflow instance."""
    submission = instance.parent_submission
    stage_num = stage.order
    groups = list(stage.approval_groups.all().order_by("stageapprovalgroup__position"))

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
                sub_workflow_instance=instance,
                assigned_to=manager,
                workflow_stage=stage,
                stage_number=stage_num,
                step_name=f"{instance.label} – Stage {stage_num}",
                status="pending",
                due_date=due_date,
            )
            instance.status = "in_progress"
            instance.save(update_fields=["status"])
            manager_task_created = True
            _notify_task_request(task)
        else:
            logger.info(
                "Sub-workflow manager approval required but manager not found for user %s (stage %d)",
                submission.submitter,
                stage_num,
            )

    if manager_task_created:
        return

    if not groups:
        return

    instance.status = "in_progress"
    instance.save(update_fields=["status"])

    if stage.approval_logic == "sequence":
        g = groups[0]
        task = ApprovalTask.objects.create(
            submission=submission,
            sub_workflow_instance=instance,
            assigned_group=g,
            workflow_stage=stage,
            stage_number=stage_num,
            step_name=f"{instance.label} – Stage {stage_num} (Step 1 of {len(groups)})",
            step_number=1,
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
    else:
        for g in groups:
            task = ApprovalTask.objects.create(
                submission=submission,
                sub_workflow_instance=instance,
                assigned_group=g,
                workflow_stage=stage,
                stage_number=stage_num,
                step_name=f"{instance.label} – Stage {stage_num}",
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(task)


def _advance_sub_workflow(
    instance: SubWorkflowInstance,
    stages: list,
    current_order: int,
    due_date,
) -> None:
    """Advance to the next stage of a sub-workflow, or finalize if none remain."""
    for sibling in (s for s in stages if s.order == current_order):
        if instance.approval_tasks.filter(
            workflow_stage=sibling, status="pending"
        ).exists():
            return

    future = [s for s in stages if s.order > current_order]
    if not future:
        _finalize_sub_workflow(instance)
        return

    next_order = future[0].order
    for stage in (s for s in future if s.order == next_order):
        _create_sub_workflow_stage_tasks(instance, stage, due_date)


def _spawn_sub_workflows_for_trigger(submission: FormSubmission, trigger: str) -> None:
    """Spawn sub-workflow instances if a SubWorkflowDefinition exists with matching trigger."""
    workflow = getattr(submission.form_definition, "workflow", None)
    if not workflow:
        return
    try:
        config = workflow.sub_workflow_config
    except SubWorkflowDefinition.DoesNotExist:
        return
    if config.trigger != trigger:
        return

    raw = submission.form_data.get(config.count_field)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "SubWorkflow count_field '%s' value %r is not a valid integer for submission %s",
            config.count_field,
            raw,
            submission.id,
        )
        return

    sub_wf = config.sub_workflow
    stages = list(sub_wf.stages.order_by("order", "id"))
    due_date = _due_date_for(sub_wf)

    for i in range(1, count + 1):
        instance, created = SubWorkflowInstance.objects.get_or_create(
            parent_submission=submission,
            definition=config,
            index=i,
            defaults={"status": "pending"},
        )
        if not created:
            continue  # already spawned (e.g. on resubmit)

        if stages:
            first_order = stages[0].order
            for stage in (s for s in stages if s.order == first_order):
                _create_sub_workflow_stage_tasks(instance, stage, due_date)
        else:
            _finalize_sub_workflow(instance)


@transaction.atomic
def handle_sub_workflow_approval(task: ApprovalTask) -> None:
    """Advance a sub-workflow after an approval event on one of its tasks."""
    instance = task.sub_workflow_instance
    sub_wf = instance.definition.sub_workflow
    stages = list(sub_wf.stages.order_by("order", "id"))
    due_date = _due_date_for(sub_wf)
    stage = task.workflow_stage

    is_manager_task = (
        task.assigned_to_id is not None and "manager" in task.step_name.lower()
    )

    if is_manager_task:
        groups = list(
            stage.approval_groups.all().order_by("stageapprovalgroup__position")
        )
        if not groups:
            _advance_sub_workflow(instance, stages, stage.order, due_date)
            return
        if stage.approval_logic == "sequence":
            g = groups[0]
            new_task = ApprovalTask.objects.create(
                submission=instance.parent_submission,
                sub_workflow_instance=instance,
                assigned_group=g,
                workflow_stage=stage,
                stage_number=stage.order,
                step_name=f"{instance.label} – Stage {stage.order} (Step 1 of {len(groups)})",
                step_number=1,
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(new_task)
        else:
            for g in groups:
                new_task = ApprovalTask.objects.create(
                    submission=instance.parent_submission,
                    sub_workflow_instance=instance,
                    assigned_group=g,
                    workflow_stage=stage,
                    stage_number=stage.order,
                    step_name=f"{instance.label} – Stage {stage.order}",
                    status="pending",
                    due_date=due_date,
                )
                _notify_task_request(new_task)
        return

    logic = stage.approval_logic

    if logic == "any":
        instance.approval_tasks.filter(workflow_stage=stage, status="pending").exclude(
            id=task.id
        ).update(status="skipped")
        _advance_sub_workflow(instance, stages, stage.order, due_date)

    elif logic == "all":
        if not instance.approval_tasks.filter(
            workflow_stage=stage, status="pending", assigned_group__isnull=False
        ).exists():
            _advance_sub_workflow(instance, stages, stage.order, due_date)

    elif logic == "sequence":
        groups = list(
            stage.approval_groups.all().order_by("stageapprovalgroup__position")
        )
        ids = [g.id for g in groups]
        try:
            idx = ids.index(task.assigned_group_id)  # type: ignore[arg-type]
        except ValueError:
            idx = len(ids) - 1

        if idx + 1 < len(groups):
            next_group = groups[idx + 1]
            new_task = ApprovalTask.objects.create(
                submission=instance.parent_submission,
                sub_workflow_instance=instance,
                assigned_group=next_group,
                workflow_stage=stage,
                stage_number=stage.order,
                step_name=f"{instance.label} – Stage {stage.order} (Step {idx + 2} of {len(groups)})",
                step_number=idx + 2,
                status="pending",
                due_date=due_date,
            )
            _notify_task_request(new_task)
        else:
            _advance_sub_workflow(instance, stages, stage.order, due_date)


@transaction.atomic
def handle_sub_workflow_rejection(task: ApprovalTask) -> None:
    """Handle rejection of a sub-workflow task."""
    instance = task.sub_workflow_instance
    stage = task.workflow_stage
    logic = stage.approval_logic if stage else "any"
    scope_qs = instance.approval_tasks.filter(workflow_stage=stage)

    if logic == "any":
        if scope_qs.filter(status="approved").exists():
            return
        if scope_qs.filter(status="pending").exists():
            return
        _reject_sub_workflow(instance)
    else:
        # "all" or "sequence" — one rejection vetoes immediately
        _reject_sub_workflow(instance)
