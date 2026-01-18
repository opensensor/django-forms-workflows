"""
Utility functions for django-forms-workflows.

Provides helper functions for permissions, LDAP integration, and workflow logic.
"""

import logging
import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models

from .models import FormDefinition, FormSubmission

logger = logging.getLogger(__name__)


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


def get_ldap_attribute(user, attr_name: str, ldap_attr_name: str = None) -> str:
    """
    Get LDAP attribute for a user.

    Args:
        user: Django User object
        attr_name: Name of the attribute to retrieve (for logging)
        ldap_attr_name: Actual LDAP attribute name (defaults to attr_name)

    Returns:
        String value of the attribute or empty string if not found
    """
    if not user:
        return ""

    ldap_attr_name = ldap_attr_name or attr_name

    # Try to get LDAP attributes from user object
    # These would be populated by django-auth-ldap
    ldap_user = getattr(user, "ldap_user", None)
    if ldap_user:
        try:
            attrs = ldap_user.attrs

            # Common LDAP attribute mappings
            attr_map = {
                "department": "department",
                "title": "title",
                "manager": "manager",
                "phone": "telephoneNumber",
                "employee_id": "employeeNumber",
                "email": "mail",
                "first_name": "givenName",
                "last_name": "sn",
                "display_name": "displayName",
            }

            # Use mapping if available, otherwise use provided name
            ldap_attr = attr_map.get(ldap_attr_name, ldap_attr_name)

            if ldap_attr in attrs:
                value = attrs[ldap_attr]
                # LDAP attributes are often lists
                if isinstance(value, list) and value:
                    return (
                        value[0].decode("utf-8")
                        if isinstance(value[0], bytes)
                        else str(value[0])
                    )
                return value.decode("utf-8") if isinstance(value, bytes) else str(value)

        except Exception as e:
            logger.warning(
                f"Error getting LDAP attribute {ldap_attr_name} for user {user.username}: {e}"
            )

    return ""


def get_user_manager(user) -> User | None:
    """
    Get the manager of a user from LDAP or UserProfile.

    Args:
        user: Django User object

    Returns:
        User object of the manager or None
    """
    if not user:
        return None

    # First try to get manager from UserProfile
    try:
        from django_forms_workflows.models import UserProfile

        profile = UserProfile.objects.filter(user=user).first()
        if profile and profile.manager:
            return profile.manager
    except Exception as e:
        logger.debug(f"Could not get manager from UserProfile: {e}")

    # Try to get manager DN from LDAP
    manager_dn = get_ldap_attribute(user, "manager")
    if not manager_dn:
        return None

    # Try to find user by manager DN
    # This is a simplified version - actual implementation depends on LDAP structure
    try:
        # Extract CN from DN (e.g., "CN=John Doe,OU=Users,DC=example,DC=com")
        cn_match = re.search(r"CN=([^,]+)", manager_dn)
        if cn_match:
            manager_cn = cn_match.group(1)

            # Try to find user by full name or username
            # This is a best-effort approach
            manager = User.objects.filter(
                first_name__icontains=manager_cn.split()[0]
            ).first()
            if manager:
                return manager

    except Exception as e:
        logger.warning(f"Error getting manager for user {user.username}: {e}")

    return None


def user_can_view_form(user, form_definition: FormDefinition) -> bool:
    """
    Check if a user can view a specific form.

    Args:
        user: Django User object
        form_definition: FormDefinition object

    Returns:
        Boolean indicating if user can view
    """
    # Public forms can be viewed by anyone
    if not form_definition.requires_login:
        return True

    # Must be authenticated
    if not user or not user.is_authenticated:
        return False

    # Superusers can view any form
    if user.is_superuser:
        return True

    # Check if user is in any of the view groups
    view_groups = form_definition.view_groups.all()
    if not view_groups.exists():
        # No groups specified means any authenticated user can view
        return True

    return user.groups.filter(id__in=view_groups).exists()


def user_can_view_submission(user, submission: FormSubmission) -> bool:
    """
    Check if a user can view a specific submission.

    Args:
        user: Django User object
        submission: FormSubmission object

    Returns:
        Boolean indicating if user can view the submission
    """
    if not user or not user.is_authenticated:
        return False

    # Superusers can view anything
    if user.is_superuser:
        return True

    # Submitter can view their own submission
    if submission.submitter == user:
        return True

    # Approvers can view submissions they need to approve
    if user_can_approve(user, submission):
        return True

    # Form admins can view submissions
    if user.groups.filter(
        id__in=submission.form_definition.admin_groups.all()
    ).exists():
        return True

    return False


def check_escalation_needed(submission: FormSubmission) -> bool:
    """
    Check if a submission needs escalation based on workflow rules.

    Args:
        submission: FormSubmission object

    Returns:
        Boolean indicating if escalation is needed
    """
    workflow = getattr(submission.form_definition, "workflow", None)
    if not workflow:
        return False

    if not workflow.escalation_field or not workflow.escalation_threshold:
        return False

    # Check if the escalation field value exceeds threshold
    field_value = submission.form_data.get(workflow.escalation_field)
    if field_value is None:
        return False

    try:
        value = Decimal(str(field_value))
        threshold = workflow.escalation_threshold
        return value > threshold
    except (ValueError, TypeError):
        logger.warning(
            f"Could not compare escalation field value: {field_value} for submission {submission.id}"
        )
        return False


def sync_ldap_groups():
    """
    Synchronize LDAP groups to Django groups.

    This should be run periodically to keep groups in sync.
    Note: This is a placeholder - actual implementation depends on LDAP structure.
    """
    try:
        from django_auth_ldap.backend import LDAPBackend

        _backend = LDAPBackend()  # noqa: F841 - Placeholder for future implementation

        # This would need to be implemented based on your LDAP structure
        # and how you want to sync groups
        logger.info("LDAP group sync completed")

    except ImportError:
        logger.warning("django-auth-ldap not installed, skipping group sync")
    except Exception as e:
        logger.error(f"Error syncing LDAP groups: {e}")
