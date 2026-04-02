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


def _dispatch_notification_rules(
    submission: FormSubmission, event: str, task_id: int | None = None
) -> None:
    """Dispatch all NotificationRule records for the given event.

    Uses Celery when available; falls back to synchronous dispatch.
    """
    # --- Unified NotificationRule dispatch ---
    try:
        from .tasks import send_notification_rules

        def _fire_rules() -> None:
            try:
                send_notification_rules.delay(submission.id, event, task_id)
            except Exception:
                logger.warning(
                    "NotificationRule '%s' fell back to synchronous for submission %s",
                    event,
                    submission.id,
                )
                send_notification_rules(submission.id, event, task_id)

        transaction.on_commit(_fire_rules)
    except Exception:
        logger.warning(
            "Could not dispatch NotificationRule '%s' for submission %s",
            event,
            submission.id,
        )


def _dispatch_workflow_webhooks(
    submission: FormSubmission,
    event: str,
    *,
    task_id: int | None = None,
    workflow_id: int | None = None,
    target_stage_id: int | None = None,
) -> None:
    """Dispatch first-class webhook deliveries for a workflow lifecycle event."""
    try:
        from .tasks import dispatch_workflow_webhooks

        def _fire_webhooks() -> None:
            try:
                dispatch_workflow_webhooks.delay(
                    submission.id,
                    event,
                    task_id,
                    workflow_id,
                    target_stage_id,
                )
            except Exception:
                logger.warning(
                    "Webhook '%s' fell back to synchronous dispatch for submission %s",
                    event,
                    submission.id,
                )
                dispatch_workflow_webhooks(
                    submission.id,
                    event,
                    task_id,
                    workflow_id,
                    target_stage_id,
                )

        transaction.on_commit(_fire_webhooks)
    except Exception:
        logger.warning(
            "Could not dispatch webhook '%s' for submission %s",
            event,
            submission.id,
        )


def _notify_submission_created(submission: FormSubmission) -> None:
    _dispatch_notification_rules(submission, "submission_received")
    _dispatch_workflow_webhooks(submission, "submission.created")


def _notify_task_request(task: ApprovalTask) -> None:
    """Fire approval_request notifications for a newly activated task.

    All notification behaviour is driven by NotificationRule records.
    The legacy built-in ``send_approval_request`` task is no longer
    dispatched here — a data migration creates equivalent rules for
    every existing workflow so that approvers continue to receive
    emails.
    """
    _dispatch_notification_rules(task.submission, "approval_request", task_id=task.id)
    _dispatch_workflow_webhooks(
        task.submission,
        "task.created",
        task_id=task.id,
        workflow_id=task.workflow_stage.workflow_id if task.workflow_stage_id else None,
    )


def _notify_final_approval(submission: FormSubmission) -> None:
    _dispatch_notification_rules(submission, "workflow_approved")
    _dispatch_workflow_webhooks(submission, "submission.approved")


def _notify_rejection(submission: FormSubmission) -> None:
    _dispatch_notification_rules(submission, "workflow_denied")
    _dispatch_workflow_webhooks(submission, "submission.rejected")


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
    # hold the parent at "pending_approval" until they all complete.
    try:
        _maybe_set_pending_approval(submission)
    except Exception as e:
        logger.error("Error setting pending_approval status: %s", e, exc_info=True)


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


def _resolve_dynamic_assignee(submission: FormSubmission, stage: WorkflowStage):
    """Return the User matching the form-field value on this stage, or None.

    Reads the value stored in ``submission.form_data[stage.assignee_form_field]``
    and resolves it to a Django User according to ``stage.assignee_lookup_type``:

    * ``email``     – ``User.objects.get(email__iexact=value)``
    * ``username``  – ``User.objects.get(username__iexact=value)``
    * ``full_name`` – splits on whitespace, matches first_name + last_name
    * ``ldap``      – searches Active Directory by display name, auto-provisions
                      the Django User if not yet in the local database

    Returns ``None`` (falls back to group assignment) when the field is empty,
    the value cannot be resolved, or no unique match is found.
    """
    if not stage.assignee_form_field:
        return None
    form_data = submission.form_data or {}
    field_value = str(form_data.get(stage.assignee_form_field, "")).strip()
    if not field_value:
        return None

    lookup_type = stage.assignee_lookup_type or "email"
    from django.contrib.auth import get_user_model

    user_model = get_user_model()

    if lookup_type == "email":
        return _lookup_by_email(user_model, field_value, stage, submission)
    if lookup_type == "username":
        return _lookup_by_username(user_model, field_value, stage, submission)
    if lookup_type == "full_name":
        return _lookup_by_full_name(user_model, field_value, stage, submission)
    if lookup_type == "ldap":
        return _lookup_by_ldap(user_model, field_value, stage, submission)
    logger.warning(
        "Unknown assignee_lookup_type '%s' on stage '%s'; "
        "falling back to group assignment.",
        lookup_type,
        stage.name,
    )
    return None


