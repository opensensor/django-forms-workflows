"""
Advanced reporting and analytics dashboard views.

Provides submission volume, approval turnaround, bottleneck stage
analysis, and status breakdowns — all computed from existing
FormSubmission, ApprovalTask, and WorkflowStage data.
"""

import csv
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, Max, Min
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import ApprovalTask, FormDefinition, FormSubmission


@login_required
def analytics_export_csv(request):
    """Export analytics summary data as CSV."""
    range_days = int(request.GET.get("days", 90))
    cutoff = timezone.now() - timedelta(days=range_days)
    form_slug = request.GET.get("form", "")

    submissions_qs = FormSubmission.objects.exclude(status="draft")
    if form_slug:
        submissions_qs = submissions_qs.filter(form_definition__slug=form_slug)

    submissions_in_range = submissions_qs.filter(created_at__gte=cutoff)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="analytics_{range_days}d.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(["Date", "Form", "Status", "Submitter", "Submission ID"])
    for sub in submissions_in_range.select_related(
        "form_definition", "submitter"
    ).order_by("-created_at"):
        writer.writerow(
            [
                sub.created_at.strftime("%Y-%m-%d %H:%M"),
                sub.form_definition.name if sub.form_definition else "",
                sub.status,
                (
                    sub.submitter.get_full_name() or sub.submitter.username
                    if sub.submitter
                    else "Anonymous"
                ),
                sub.id,
            ]
        )

    return response


