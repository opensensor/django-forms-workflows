"""
Context processors for django_forms_workflows.
"""

from django.conf import settings
from django.db.models import Q


def forms_workflows(request):
    """
    Inject package-level settings into every template context.

    Adds:
        site_name (str): Human-readable name of the site, used in page
            titles, the navbar brand, and the footer.  Configured via::

                FORMS_WORKFLOWS = {
                    'SITE_NAME': 'My Organisation Workflows',
                    ...
                }

            Defaults to ``"Django Forms Workflows"`` when not set.

        user_is_approver (bool): True when the current user is superuser/staff
            or has ever been assigned an ApprovalTask (directly or via a
            group).  Used to gate the Approvals nav link so it is only shown
            to users who have an approver role.
    """
    fw_settings = getattr(settings, "FORMS_WORKFLOWS", {})

    user_is_approver = False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        if user.is_superuser or user.is_staff:
            user_is_approver = True
        else:
            from .models import ApprovalTask

            user_is_approver = ApprovalTask.objects.filter(
                Q(assigned_to=user) | Q(assigned_group__in=user.groups.all())
            ).exists()

    return {
        "site_name": fw_settings.get("SITE_NAME", "Django Forms Workflows"),
        "user_is_approver": user_is_approver,
    }
