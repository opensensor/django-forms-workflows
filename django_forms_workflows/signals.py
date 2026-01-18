"""
Signal handlers for django-forms-workflows.

Handles automatic UserProfile creation, LDAP attribute synchronization,
and SSO user attribute syncing.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


def get_ldap_attribute(user, attr_name, ldap_attr_name=None):
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
            if ldap_attr_name in attrs:
                value = attrs[ldap_attr_name]
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


def sync_ldap_attributes(user, profile=None):
    """
    Sync LDAP attributes to UserProfile.

    Args:
        user: Django User object
        profile: UserProfile object (optional, will be fetched if not provided)

    Returns:
        UserProfile object or None if sync failed
    """
    from django_forms_workflows.models import UserProfile

    # Get or create profile
    if profile is None:
        profile, created = UserProfile.objects.get_or_create(user=user)
    else:
        created = False

    # Check if LDAP sync is enabled
    forms_workflows_settings = getattr(settings, "FORMS_WORKFLOWS", {})
    ldap_sync_settings = forms_workflows_settings.get("LDAP_SYNC", {})

    if not ldap_sync_settings.get("enabled", False):
        return profile

    # Get LDAP attribute mappings
    attribute_mappings = ldap_sync_settings.get(
        "attributes",
        {
            "employee_id": "extensionAttribute1",
            "department": "department",
            "title": "title",
            "phone": "telephoneNumber",
            "manager_dn": "manager",
        },
    )

    # Sync each attribute
    updated = False
    for profile_field, ldap_attr in attribute_mappings.items():
        if hasattr(profile, profile_field):
            value = get_ldap_attribute(user, profile_field, ldap_attr)
            if value:
                current_value = getattr(profile, profile_field, "")
                if current_value != value:
                    setattr(profile, profile_field, value)
                    updated = True
                    logger.debug(
                        f"Updated {profile_field} for {user.username}: {value}"
                    )

    # Update sync timestamp if any changes were made
    if updated or created:
        profile.ldap_last_sync = timezone.now()
        profile.save()
        logger.info(f"LDAP attributes synced for user {user.username}")

    return profile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create UserProfile when User is created.

    This ensures every user has a profile.
    """
    from django_forms_workflows.models import UserProfile

    if created:
        UserProfile.objects.get_or_create(user=instance)
        logger.debug(f"Created UserProfile for {instance.username}")


@receiver(user_logged_in)
def sync_ldap_on_login(sender, user, request, **kwargs):
    """
    Sync LDAP attributes to UserProfile when user logs in.

    This keeps the profile up-to-date with LDAP data.
    Only runs if LDAP_SYNC.sync_on_login is True in settings.
    """
    forms_workflows_settings = getattr(settings, "FORMS_WORKFLOWS", {})
    ldap_sync_settings = forms_workflows_settings.get("LDAP_SYNC", {})

    if ldap_sync_settings.get("sync_on_login", False):
        try:
            sync_ldap_attributes(user)
        except Exception as e:
            logger.error(f"Error syncing LDAP attributes for {user.username}: {e}")


# ============================================================
# SSO Signal Handlers
# ============================================================


def sync_sso_attributes_to_profile(user, details, response=None):
    """
    Sync SSO attributes to UserProfile.

    Args:
        user: Django User object
        details: Dict of user details from SSO provider
        response: Raw response from SSO provider (optional)

    Returns:
        UserProfile object or None if sync failed
    """
    from django_forms_workflows.models import UserProfile
    from django_forms_workflows.sso_backends import get_sso_settings

    sso_settings = get_sso_settings()

    if not sso_settings.get("update_user_on_login", True):
        return None

    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Merge details with response if available
    all_attrs = {**details}
    if response and isinstance(response, dict):
        all_attrs.update(response)

    attr_map = sso_settings.get("attr_map", {})

    # Update profile fields based on attribute mapping
    updated = False
    for django_field, sso_field in attr_map.items():
        if django_field.startswith("profile."):
            profile_field = django_field.replace("profile.", "")
            value = all_attrs.get(sso_field)
            if value and hasattr(profile, profile_field):
                current_value = getattr(profile, profile_field, "")
                if current_value != value:
                    setattr(profile, profile_field, value)
                    updated = True
                    logger.debug(
                        f"Updated {profile_field} for {user.username}: {value}"
                    )

    if updated or created:
        profile.save()
        logger.info(f"SSO attributes synced for user {user.username}")

    return profile


def is_sso_authentication(request):
    """
    Check if the current authentication is from an SSO provider.

    Args:
        request: Django request object

    Returns:
        bool: True if authentication is from SSO, False otherwise
    """
    # Check for social-auth session data
    if hasattr(request, "session"):
        return bool(request.session.get("social_auth_last_login_backend"))
    return False


@receiver(user_logged_in)
def sync_sso_on_login(sender, user, request, **kwargs):
    """
    Sync SSO attributes to UserProfile when user logs in via SSO.

    This runs after social-auth pipeline and keeps the profile
    in sync with SSO provider data.
    """
    # Check if this is an SSO login
    if not is_sso_authentication(request):
        return

    try:
        # Get SSO backend and user details from session
        backend = request.session.get("social_auth_last_login_backend", "")
        logger.info(f"SSO login detected for {user.username} via {backend}")

        # The actual sync happens in the pipeline (sso_backends.sync_user_profile)
        # This signal is for additional processing if needed

    except Exception as e:
        logger.error(f"Error in SSO login signal for {user.username}: {e}")
