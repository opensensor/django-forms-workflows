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
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import DynamicForm
from .models import ApprovalTask, AuditLog, FormDefinition, FormSubmission
from .utils import user_can_approve, user_can_submit_form

logger = logging.getLogger(__name__)


def _build_grouped_forms(forms):
    """
    Return an ordered list of ``(category_or_None, [form, ...])`` tuples.

    Forms with a category are sorted first by ``category.order``, then by
    ``category.name``, then by form ``name``.  Uncategorised forms are
    appended at the end under ``None``.
    """
    ordered = forms.order_by(
        "category__order",
        "category__name",
        "name",
    ).select_related("category")

    seen_keys = {}  # category pk -> index in results list
    results = []  # list of [category_or_None, [forms]]
    uncategorised = []

    for form in ordered:
        cat = form.category
        if cat is None:
            uncategorised.append(form)
            continue
        if cat.pk not in seen_keys:
            seen_keys[cat.pk] = len(results)
            results.append([cat, []])
        results[seen_keys[cat.pk]][1].append(form)

    # Append uncategorised as the final bucket
    if uncategorised:
        results.append([None, uncategorised])

    return [(cat, forms_list) for cat, forms_list in results]


@login_required
def form_list(request):
    """List all active forms the current user has access to.

    For non-staff users two layers of group filtering are applied:

    1. **Form-level** — the user must be in ``submit_groups``, or the form
       has no ``submit_groups`` restriction.
    2. **Category-level** — the user must be in one of the category's
       ``allowed_groups``, or the category has no group restriction, or the
       form has no category at all.

    Staff / superusers bypass both filters and see every active form.

    Context variables
    -----------------
    forms
        Raw queryset (for templates that just want a flat list).
    grouped_forms
        Ordered list of ``(FormCategory | None, [FormDefinition, ...])``.
    """
    if request.user.is_staff or request.user.is_superuser:
        forms = FormDefinition.objects.filter(is_active=True).select_related("category")
    else:
        user_groups = request.user.groups.all()
        forms = (
            FormDefinition.objects.filter(is_active=True)
            # Annotate counts so we can distinguish "no groups" from "some groups"
            .annotate(
                submit_group_count=models.Count("submit_groups", distinct=True),
                category_group_count=models.Count(
                    "category__allowed_groups", distinct=True
                ),
            )
            # Form-level: user in submit_groups OR form has no restriction
            .filter(
                models.Q(submit_groups__in=user_groups) | models.Q(submit_group_count=0)
            )
            # Category-level: no category, or category unrestricted, or user in group
            .filter(
                models.Q(category__isnull=True)
                | models.Q(category_group_count=0)
                | models.Q(category__allowed_groups__in=user_groups)
            )
            .distinct()
            .select_related("category")
        )

    # --- Optional name search ---
    search_query = request.GET.get("q", "").strip()
    if search_query:
        forms = forms.filter(name__icontains=search_query)

    grouped_forms = _build_grouped_forms(forms)

    return render(
        request,
        "django_forms_workflows/form_list.html",
        {
            "forms": forms,
            "grouped_forms": grouped_forms,
            "search_query": search_query,
        },
    )


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
    """View user's submissions, optionally filtered by form category.

    Accepts an optional ``?category=<slug>`` query parameter to narrow the
    submission list to a single form category.  The template also receives a
    ``category_counts`` list so the UI can render a filter-pill bar showing
    how many submissions belong to each category.
    """
    base_submissions = FormSubmission.objects.filter(submitter=request.user)

    # --- Category counts (for the filter bar) ---
    raw_counts = (
        base_submissions.values(
            "form_definition__category__pk",
            "form_definition__category__name",
            "form_definition__category__slug",
            "form_definition__category__icon",
            "form_definition__category__order",
        )
        .annotate(count=models.Count("id"))
        .order_by(
            "form_definition__category__order",
            "form_definition__category__name",
        )
    )

    category_counts = []
    for row in raw_counts:
        slug = row["form_definition__category__slug"]
        if slug:  # only include categorised entries in the filter bar
            category_counts.append(
                {
                    "name": row["form_definition__category__name"],
                    "slug": slug,
                    "icon": row["form_definition__category__icon"] or "",
                    "count": row["count"],
                }
            )

    total_submissions_count = base_submissions.count()

    # --- Apply optional category filter ---
    category_slug = request.GET.get("category", "").strip()
    active_category = None

    if category_slug:
        submissions = base_submissions.filter(
            form_definition__category__slug=category_slug
        )
        active_category = next(
            (c for c in category_counts if c["slug"] == category_slug), None
        )
    else:
        submissions = base_submissions

    # --- Form counts within the active category (for the form-level filter bar) ---
    form_slug = request.GET.get("form", "").strip()
    form_counts = []
    active_form = None

    if category_slug:
        raw_form_counts = (
            submissions.values(
                "form_definition__pk",
                "form_definition__name",
                "form_definition__slug",
            )
            .annotate(count=models.Count("id"))
            .order_by("form_definition__name")
        )
        form_counts = [
            {
                "name": r["form_definition__name"],
                "slug": r["form_definition__slug"],
                "count": r["count"],
            }
            for r in raw_form_counts
            if r["form_definition__slug"]
        ]
        if form_slug:
            submissions = submissions.filter(form_definition__slug=form_slug)
            active_form = next((f for f in form_counts if f["slug"] == form_slug), None)

    submissions = submissions.select_related("form_definition__category").order_by(
        "-created_at"
    )

    return render(
        request,
        "django_forms_workflows/my_submissions.html",
        {
            "submissions": submissions,
            "category_counts": category_counts,
            "active_category": active_category,
            "category_slug": category_slug,
            "total_submissions_count": total_submissions_count,
            "form_counts": form_counts,
            "form_slug": form_slug,
            "active_form": active_form,
        },
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

    # Get approval tasks with related objects for efficient rendering
    approval_tasks = submission.approval_tasks.select_related(
        "workflow_stage", "assigned_to", "assigned_group", "completed_by"
    ).order_by("stage_number", "-created_at")

    # Build stage groups if any tasks are linked to a workflow stage
    stage_groups = None
    if approval_tasks.filter(workflow_stage__isnull=False).exists():
        groups: dict = {}
        for task in approval_tasks:
            stage_key = task.stage_number or 0
            if stage_key not in groups:
                stage_name = (
                    task.workflow_stage.name
                    if task.workflow_stage
                    else f"Stage {stage_key}"
                )
                approval_logic = (
                    task.workflow_stage.approval_logic if task.workflow_stage else "all"
                )
                groups[stage_key] = {
                    "number": stage_key,
                    "name": stage_name,
                    "approval_logic": approval_logic,
                    "tasks": [],
                    "approved_count": 0,
                    "rejected_count": 0,
                    "total_count": 0,
                }
            groups[stage_key]["tasks"].append(task)
            groups[stage_key]["total_count"] += 1
            if task.status == "approved":
                groups[stage_key]["approved_count"] += 1
            elif task.status == "rejected":
                groups[stage_key]["rejected_count"] += 1
        stage_groups = sorted(groups.values(), key=lambda x: x["number"])

    # Resolve fresh presigned URLs for any file-upload fields
    form_data = _resolve_form_data_urls(submission.form_data)
    form_data_ordered = _build_ordered_form_data(submission, form_data)

    return render(
        request,
        "django_forms_workflows/submission_detail.html",
        {
            "submission": submission,
            "approval_tasks": approval_tasks,
            "stage_groups": stage_groups,
            "form_data": form_data,
            "form_data_ordered": form_data_ordered,
        },
    )


@login_required
def approval_inbox(request):
    """View pending approvals, optionally filtered by form category.

    Accepts an optional ``?category=<slug>`` query parameter to narrow the
    task list to a single form category.  The template also receives a
    ``category_counts`` list so the UI can render a filter-pill bar showing
    how many pending tasks belong to each category.
    """
    # Build base queryset of accessible pending tasks (no select_related yet
    # so the values()/annotate() path stays lightweight).
    if request.user.is_superuser:
        base_tasks = ApprovalTask.objects.filter(status="pending")
    else:
        user_groups = request.user.groups.all()
        base_tasks = ApprovalTask.objects.filter(status="pending").filter(
            models.Q(assigned_to=request.user)
            | models.Q(assigned_group__in=user_groups)
        )

    # --- Category counts (for the filter bar) ---
    raw_counts = (
        base_tasks.values(
            "submission__form_definition__category__pk",
            "submission__form_definition__category__name",
            "submission__form_definition__category__slug",
            "submission__form_definition__category__icon",
            "submission__form_definition__category__order",
        )
        .annotate(count=models.Count("id"))
        .order_by(
            "submission__form_definition__category__order",
            "submission__form_definition__category__name",
        )
    )

    category_counts = []
    for row in raw_counts:
        slug = row["submission__form_definition__category__slug"]
        if slug:  # only include categorised entries in the filter bar
            category_counts.append(
                {
                    "name": row["submission__form_definition__category__name"],
                    "slug": slug,
                    "icon": row["submission__form_definition__category__icon"] or "",
                    "count": row["count"],
                }
            )

    total_tasks_count = base_tasks.count()

    # --- Apply optional category filter ---
    category_slug = request.GET.get("category", "").strip()
    active_category = None

    if category_slug:
        display_tasks = base_tasks.filter(
            submission__form_definition__category__slug=category_slug
        )
        active_category = next(
            (c for c in category_counts if c["slug"] == category_slug), None
        )
    else:
        display_tasks = base_tasks

    # --- Form counts within the active category (for the form-level filter bar) ---
    form_slug = request.GET.get("form", "").strip()
    form_counts = []
    active_form = None

    if category_slug:
        raw_form_counts = (
            display_tasks.values(
                "submission__form_definition__pk",
                "submission__form_definition__name",
                "submission__form_definition__slug",
            )
            .annotate(count=models.Count("id"))
            .order_by("submission__form_definition__name")
        )
        form_counts = [
            {
                "name": r["submission__form_definition__name"],
                "slug": r["submission__form_definition__slug"],
                "count": r["count"],
            }
            for r in raw_form_counts
            if r["submission__form_definition__slug"]
        ]
        if form_slug:
            display_tasks = display_tasks.filter(
                submission__form_definition__slug=form_slug
            )
            active_form = next((f for f in form_counts if f["slug"] == form_slug), None)

    display_tasks = display_tasks.select_related(
        "submission__form_definition__category",
        "submission__submitter",
    ).order_by("-created_at")

    return render(
        request,
        "django_forms_workflows/approval_inbox.html",
        {
            "tasks": display_tasks,
            "category_counts": category_counts,
            "active_category": active_category,
            "category_slug": category_slug,
            "total_tasks_count": total_tasks_count,
            "form_counts": form_counts,
            "form_slug": form_slug,
            "active_form": active_form,
        },
    )


@login_required
def approve_submission(request, task_id):
    """Approve or reject a submission"""
    task = get_object_or_404(ApprovalTask, id=task_id)
    submission = task.submission
    form_def = submission.form_definition

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

    # Check if this form has approval step fields for the current step
    has_approval_step_fields = form_def.fields.filter(
        approval_step=task.step_number
    ).exists()
    approval_step_form = None

    if request.method == "POST":
        decision = request.POST.get("decision")
        comments = request.POST.get("comments", "")

        if decision not in ["approve", "reject"]:
            messages.error(request, "Invalid decision.")
            return redirect("forms_workflows:approve_submission", task_id=task_id)

        # If there are approval step fields and decision is approve, validate them
        if has_approval_step_fields and decision == "approve":
            from .forms import ApprovalStepForm

            approval_step_form = ApprovalStepForm(
                form_definition=form_def,
                submission=submission,
                approval_task=task,
                user=request.user,
                data=request.POST,
            )

            if not approval_step_form.is_valid():
                messages.error(
                    request, "Please correct the errors in the approval fields."
                )
                _fd = _resolve_form_data_urls(submission.form_data)
                return render(
                    request,
                    "django_forms_workflows/approve.html",
                    {
                        "task": task,
                        "submission": submission,
                        "approval_step_form": approval_step_form,
                        "has_approval_step_fields": has_approval_step_fields,
                        "form_data": _fd,
                        "form_data_ordered": _build_ordered_form_data(submission, _fd),
                    },
                )

            # Update submission form_data with approval step fields
            submission.form_data = approval_step_form.get_updated_form_data()
            submission.save()

        # Update task
        task.status = "approved" if decision == "approve" else "rejected"
        task.completed_by = request.user
        task.completed_at = timezone.now()
        task.comments = comments
        task.decision = decision
        task.save()

        # Update submission status
        workflow = form_def.workflow

        if decision == "reject":
            from .workflow_engine import handle_rejection

            handle_rejection(submission, task, workflow)
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

    # GET request - create the approval step form if needed
    if has_approval_step_fields:
        from .forms import ApprovalStepForm

        approval_step_form = ApprovalStepForm(
            form_definition=form_def,
            submission=submission,
            approval_task=task,
            user=request.user,
        )

    # Build approval progress context — staged, sequential, or parallel
    approval_steps = []
    approval_step_fields: dict = {}
    all_approval_field_names: list = []
    approval_stages: list = []
    parallel_tasks: list = []
    workflow_mode = "none"
    workflow = form_def.workflow

    if workflow:
        stages = list(workflow.stages.order_by("order"))

        if stages:
            # -------- staged workflow --------
            workflow_mode = "staged"
            current_stage_number = task.stage_number or 1
            all_sub_tasks = list(
                submission.approval_tasks.select_related(
                    "workflow_stage", "assigned_group", "assigned_to"
                ).all()
            )
            tasks_by_stage: dict = {}
            for t in all_sub_tasks:
                key = t.workflow_stage_id
                tasks_by_stage.setdefault(key, []).append(t)

            for i, stage in enumerate(stages, start=1):
                stage_tasks = tasks_by_stage.get(stage.id, [])
                approved_count = sum(1 for t in stage_tasks if t.status == "approved")
                approval_stages.append(
                    {
                        "number": i,
                        "name": stage.name,
                        "approval_logic": stage.approval_logic,
                        "total_stages": len(stages),
                        "is_current": i == current_stage_number,
                        "is_completed": approved_count > 0
                        and not any(t.status == "pending" for t in stage_tasks),
                        "is_rejected": any(t.status == "rejected" for t in stage_tasks),
                        "is_pending": i > current_stage_number,
                        "tasks": stage_tasks,
                        "approved_count": approved_count,
                        "total_count": len(stage_tasks),
                    }
                )

        elif workflow.approval_logic == "sequence":
            # -------- legacy sequential --------
            workflow_mode = "sequence"
            approval_groups = list(workflow.approval_groups.all())
            total_steps = len(approval_groups)
            all_tasks = {t.step_number: t for t in submission.approval_tasks.all()}

            for field in form_def.fields.filter(approval_step__isnull=False).order_by(
                "approval_step", "order"
            ):
                step_num = field.approval_step
                if step_num not in approval_step_fields:
                    approval_step_fields[step_num] = []
                approval_step_fields[step_num].append(
                    {"field_name": field.field_name, "field_label": field.field_label}
                )
                all_approval_field_names.append(field.field_name)

            for idx, group in enumerate(approval_groups, start=1):
                step_task = all_tasks.get(idx)
                approval_steps.append(
                    {
                        "number": idx,
                        "total": total_steps,
                        "group_name": group.name,
                        "is_current": idx == task.step_number,
                        "is_completed": step_task.status == "approved"
                        if step_task
                        else False,
                        "is_rejected": step_task.status == "rejected"
                        if step_task
                        else False,
                        "is_pending": idx > (task.step_number or 0),
                        "task": step_task,
                        "fields": approval_step_fields.get(idx, []),
                    }
                )

        elif workflow.approval_logic in ("all", "any"):
            # -------- legacy parallel --------
            workflow_mode = workflow.approval_logic
            for t in submission.approval_tasks.filter(
                assigned_group__isnull=False
            ).select_related("assigned_group"):
                parallel_tasks.append(
                    {
                        "task": t,
                        "group_name": t.assigned_group.name
                        if t.assigned_group
                        else "—",
                        "is_current": t.id == task.id,
                    }
                )

    # Resolve fresh presigned URLs for any file-upload fields
    form_data = _resolve_form_data_urls(submission.form_data)
    form_data_ordered = _build_ordered_form_data(submission, form_data)

    return render(
        request,
        "django_forms_workflows/approve.html",
        {
            "task": task,
            "submission": submission,
            "approval_step_form": approval_step_form,
            "has_approval_step_fields": has_approval_step_fields,
            # sequential legacy
            "approval_steps": approval_steps,
            "current_step_number": task.step_number,
            "total_steps": len(approval_steps) if approval_steps else 0,
            "approval_field_names": all_approval_field_names,
            # staged
            "approval_stages": approval_stages,
            "current_stage_number": task.stage_number or 1,
            "total_stages": len(approval_stages),
            # parallel legacy
            "parallel_tasks": parallel_tasks,
            # shared
            "workflow_mode": workflow_mode,
            "form_data": form_data,
            "form_data_ordered": form_data_ordered,
        },
    )


@login_required
def completed_approvals(request):
    """View completed submissions where the user was part of the approval workflow.

    Shows submissions with status approved/rejected/withdrawn where the current
    user had an ApprovalTask assigned directly or via group membership.  This
    provides a history / audit view for approvers, which is especially important
    for business-process workflows (e.g. PCN) where data retention matters.

    Accepts an optional ``?category=<slug>`` query parameter and an optional
    ``?form=<slug>`` query parameter for narrowing the list.
    """
    if request.user.is_superuser:
        base_submissions = FormSubmission.objects.filter(
            status__in=["approved", "rejected", "withdrawn"]
        )
    else:
        user_groups = request.user.groups.all()
        base_submissions = (
            FormSubmission.objects.filter(
                status__in=["approved", "rejected", "withdrawn"]
            )
            .filter(
                models.Q(approval_tasks__assigned_to=request.user)
                | models.Q(approval_tasks__assigned_group__in=user_groups)
            )
            .distinct()
        )

    # --- Category counts (for the filter bar) ---
    raw_counts = (
        base_submissions.values(
            "form_definition__category__pk",
            "form_definition__category__name",
            "form_definition__category__slug",
            "form_definition__category__icon",
            "form_definition__category__order",
        )
        .annotate(count=models.Count("id"))
        .order_by(
            "form_definition__category__order",
            "form_definition__category__name",
        )
    )

    category_counts = []
    for row in raw_counts:
        slug = row["form_definition__category__slug"]
        if slug:
            category_counts.append(
                {
                    "name": row["form_definition__category__name"],
                    "slug": slug,
                    "icon": row["form_definition__category__icon"] or "",
                    "count": row["count"],
                }
            )

    total_count = base_submissions.count()

    # --- Apply optional category filter ---
    category_slug = request.GET.get("category", "").strip()
    active_category = None

    if category_slug:
        display_submissions = base_submissions.filter(
            form_definition__category__slug=category_slug
        )
        active_category = next(
            (c for c in category_counts if c["slug"] == category_slug), None
        )
    else:
        display_submissions = base_submissions

    # --- Form counts within the active category (for the form-level filter bar) ---
    form_slug = request.GET.get("form", "").strip()
    form_counts = []
    active_form = None

    if category_slug:
        raw_form_counts = (
            display_submissions.values(
                "form_definition__pk",
                "form_definition__name",
                "form_definition__slug",
            )
            .annotate(count=models.Count("id"))
            .order_by("form_definition__name")
        )
        form_counts = [
            {
                "name": r["form_definition__name"],
                "slug": r["form_definition__slug"],
                "count": r["count"],
            }
            for r in raw_form_counts
            if r["form_definition__slug"]
        ]
        if form_slug:
            display_submissions = display_submissions.filter(
                form_definition__slug=form_slug
            )
            active_form = next((f for f in form_counts if f["slug"] == form_slug), None)

    # --- Status filter (optional) ---
    status_filter = request.GET.get("status", "").strip()
    if status_filter in ["approved", "rejected", "withdrawn"]:
        display_submissions = display_submissions.filter(status=status_filter)

    display_submissions = display_submissions.select_related(
        "form_definition__category",
        "submitter",
    ).order_by("-completed_at", "-submitted_at")

    return render(
        request,
        "django_forms_workflows/completed_approvals.html",
        {
            "submissions": display_submissions,
            "category_counts": category_counts,
            "active_category": active_category,
            "category_slug": category_slug,
            "total_count": total_count,
            "form_counts": form_counts,
            "form_slug": form_slug,
            "active_form": active_form,
            "status_filter": status_filter,
        },
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


@login_required
def submission_pdf(request, submission_id):
    """Generate and serve a PDF of a form submission.

    Respects the ``pdf_generation`` setting on the form definition:
      - ``none``          – PDF download is disabled; returns 403.
      - ``anytime``       – PDF is available as soon as the form is submitted.
      - ``post_approval`` – PDF is only available once the submission is approved.
    """
    submission = get_object_or_404(FormSubmission, id=submission_id)
    form_def = submission.form_definition

    # --- permission check (same as submission_detail) ---
    can_view = (
        submission.submitter == request.user
        or request.user.is_superuser
        or user_can_approve(request.user, submission)
        or request.user.groups.filter(
            id__in=form_def.admin_groups.all()
        ).exists()
    )
    if not can_view:
        return HttpResponseForbidden(
            "You don't have permission to view this submission."
        )

    # --- pdf_generation setting check ---
    pdf_setting = form_def.pdf_generation
    if pdf_setting == "none":
        return HttpResponseForbidden("PDF generation is not enabled for this form.")

    if pdf_setting == "post_approval" and submission.status != "approved":
        return HttpResponseForbidden(
            "PDF is only available after the submission has been approved."
        )

    # --- build ordered data (no presigned URLs needed for PDF) ---
    form_data_ordered = _build_ordered_form_data(submission, submission.form_data or {})

    # --- render HTML template to a string ---
    from django.template.loader import render_to_string

    html_string = render_to_string(
        "django_forms_workflows/submission_pdf.html",
        {
            "submission": submission,
            "form_def": form_def,
            "form_data_ordered": form_data_ordered,
            "request": request,
        },
    )

    # --- convert HTML to PDF using xhtml2pdf ---
    try:
        from io import BytesIO

        from xhtml2pdf import pisa

        buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=buffer)
        if pisa_status.err:
            logger.error(
                "xhtml2pdf error for submission %s: %s",
                submission_id,
                pisa_status.err,
            )
            return HttpResponse(
                "An error occurred while generating the PDF.", status=500
            )
        pdf_bytes = buffer.getvalue()
    except ImportError:
        return HttpResponse(
            "PDF generation requires the xhtml2pdf package. "
            "Please install it with: pip install xhtml2pdf",
            status=501,
        )

    filename = f"submission_{submission_id}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# Helper functions


def serialize_form_data(data, submission_id=None):
    """
    Convert form data to JSON-serializable format.

    For file uploads, saves the file to storage and stores the filename,
    storage path, size, and content-type.  The URL is intentionally NOT
    stored here — presigned S3/Spaces URLs expire and must be generated
    on-demand at render time via ``_resolve_form_data_urls()``.
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
                serialized[key] = {
                    "filename": value.name,
                    "path": file_path,
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


def _build_ordered_form_data(submission, form_data):
    """
    Return form data as an ordered list of dicts, respecting FormField.order.

    The raw ``form_data`` JSON dict preserves insertion order (Python 3.7+),
    but that order reflects when fields were *submitted*, not the declared field
    order on the form.  This helper re-orders the entries so they match the
    field definition ordering configured by the form designer.

    Each returned item has:
      - ``label``: the human-readable field label
      - ``key``:   the field_name / dict key
      - ``value``: the resolved value (may be a file-info dict after URL resolution)
    """
    if not form_data:
        return []

    ordered = []
    seen_keys = set()

    # Walk fields in declared order (sections are skipped – they have no data)
    for field in submission.form_definition.fields.exclude(
        field_type="section"
    ).order_by("order"):
        key = field.field_name
        if key in form_data:
            ordered.append(
                {
                    "label": field.field_label,
                    "key": key,
                    "value": form_data[key],
                }
            )
            seen_keys.add(key)

    # Append any keys in form_data that aren't represented in field definitions
    # (e.g. approval-step fields or legacy entries) so nothing is lost.
    for key, value in form_data.items():
        if key not in seen_keys:
            ordered.append(
                {
                    "label": key.replace("_", " ").title(),
                    "key": key,
                    "value": value,
                }
            )

    return ordered


def _resolve_form_data_urls(form_data):
    """
    Return a copy of form_data with fresh presigned URLs injected for every
    file-upload entry (i.e. any dict value that contains a ``path`` key).

    Presigned S3/Spaces URLs expire and must never be stored in the database.
    This helper is called in views immediately before rendering a template so
    that the template always receives a valid, unexpired URL.

    Values that are not file-upload dicts are passed through unchanged.
    """
    if not form_data:
        return {}
    resolved = {}
    for key, value in form_data.items():
        if isinstance(value, dict) and "path" in value:
            # Build a fresh copy with a newly-generated URL
            entry = dict(value)  # shallow copy so we don't mutate the model field
            entry["url"] = get_file_url(value)  # may be None if storage is unavailable
            resolved[key] = entry
        else:
            resolved[key] = value
    return resolved


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