def _lookup_by_email(user_model, value, stage, submission):
    """Resolve assignee by email address."""
    if "@" not in value:
        return None
    try:
        return user_model.objects.get(email__iexact=value)
    except user_model.DoesNotExist:
        logger.info(
            "Dynamic assignee lookup (email): no user with email '%s' "
            "(stage '%s', submission %s); falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
    except user_model.MultipleObjectsReturned:
        logger.warning(
            "Dynamic assignee lookup (email): multiple users with email '%s' "
            "(stage '%s', submission %s); falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
    return None


def _lookup_by_username(user_model, value, stage, submission):
    """Resolve assignee by username (sAMAccountName)."""
    try:
        return user_model.objects.get(username__iexact=value)
    except user_model.DoesNotExist:
        logger.info(
            "Dynamic assignee lookup (username): no user '%s' "
            "(stage '%s', submission %s); falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
    except user_model.MultipleObjectsReturned:
        logger.warning(
            "Dynamic assignee lookup (username): multiple users '%s' "
            "(stage '%s', submission %s); falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
    return None


def _lookup_by_full_name(user_model, value, stage, submission):
    """Resolve assignee by full name (e.g. 'Jane Smith').

    Performs two passes against the Django User table:

    1. **Exact split** – splits the value on the first space into first_name /
       last_name and does ``iexact`` lookups on both columns.  This requires
       that ``auth_user.first_name`` and ``auth_user.last_name`` are populated.

    When multiple users share the same name, the function attempts to
    disambiguate by narrowing the queryset to members of the stage's
    approval groups (when ``validate_assignee_group`` is enabled).  If
    exactly one match remains after filtering, that user is returned.

    .. important::
        For sites using **Google SSO exclusively**, Django's first_name /
        last_name fields are only populated when the Google SAML app is
        configured to send those attributes *and* ``social_core``'s
        ``user_details`` pipeline step maps them.  If those attributes are not
        sent, both columns will be empty and this lookup will always fail.

        In that scenario, prefer the ``ldap`` lookup type, which queries
        Active Directory directly by display name and is independent of what
        is stored in the Django User table.

    2. **LDAP fallback** – if no match is found locally *and* LDAP is
       configured, falls through to ``_lookup_by_ldap`` so the name is
       resolved from Active Directory and the user is JIT-provisioned if
       not yet in the system.
    """
    parts = value.split()

    # Build the base queryset for name matching
    if len(parts) >= 2:
        first_name = parts[0]
        last_name = " ".join(parts[1:])
        qs = user_model.objects.filter(
            first_name__iexact=first_name, last_name__iexact=last_name
        )
    else:
        first_name = None
        last_name = value
        qs = user_model.objects.filter(last_name__iexact=value)

    matches = list(qs[:3])  # fetch up to 3 to detect duplicates cheaply

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        # Multiple users share this name — try to disambiguate by
        # restricting to members of the stage's approval groups.
        approval_groups = list(stage.approval_groups.all())
        if approval_groups:
            group_ids = {g.pk for g in approval_groups}
            narrowed = [
                u for u in matches if u.groups.filter(pk__in=group_ids).exists()
            ]
            if len(narrowed) == 1:
                logger.info(
                    "Dynamic assignee lookup (full_name): multiple users matching '%s' "
                    "but exactly one (%s) is in the stage approval groups "
                    "(stage '%s', submission %s).",
                    value,
                    narrowed[0].username,
                    stage.name,
                    submission.id,
                )
                return narrowed[0]

        # Still ambiguous — fall back to group assignment
        logger.warning(
            "Dynamic assignee lookup (full_name): multiple users matching '%s' "
            "(stage '%s', submission %s); cannot disambiguate — "
            "falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
        return None

    # No match found — fall through to LDAP
    logger.info(
        "Dynamic assignee lookup (full_name): '%s' not found in Django User table "
        "(first_name/last_name may not be populated for SSO-only users); "
        "attempting LDAP lookup (stage '%s', submission %s).",
        value,
        stage.name,
        submission.id,
    )
    return _lookup_by_ldap(user_model, value, stage, submission)


def _lookup_by_ldap(user_model, value, stage, submission):
    """Resolve assignee via LDAP search by display name, with JIT user provisioning.

    Searches Active Directory for users matching the display name.  If exactly
    one match is found and the user does not yet exist in Django, the User
    record is auto-created so they can later authenticate via SSO seamlessly.
    """
    try:
        from .ldap_backend import search_ldap_users
    except ImportError:
        logger.warning(
            "Dynamic assignee lookup (ldap): ldap_backend not available; "
            "falling back to group assignment."
        )
        return None

    results = search_ldap_users(value, max_results=5)
    if not results:
        logger.info(
            "Dynamic assignee lookup (ldap): no LDAP results for '%s' "
            "(stage '%s', submission %s); falling back to group assignment.",
            value,
            stage.name,
            submission.id,
        )
        return None

    # Try exact display-name match first, then fall back to first result
    match = None
    for r in results:
        full = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
        if (
            full.lower() == value.lower()
            or r.get("username", "").lower() == value.lower()
        ):
            match = r
            break
    if match is None:
        # Only use the single result if exactly one came back
        if len(results) == 1:
            match = results[0]
        else:
            logger.warning(
                "Dynamic assignee lookup (ldap): %d results for '%s' but no exact match "
                "(stage '%s', submission %s); falling back to group assignment.",
                len(results),
                value,
                stage.name,
                submission.id,
            )
            return None

    username = match.get("username", "").strip()
    if not username:
        return None

    # Get or JIT-create the Django User
    jit_created = False
    try:
        user = user_model.objects.get(username__iexact=username)
    except user_model.DoesNotExist:
        # Auto-provision the user so the approval task can be assigned.
        # When they later SSO in, the social-auth pipeline's
        # link_to_existing_user step will match them by username.
        user = user_model.objects.create(
            username=username,
            email=match.get("email", ""),
            first_name=match.get("first_name", ""),
            last_name=match.get("last_name", ""),
            is_active=True,
        )
        jit_created = True
        # Create a profile if the model exists
        try:
            from .models import UserProfile

            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "department": match.get("department", ""),
                    "title": match.get("title", ""),
                },
            )
        except Exception:
            logger.debug(
                "UserProfile creation failed for '%s'; continuing without profile",
                username,
                exc_info=True,
            )
        logger.info(
            "Dynamic assignee lookup (ldap): auto-provisioned user '%s' for "
            "assignee '%s' (stage '%s', submission %s).",
            username,
            value,
            stage.name,
            submission.id,
        )

    # Sync LDAP group memberships so the user has the correct Django permissions.
    # Always do this for JIT-provisioned users (they have no groups yet), and
    # also for existing pre-provisioned users in case their groups have changed
    # since they were last synced.
    try:
        from .sso_backends import sync_user_ldap_groups

        n = sync_user_ldap_groups(user)
        logger.info(
            "Dynamic assignee lookup (ldap): synced %d LDAP groups for user '%s' "
            "(jit_created=%s, stage '%s', submission %s).",
            n,
            username,
            jit_created,
            stage.name,
            submission.id,
        )
    except Exception:
        logger.warning(
            "Dynamic assignee lookup (ldap): could not sync LDAP groups for "
            "user '%s' (stage '%s', submission %s).",
            username,
            stage.name,
            submission.id,
            exc_info=True,
        )

    return user


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

    Dynamic assignment: if ``stage.assignee_form_field`` is set, the engine
    resolves the assignee using the configured ``assignee_lookup_type`` (email,
    username, full_name, or ldap) and creates a single ``assigned_to`` task
    instead of group tasks.  Falls back to the normal group task path when the
    user cannot be resolved.
    """
    stage_num = stage.order
    groups = list(stage.approval_groups.all().order_by("stageapprovalgroup__position"))

    # --- Dynamic assignment (form field → User lookup) ------------------------
    dynamic_assignee = _resolve_dynamic_assignee(submission, stage)
    if dynamic_assignee is not None:
        # Optionally validate the resolved user belongs to a stage approval group
        if stage.validate_assignee_group and groups:
            group_ids = {g.pk for g in groups}
            if not dynamic_assignee.groups.filter(pk__in=group_ids).exists():
                logger.warning(
                    "Dynamic assignee '%s' is not a member of any approval group "
                    "for stage '%s' (submission %s); falling back to group assignment.",
                    dynamic_assignee.username,
                    stage.name,
                    submission.id,
                )
                dynamic_assignee = None  # fall through to normal group assignment

    if dynamic_assignee is not None:
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_to=dynamic_assignee,
            workflow_stage=stage,
            stage_number=stage_num,
            step_name=f"Stage {stage_num}",
            status="pending",
            due_date=due_date,
        )
        _notify_task_request(task)
        return

    # --- Manager-first ordering ----------------------------------------------
    manager_task_created = False
    if stage.requires_manager_approval:
        try:
            from .ldap_backend import get_user_manager
        except Exception:
            get_user_manager = None  # type: ignore
        manager = (
            get_user_manager(submission.submitter)
            if get_user_manager and submission.submitter_id
            else None
        )
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
        first_task = None
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
            if first_task is None:
                first_task = task


def _start_deferred_workflows(submission: FormSubmission) -> bool:
    """Start any on_all_complete workflows that are now eligible.

    Returns True if at least one deferred workflow was started (meaning the
    submission should stay at ``pending_approval``), False otherwise.
    """
    from .conditions import evaluate_conditions as _eval

    form_data = submission.form_data or {}
    deferred = [
        w
        for w in submission.form_definition.workflows.filter(
            requires_approval=True,
            start_trigger="on_all_complete",
        )
        if not w.used_as_sub_workflow.exists()
        and _eval(w.trigger_conditions, form_data)
    ]
    if not deferred:
        return False

    any_started = False
    for workflow in deferred:
        # Skip if tasks already exist for this workflow (idempotency)
        stage_ids = list(workflow.stages.values_list("id", flat=True))
        if (
            stage_ids
            and submission.approval_tasks.filter(
                workflow_stage_id__in=stage_ids,
            ).exists()
        ):
            continue

        due_date = _due_date_for(workflow)
        stages = list(workflow.stages.order_by("order", "id"))
        if not stages:
            continue

        first_order = stages[0].order
        first_order_stages = [
            s
            for s in stages
            if s.order == first_order and _eval(s.trigger_conditions, form_data)
        ]
        for stage in first_order_stages:
            groups = list(stage.approval_groups.all())
            if not stage.requires_manager_approval and not groups:
                continue
            _create_stage_tasks(submission, stage, due_date=due_date)
            any_started = True

    return any_started


def _try_finalize_all_tracks(submission: FormSubmission) -> None:
    """Finalize the submission only when every workflow track is complete.

    A track is complete when it has no pending approval tasks across any of
    its stages.  For single-workflow forms this is equivalent to the old
    ``_finalize_submission`` call.

    When all ``on_submission`` workflows are complete, any ``on_all_complete``
    workflows are started.  The submission is only finalized once those
    deferred workflows also complete.
    """
    # Collect all stage IDs across every workflow on this form
    all_workflows = list(
        submission.form_definition.workflows.filter(requires_approval=True)
    )
    if not all_workflows:
        _finalize_submission(submission)
        return

    # Check whether on_submission workflows are all complete
    on_submission_wfs = [
        w
        for w in all_workflows
        if getattr(w, "start_trigger", "on_submission") == "on_submission"
    ]
    for wf in on_submission_wfs:
        stage_ids = list(wf.stages.values_list("id", flat=True))
        if not stage_ids:
            continue
        if submission.approval_tasks.filter(
            workflow_stage_id__in=stage_ids, status="pending"
        ).exists():
            return  # An on_submission track still has pending work

    # All on_submission tracks are done — start deferred workflows if any
    if _start_deferred_workflows(submission):
        return  # Deferred workflow(s) started; wait for them to complete

    # Check whether on_all_complete workflows (already running) are done
    deferred_wfs = [
        w
        for w in all_workflows
        if getattr(w, "start_trigger", "on_submission") == "on_all_complete"
    ]
    for wf in deferred_wfs:
        stage_ids = list(wf.stages.values_list("id", flat=True))
        if not stage_ids:
            continue
        if submission.approval_tasks.filter(
            workflow_stage_id__in=stage_ids, status="pending"
        ).exists():
            return  # A deferred track still has pending work

    # Everything is complete
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

    # Fire stage_decision notifications for all completed siblings
    for sibling in (s for s in stages if s.order == current_order):
        completed_task = (
            submission.approval_tasks.filter(workflow_stage=sibling)
            .exclude(status="pending")
            .order_by("-completed_at")
            .first()
        )
        _dispatch_notification_rules(
            submission,
            "stage_decision",
            task_id=completed_task.id if completed_task else None,
        )

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

    # Notify submission was received via NotificationRule records.
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
    # Workflows referenced by any SubWorkflowDefinition.sub_workflow are
    # templates — they must only be spawned via _spawn_sub_workflows_for_trigger,
    # never auto-started on submission.
    # Workflows with start_trigger="on_all_complete" are deferred — they only
    # start after every on_submission workflow has finished (see
    # _try_finalize_all_tracks).
    form_data = submission.form_data or {}
    approval_workflows = [
        w
        for w in workflows
        if w.requires_approval
        and not w.used_as_sub_workflow.exists()
        and getattr(w, "start_trigger", "on_submission") == "on_submission"
        and evaluate_conditions(w.trigger_conditions, form_data)
    ]
    if not approval_workflows:
        _finalize_submission(submission)
        return

    if submission.status != "pending_approval":
        submission.status = "pending_approval"
        submission.save(update_fields=["status"])

    any_created = False
    trigger_skipped = False  # a stage with groups existed but its trigger didn't match
    for workflow in approval_workflows:
        due_date = _due_date_for(workflow)
        stages = list(workflow.stages.order_by("order", "id"))
        if not stages:
            continue  # No stages configured for this track

        first_order = stages[0].order
        first_order_all = [s for s in stages if s.order == first_order]
        first_order_stages = [
            s
            for s in first_order_all
            if evaluate_conditions(s.trigger_conditions, form_data)
        ]

        # Detect stages that HAVE approval groups but whose trigger
        # conditions didn't match — this distinguishes a genuine "no
        # stages to run" from a misconfiguration where choices were
        # renamed but triggers were not updated.
        for s in first_order_all:
            if s not in first_order_stages:
                groups = list(s.approval_groups.all())
                if groups or s.requires_manager_approval:
                    trigger_skipped = True

        for stage in first_order_stages:
            groups = list(stage.approval_groups.all())
            if not stage.requires_manager_approval and not groups:
                continue  # empty stage — skip
            _create_stage_tasks(submission, stage, due_date=due_date)
            any_created = True

    if not any_created:
        if trigger_skipped:
            # Non-empty stages exist but their trigger conditions didn't
            # match — likely a configuration issue (e.g. form choices were
            # renamed but stage triggers were not updated).  Leave the
            # submission as pending_approval so it isn't silently
            # auto-approved.
            logger.warning(
                "Submission %s has approval workflows with stages but no "
                "first-order stage trigger conditions matched.  The submission "
                "will remain pending_approval.  Check stage trigger conditions "
                "for workflow(s): %s",
                submission.pk,
                ", ".join(str(w.pk) for w in approval_workflows),
            )
        else:
            # All stages are genuinely empty or all trigger conditions
            # matched but stages had no groups — nothing to approve.
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


@transaction.atomic
def handle_send_back(
    submission: FormSubmission,
    task: ApprovalTask,
    target_stage: WorkflowStage,
) -> None:
    """Return a staged workflow to a prior stage for correction.

    The current task must already be saved with ``status="returned"`` before
    calling this function (the view is responsible for that).

    Steps:
      1. Cancel any other pending tasks at the current stage.
      2. Create fresh tasks for ``target_stage`` (reuses ``_create_stage_tasks``
         so all assignment / notification logic is identical to first activation).
      3. ``FormSubmission.status`` stays ``pending_approval`` throughout — the
         submission is *not* rejected or finalised.
    """
    current_stage = task.workflow_stage
    if current_stage is None:
        logger.warning(
            "handle_send_back called on task %s with no workflow_stage; ignoring.",
            task.id,
        )
        return

    # 1. Cancel parallel sibling tasks still pending at the current stage.
    submission.approval_tasks.filter(
        workflow_stage=current_stage, status="pending"
    ).exclude(id=task.id).update(status="skipped")

    # 2. Create new tasks at the target (prior) stage.
    workflow = target_stage.workflow
    due_date = _due_date_for(workflow)
    _create_stage_tasks(submission, target_stage, due_date)

    logger.info(
        "Submission %s sent back from stage '%s' to stage '%s' by task %s.",
        submission.id,
        current_stage.name,
        target_stage.name,
        task.id,
    )
    _dispatch_workflow_webhooks(
        submission,
        "submission.returned",
        task_id=task.id,
        workflow_id=workflow.id,
        target_stage_id=target_stage.id,
    )


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


def _maybe_set_pending_approval(submission: FormSubmission) -> None:
    """Flip parent to pending_approval if non-detached sub-workflow instances are running."""
    if submission.status != "approved":
        return
    try:
        config = submission.form_definition.workflow.sub_workflow_config
    except Exception:
        return
    if config.detached:
        return
    if submission.sub_workflows.filter(status__in=["pending", "in_progress"]).exists():
        submission.status = "pending_approval"
        submission.save(update_fields=["status"])


def _promote_parent_if_complete(submission: FormSubmission) -> None:
    """Promote parent from pending_approval to approved when all sub-workflows finish."""
    if submission.status != "pending_approval":
        return
    if submission.sub_workflows.filter(status__in=["pending", "in_progress"]).exists():
        return
    submission.status = "approved"
    submission.save(update_fields=["status"])
    logger.info(
        "Submission %s promoted to approved — all sub-workflows complete.",
        submission.id,
    )
    _notify_final_approval(submission)


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

        if submission.status in ("pending_approval", "approved"):
            submission.status = "rejected"
            submission.save(update_fields=["status"])
            logger.info(
                "Submission %s rejected — sub-workflow %s rejection propagated to parent.",
                submission.id,
                instance.id,
            )
            _notify_rejection(submission)
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
        manager = (
            get_user_manager(submission.submitter)
            if get_user_manager and submission.submitter_id
            else None
        )
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


@transaction.atomic
def handle_sub_workflow_send_back(
    task: ApprovalTask,
    target_stage: WorkflowStage,
) -> None:
    """Return a sub-workflow to a prior stage for correction.

    Mirrors ``handle_send_back`` but scoped to the sub-workflow instance.
    The current task must already be saved with ``status="returned"`` before
    calling this function.

    Steps:
      1. Cancel any other pending tasks at the current sub-workflow stage.
      2. Create fresh tasks for ``target_stage`` within the same instance.
      3. The parent ``FormSubmission.status`` is untouched.
    """
    instance = task.sub_workflow_instance
    current_stage = task.workflow_stage
    if instance is None or current_stage is None:
        logger.warning(
            "handle_sub_workflow_send_back called on task %s with no instance/stage; ignoring.",
            task.id,
        )
        return

    # 1. Cancel parallel sibling tasks still pending at the current stage.
    instance.approval_tasks.filter(
        workflow_stage=current_stage, status="pending"
    ).exclude(id=task.id).update(status="skipped")

    # 2. Create new tasks at the target stage within the sub-workflow.
    sub_wf = instance.definition.sub_workflow
    submission = instance.parent_submission
    due_date = _due_date_for(sub_wf)
    _create_sub_workflow_stage_tasks(instance, target_stage, due_date)

    logger.info(
        "Sub-workflow instance %s sent back from stage '%s' to stage '%s' by task %s.",
        instance.id,
        current_stage.name,
        target_stage.name,
        task.id,
    )
    _dispatch_workflow_webhooks(
        submission,
        "submission.returned",
        task_id=task.id,
        workflow_id=sub_wf.id,
        target_stage_id=target_stage.id,
    )
