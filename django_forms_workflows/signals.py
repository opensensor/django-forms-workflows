"""
Signal handlers for django-forms-workflows.

Handles automatic UserProfile creation and LDAP attribute synchronization.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


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
