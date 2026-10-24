"""Shared authorization and rendering boundaries."""

import json
import time
from functools import wraps

import nh3
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.utils.html import escape

from .models import FormSubmission


def visible_submissions(user):
    """Mirror user_can_view_submission without exposing unrelated records."""
    qs = FormSubmission.objects.all()
    if not user.is_authenticated or not user.is_active:
        return qs.none()
    if user.is_superuser:
        return qs
    groups = user.groups.all()
    return qs.filter(
        Q(submitter=user)
        | Q(approval_tasks__assigned_to=user)
        | Q(approval_tasks__assigned_group__in=groups)
        | Q(form_definition__admin_groups__in=groups)
        | Q(form_definition__reviewer_groups__in=groups)
    ).distinct()


def builder_permission_required(*permissions):
    """Custom admin endpoints need model permissions in addition to staff status."""

    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            resolved = []
            for permission in permissions:
                if permission.startswith("save_"):
                    model = permission.removeprefix("save_")
                    try:
                        data = json.loads(request.body)
                    except (ValueError, TypeError):
                        data = {}
                    key = "workflow_id" if model == "workflowdefinition" else "id"
                    action = (
                        "change" if isinstance(data, dict) and data.get(key) else "add"
                    )
                    if (
                        model == "workflowdefinition"
                        and action == "add"
                        and isinstance(data, dict)
                    ):
                        from .models import WorkflowDefinition

                        # Legacy saves without workflow_id update the form's existing track.
                        if WorkflowDefinition.objects.filter(
                            form_definition_id=data.get("form_id")
                        ).exists():
                            action = "change"
                    permission = f"{action}_{model}"
                resolved.append(permission)
            if not (
                user.is_active
                and user.is_staff
                and user.has_perms([f"django_forms_workflows.{p}" for p in resolved])
            ):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


def grant_submission_receipt(request, submission):
    """A public receipt belongs only to the submitting browser for one hour."""
    now = time.time()
    receipts = {
        k: v for k, v in request.session.get("dfw_receipts", {}).items() if v > now
    }
    receipts[str(submission.pk)] = now + 3600
    request.session["dfw_receipts"] = dict(list(receipts.items())[-100:])


def require_submission_receipt(request, submission):
    if visible_submissions(request.user).filter(pk=submission.pk).exists():
        return
    expiry = request.session.get("dfw_receipts", {}).get(str(submission.pk), 0)
    if submission.submitter_id is None and expiry > time.time():
        return
    raise Http404("Not found")


def render_success_message(template, data):
    """Escape answer tokens, then sanitize HTML including URL attributes."""
    import re

    def replace(match):
        value = data.get(match.group(1), "")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        return str(escape(str(value)))

    return nh3.clean(re.sub(r"\{(\w+)\}", replace, template))
