from django.contrib.auth.models import User
from django.db import models

from .models import FormDefinition, FormSubmission


def user_can_submit_form(user: User, form_def: FormDefinition) -> bool:
    """Return True if the user is allowed to submit the given form.

    Rules:
    - Superusers can submit any active form
    - If the form has no submit_groups specified, any authenticated user may submit
    - Otherwise, the user must belong to at least one of the submit_groups
    """
    if getattr(user, "is_superuser", False):
        return True

    # If no groups specified, treat as open to all authenticated users
    try:
        has_groups = form_def.submit_groups.exists()
    except Exception:
        has_groups = False

    if not has_groups:
        return True

    user_group_ids = user.groups.values_list("id", flat=True)
    return form_def.submit_groups.filter(id__in=user_group_ids).exists()


def user_can_approve(user: User, submission: FormSubmission) -> bool:
    """Return True if the user can approve the given submission.

    Rules:
    - Superusers can approve anything
    - If there is a task assigned directly to the user, they can approve
    - If there is a task assigned to one of the user's groups, they can approve
    """
    if getattr(user, "is_superuser", False):
        return True

    user_groups = user.groups.all()
    return submission.approval_tasks.filter(
        models.Q(assigned_to=user) | models.Q(assigned_group__in=user_groups)
    ).exists()
