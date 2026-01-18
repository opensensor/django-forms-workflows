"""
Views for Django Form Workflows

This module provides the core views for form submission, approval workflows,
and submission management.
"""

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import models
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import DynamicForm
from .models import ApprovalTask, AuditLog, FormDefinition, FormSubmission
from .utils import user_can_approve, user_can_submit_form

logger = logging.getLogger(__name__)


@login_required
def form_list(request):
    """List all forms user has access to"""
    user_groups = request.user.groups.all()

    if request.user.is_superuser:
        # Superusers can see all active forms
        forms = FormDefinition.objects.filter(is_active=True)
    else:
        # Get forms where user is in submit_groups or no groups specified
        forms = (
            FormDefinition.objects.filter(is_active=True)
            .filter(
                models.Q(submit_groups__in=user_groups)
                | models.Q(submit_groups__isnull=True)
            )
            .distinct()
        )

    return render(request, "django_forms_workflows/form_list.html", {"forms": forms})


@login_required
def form_submit(request, slug):
    """Submit a form"""
    form_def = get_object_or_404(FormDefinition, slug=slug, is_active=True)

    # Check permissions
    if not user_can_submit_form(request.user, form_def):
        messages.error(request, "You don't have permission to submit this form.")
        return redirect("forms_workflows:form_list")

    # Get draft if exists
    draft = FormSubmission.objects.filter(
        form_definition=form_def, submitter=request.user, status="draft"
    ).first()

    if request.method == "POST":
        form = DynamicForm(
            form_definition=form_def,
            user=request.user,
            data=request.POST,
            files=request.FILES,
        )

        if form.is_valid():
            # Save submission first to get an ID for file storage paths
            submission = draft or FormSubmission(
                form_definition=form_def,
                submitter=request.user,
                submission_ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            # Save to get ID (needed for file paths)
            if not submission.pk:
                submission.form_data = {}  # Temporary empty data
                submission.save()

            # Serialize form data to JSON-compatible format (now with submission ID)
            submission.form_data = serialize_form_data(
                form.cleaned_data, submission_id=submission.pk
            )

            if "save_draft" in request.POST:
                submission.status = "draft"
                submission.save()
                messages.success(request, "Draft saved successfully.")

                # Log audit
                AuditLog.objects.create(
                    action="update" if draft else "create",
                    object_type="FormSubmission",
                    object_id=submission.id,
                    user=request.user,
                    user_ip=get_client_ip(request),
                    comments="Saved as draft",
                )
            else:
                submission.status = "submitted"
                submission.submitted_at = timezone.now()
                submission.save()
                messages.success(request, "Form submitted successfully.")

                # Log audit
                AuditLog.objects.create(
                    action="submit",
                    object_type="FormSubmission",
                    object_id=submission.id,
                    user=request.user,
                    user_ip=get_client_ip(request),
                    comments="Form submitted",
                )

                # Create approval tasks if workflow requires approval
                create_approval_tasks(submission)

            return redirect("forms_workflows:my_submissions")
    else:
        initial_data = draft.form_data if draft else None
        form = DynamicForm(
            form_definition=form_def, user=request.user, initial_data=initial_data
        )

    # Get form enhancements configuration
    import json

    form_enhancements_config = json.dumps(form.get_enhancements_config())

    return render(
        request,
        "django_forms_workflows/form_submit.html",
        {
            "form_def": form_def,
            "form": form,
            "is_draft": draft is not None,
            "form_enhancements_config": form_enhancements_config,
        },
    )


@login_required
@require_http_methods(["POST"])
def form_auto_save(request, slug):
    """Auto-save form draft via AJAX"""
    form_def = get_object_or_404(FormDefinition, slug=slug, is_active=True)

    # Check permissions
    if not user_can_submit_form(request.user, form_def):
        return JsonResponse(
            {"success": False, "error": "Permission denied"}, status=403
        )

    try:
        # Parse JSON data
        data = json.loads(request.body)

        # Get or create draft
        draft, created = FormSubmission.objects.get_or_create(
            form_definition=form_def,
            submitter=request.user,
            status="draft",
            defaults={
                "submission_ip": get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            },
        )

        # Update form data
        draft.form_data = data
        draft.save()

        # Log audit
        AuditLog.objects.create(
            action="auto_save",
            object_type="FormSubmission",
            object_id=draft.id,
            user=request.user,
            user_ip=get_client_ip(request),
            comments="Auto-saved draft",
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Draft saved",
                "draft_id": draft.id,
                "saved_at": draft.created_at.isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Auto-save error for form {slug}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def my_submissions(request):
    """View user's submissions"""
    submissions = (
        FormSubmission.objects.filter(submitter=request.user)
        .select_related("form_definition")
        .order_by("-created_at")
    )

    return render(
        request,
        "django_forms_workflows/my_submissions.html",
        {"submissions": submissions},
    )


@login_required
def submission_detail(request, submission_id):
    """View submission details"""
    submission = get_object_or_404(FormSubmission, id=submission_id)

    # Check permissions - user must be submitter, approver, or admin
    can_view = (
        submission.submitter == request.user
        or request.user.is_superuser
        or user_can_approve(request.user, submission)
        or request.user.groups.filter(
            id__in=submission.form_definition.admin_groups.all()
        ).exists()
    )

    if not can_view:
        return HttpResponseForbidden(
            "You don't have permission to view this submission."
        )

    # Get approval tasks
    approval_tasks = submission.approval_tasks.all().order_by("-created_at")

    return render(
        request,
        "django_forms_workflows/submission_detail.html",
        {"submission": submission, "approval_tasks": approval_tasks},
    )


@login_required
def approval_inbox(request):
    """View pending approvals"""
    # Superusers can see all pending tasks
    if request.user.is_superuser:
        tasks = (
            ApprovalTask.objects.filter(status="pending")
            .select_related("submission__form_definition", "submission__submitter")
            .order_by("-created_at")
        )
    else:
        # Regular users see tasks assigned to them or their groups
        user_groups = request.user.groups.all()
        tasks = (
            ApprovalTask.objects.filter(status="pending")
            .filter(
                models.Q(assigned_to=request.user)
                | models.Q(assigned_group__in=user_groups)
            )
            .select_related("submission__form_definition", "submission__submitter")
            .order_by("-created_at")
        )

    return render(
        request, "django_forms_workflows/approval_inbox.html", {"tasks": tasks}
    )


@login_required
def approve_submission(request, task_id):
    """Approve or reject a submission"""
    task = get_object_or_404(ApprovalTask, id=task_id)

    # Check permission
    can_approve = (
        task.assigned_to == request.user
        or (task.assigned_group and task.assigned_group in request.user.groups.all())
        or request.user.is_superuser
    )

    if not can_approve:
        messages.error(request, "You don't have permission to approve this.")
        return redirect("forms_workflows:approval_inbox")

    if task.status != "pending":
        messages.warning(request, "This task has already been processed.")
        return redirect("forms_workflows:approval_inbox")

    if request.method == "POST":
        decision = request.POST.get("decision")
        comments = request.POST.get("comments", "")

        if decision not in ["approve", "reject"]:
            messages.error(request, "Invalid decision.")
            return redirect("forms_workflows:approve_submission", task_id=task_id)

        # Update task
        task.status = "approved" if decision == "approve" else "rejected"
        task.completed_by = request.user
        task.completed_at = timezone.now()
        task.comments = comments
        task.decision = decision
        task.save()

        # Update submission status
        submission = task.submission
        workflow = submission.form_definition.workflow

        if decision == "reject":
            # Rejection - mark submission as rejected
            submission.status = "rejected"
            submission.completed_at = timezone.now()
            submission.save()

            # Cancel all pending tasks
            submission.approval_tasks.filter(status="pending").update(status="skipped")

            # Execute on_reject post-submission actions
            from .workflow_engine import execute_post_submission_actions

            execute_post_submission_actions(submission, "on_reject")

            # Send rejection notification (if Celery is configured)
            try:
                from .tasks import send_rejection_notification

                send_rejection_notification.delay(submission.id)
            except ImportError:
                logger.warning("Celery tasks not available, skipping notification")
        else:
            # Approval - check workflow logic
            from .workflow_engine import handle_approval

            handle_approval(submission, task, workflow)

        # Log audit
        AuditLog.objects.create(
            action="approve" if decision == "approve" else "reject",
            object_type="FormSubmission",
            object_id=submission.id,
            user=request.user,
            user_ip=get_client_ip(request),
            changes={"task_id": task.id, "comments": comments},
        )

        messages.success(request, f"Submission {decision}d successfully.")
        return redirect("forms_workflows:approval_inbox")

    return render(
        request,
        "django_forms_workflows/approve.html",
        {"task": task, "submission": task.submission},
    )


@login_required
def withdraw_submission(request, submission_id):
    """Withdraw a submission"""
    submission = get_object_or_404(FormSubmission, id=submission_id)

    # Only submitter can withdraw
    if submission.submitter != request.user:
        return HttpResponseForbidden("You can only withdraw your own submissions.")

    # Check if withdrawal is allowed
    if not submission.form_definition.allow_withdrawal:
        messages.error(request, "This form does not allow withdrawal.")
        return redirect(
            "forms_workflows:submission_detail", submission_id=submission_id
        )

    # Can only withdraw if not yet approved/rejected
    if submission.status in ["approved", "rejected", "withdrawn"]:
        messages.error(request, "This submission cannot be withdrawn.")
        return redirect(
            "forms_workflows:submission_detail", submission_id=submission_id
        )

    if request.method == "POST":
        submission.status = "withdrawn"
        submission.completed_at = timezone.now()
        submission.save()

        # Cancel pending approval tasks
        submission.approval_tasks.filter(status="pending").update(status="skipped")

        # Log audit
        AuditLog.objects.create(
            action="withdraw",
            object_type="FormSubmission",
            object_id=submission.id,
            user=request.user,
            user_ip=get_client_ip(request),
            comments="Submission withdrawn by submitter",
        )

        messages.success(request, "Submission withdrawn successfully.")
        return redirect("forms_workflows:my_submissions")

    return render(
        request,
        "django_forms_workflows/withdraw_confirm.html",
        {"submission": submission},
    )


# Helper functions


def serialize_form_data(data, submission_id=None):
    """
    Convert form data to JSON-serializable format.

    For file uploads, saves the file to storage and stores both
    the filename and the storage path.
    """
    serialized = {}
    for key, value in data.items():
        if isinstance(value, date | datetime | time):
            serialized[key] = value.isoformat()
        elif isinstance(value, Decimal):
            serialized[key] = str(value)
        elif hasattr(value, "read"):  # File upload (InMemoryUploadedFile or similar)
            # Save file to storage (uses S3/Spaces if configured)
            file_path = save_uploaded_file(value, key, submission_id)
            if file_path:
                # Get the URL for the saved file
                try:
                    file_url = default_storage.url(file_path)
                except Exception:
                    file_url = None

                serialized[key] = {
                    "filename": value.name,
                    "path": file_path,
                    "url": file_url,
                    "size": value.size if hasattr(value, "size") else 0,
                    "content_type": (
                        value.content_type
                        if hasattr(value, "content_type")
                        else "application/octet-stream"
                    ),
                }
            else:
                # Fallback if save fails
                serialized[key] = value.name
        else:
            serialized[key] = value
    return serialized


def save_uploaded_file(file_obj, field_name, submission_id=None):
    """
    Save an uploaded file to storage.

    Returns the storage path or None if save fails.
    """
    try:
        # Generate a unique path for the file
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        sub_id = submission_id or "temp"

        # Sanitize filename
        original_name = file_obj.name
        # Remove any path components from the filename
        safe_name = original_name.replace("/", "_").replace("\\", "_")

        # Build storage path: uploads/<submission_id>/<timestamp>_<filename>
        storage_path = f"uploads/{sub_id}/{field_name}_{timestamp}_{safe_name}"

        # Save to storage (will use S3/Spaces if configured via STORAGES)
        saved_path = default_storage.save(storage_path, file_obj)

        logger.info(f"Saved uploaded file to: {saved_path}")
        return saved_path

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}", exc_info=True)
        return None


def get_file_url(file_info):
    """
    Get a URL for accessing an uploaded file.

    Handles both old format (just filename) and new format (dict with path).
    """
    if isinstance(file_info, dict) and "path" in file_info:
        try:
            return default_storage.url(file_info["path"])
        except Exception as e:
            logger.error(f"Failed to get file URL: {e}")
            return None
    elif isinstance(file_info, str):
        # Old format - just filename, can't generate URL
        return None
    return None


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def create_approval_tasks(submission):
    """
    Create approval tasks based on workflow definition.

    This is a placeholder - the actual implementation should be in workflow_engine.py
    """
    try:
        from .workflow_engine import create_workflow_tasks

        create_workflow_tasks(submission)
    except ImportError:
        logger.warning("Workflow engine not available")
        # No approval needed, mark as approved
        submission.status = "approved"
        submission.completed_at = timezone.now()
        submission.save()