@login_required
def analytics_dashboard(request):
    """Render the analytics dashboard with submission & approval metrics."""

    # ── Time range filter ───────────────────────────────────────────────
    range_days = int(request.GET.get("days", 90))
    cutoff = timezone.now() - timedelta(days=range_days)
    prev_cutoff = cutoff - timedelta(days=range_days)  # Previous period
    form_slug = request.GET.get("form", "")

    # Base querysets
    submissions_qs = FormSubmission.objects.exclude(status="draft")
    tasks_qs = ApprovalTask.objects.all()

    if form_slug:
        submissions_qs = submissions_qs.filter(form_definition__slug=form_slug)
        tasks_qs = tasks_qs.filter(submission__form_definition__slug=form_slug)

    submissions_in_range = submissions_qs.filter(created_at__gte=cutoff)
    submissions_prev = submissions_qs.filter(
        created_at__gte=prev_cutoff, created_at__lt=cutoff
    )
    tasks_in_range = tasks_qs.filter(created_at__gte=cutoff)

    # ── 1. Summary cards ────────────────────────────────────────────────
    total_submissions = submissions_in_range.count()
    prev_total = submissions_prev.count()

    status_counts = dict(
        submissions_in_range.values_list("status")
        .annotate(c=Count("id"))
        .values_list("status", "c")
    )
    prev_status_counts = dict(
        submissions_prev.values_list("status")
        .annotate(c=Count("id"))
        .values_list("status", "c")
    )

    pending_count = status_counts.get("pending_approval", 0) + status_counts.get(
        "submitted", 0
    )
    approved_count = status_counts.get("approved", 0)
    rejected_count = status_counts.get("rejected", 0)
    withdrawn_count = status_counts.get("withdrawn", 0)

    prev_approved = prev_status_counts.get("approved", 0)
    prev_rejected = prev_status_counts.get("rejected", 0)

    # ── 1b. Period-over-period comparison ───────────────────────────────
    def _pct_change(current, previous):
        if previous == 0:
            return None  # Can't compute change from zero
        return round(((current - previous) / previous) * 100, 1)

    total_change = _pct_change(total_submissions, prev_total)
    approved_change = _pct_change(approved_count, prev_approved)
    rejected_change = _pct_change(rejected_count, prev_rejected)

    # ── 1c. Approval rate ───────────────────────────────────────────────
    decided = approved_count + rejected_count
    approval_rate = round((approved_count / decided) * 100, 1) if decided > 0 else None
    prev_decided = prev_approved + prev_rejected
    prev_approval_rate = (
        round((prev_approved / prev_decided) * 100, 1) if prev_decided > 0 else None
    )
    approval_rate_change = (
        round(approval_rate - prev_approval_rate, 1)
        if approval_rate is not None and prev_approval_rate is not None
        else None
    )

    # ── 2. Submissions per day (for line chart) ─────────────────────────
    daily_submissions = list(
        submissions_in_range.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )

    # ── 3. Submissions per month (bar chart) ────────────────────────────
    monthly_submissions = list(
        submissions_qs.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    # Keep last 12 months
    monthly_submissions = monthly_submissions[-12:]

    # ── 4. Submissions by form (horizontal bar) ─────────────────────────
    by_form = list(
        submissions_in_range.values("form_definition__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:15]
    )

    # ── 5. Status breakdown (doughnut) ──────────────────────────────────
    status_breakdown = list(
        submissions_in_range.values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # ── 6. Approval turnaround time ─────────────────────────────────────
    completed_tasks = tasks_in_range.filter(
        completed_at__isnull=False, created_at__isnull=False
    ).annotate(turnaround=F("completed_at") - F("created_at"))

    turnaround_stats = completed_tasks.aggregate(
        avg=Avg("turnaround"),
        fastest=Min("turnaround"),
        slowest=Max("turnaround"),
    )

    def _fmt_td(td):
        if not td:
            return "N/A"
        total_hours = td.total_seconds() / 3600
        if total_hours < 1:
            return f"{int(td.total_seconds() / 60)}m"
        if total_hours < 24:
            return f"{total_hours:.1f}h"
        return f"{total_hours / 24:.1f}d"

    turnaround = {
        "avg": _fmt_td(turnaround_stats["avg"]),
        "fastest": _fmt_td(turnaround_stats["fastest"]),
        "slowest": _fmt_td(turnaround_stats["slowest"]),
    }

    # ── 7. Bottleneck stages ────────────────────────────────────────────
    # Stages with the most pending tasks right now
    bottleneck_stages = list(
        ApprovalTask.objects.filter(status="pending", workflow_stage__isnull=False)
        .values(
            "workflow_stage__name", "workflow_stage__workflow__form_definition__name"
        )
        .annotate(pending=Count("id"))
        .order_by("-pending")[:10]
    )

    # ── 8. Approval turnaround by stage (for table) ─────────────────────
    stage_turnaround = list(
        completed_tasks.filter(workflow_stage__isnull=False)
        .values(
            "workflow_stage__name", "workflow_stage__workflow__form_definition__name"
        )
        .annotate(
            avg_hours=Avg("turnaround"),
            task_count=Count("id"),
        )
        .order_by("-avg_hours")[:15]
    )
    for row in stage_turnaround:
        row["avg_display"] = _fmt_td(row["avg_hours"])

    # ── 9. Top approvers ────────────────────────────────────────────────
    top_approvers = list(
        tasks_in_range.filter(completed_by__isnull=False)
        .values(
            "completed_by__username",
            "completed_by__first_name",
            "completed_by__last_name",
        )
        .annotate(completed=Count("id"))
        .order_by("-completed")[:10]
    )

    # ── Available forms for filter dropdown ─────────────────────────────
    available_forms = list(
        FormDefinition.objects.filter(is_active=True)
        .values_list("slug", "name")
        .order_by("name")
    )

    # ── 10. Overdue tasks ───────────────────────────────────────────────
    overdue_count = ApprovalTask.objects.filter(
        status="pending",
        due_date__isnull=False,
        due_date__lt=timezone.now(),
    ).count()

    # ── Serialize chart data as JSON (dates → strings) ─────────────────
    def _chart_json(data):
        """Convert queryset-style dicts with date keys to JSON-safe strings."""
        serializable = []
        for row in data:
            clean = {}
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
                else:
                    clean[k] = v
            serializable.append(clean)
        return mark_safe(json.dumps(serializable))

    context = {
        "range_days": range_days,
        "form_slug": form_slug,
        "available_forms": available_forms,
        # Summary cards
        "total_submissions": total_submissions,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "withdrawn_count": withdrawn_count,
        "overdue_count": overdue_count,
        # Period comparison
        "total_change": total_change,
        "approved_change": approved_change,
        "rejected_change": rejected_change,
        "approval_rate": approval_rate,
        "approval_rate_change": approval_rate_change,
        # Charts (JSON-serialized for Chart.js)
        "daily_submissions_json": _chart_json(daily_submissions),
        "monthly_submissions_json": _chart_json(monthly_submissions),
        "by_form_json": _chart_json(by_form),
        "status_breakdown_json": _chart_json(status_breakdown),
        # Approval metrics
        "turnaround": turnaround,
        "bottleneck_stages": bottleneck_stages,
        "stage_turnaround": stage_turnaround,
        "top_approvers": top_approvers,
    }

    return render(
        request,
        "django_forms_workflows/analytics_dashboard.html",
        context,
    )
