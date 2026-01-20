"""
SSO Authentication Backends for Django Form Workflows

This module provides Single Sign-On (SSO) authentication backends supporting
both SAML 2.0 (for enterprise IdPs like Google Workspace, Okta, Azure AD)
and OAuth2 (for Google, Microsoft, etc.).

Requires optional dependencies:
    pip install django-forms-workflows[sso]

Configuration via Django settings:

    FORMS_WORKFLOWS_SSO = {
        'providers': {
            'google-oauth2': {
                'enabled': True,
                'display_name': 'Google',
                'icon_class': 'bi-google',
            },
            'google-saml': {
                'enabled': True,
                'display_name': 'Google Workspace',
                'icon_class': 'bi-building',
            },
        },
        'attr_map': {
            'email': 'email',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'profile.department': 'department',
            'profile.title': 'title',
        },
        'create_users': True,
        'update_user_on_login': True,
    }

For SAML configuration, also set SOCIAL_AUTH_SAML_* settings.
For OAuth2, set SOCIAL_AUTH_GOOGLE_OAUTH2_* settings.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def get_sso_settings():
    """Get SSO settings with defaults.

    Configuration options:
        providers: Dict of SSO provider configurations
        attr_map: Mapping of Django fields to SSO attributes
        create_users: Whether to create new users on SSO login (default: True)
        update_user_on_login: Whether to update user attributes on login (default: True)
        sync_groups: Whether to sync SSO groups (default: False)
        link_to_existing_user: Whether to link SSO user to existing user by username (default: True)
        sync_ldap_groups_on_sso: Whether to sync LDAP groups when user logs in via SSO (default: True)
        username_from_email: Whether to extract username from email (default: True)
    """
    defaults = {
        "providers": {},
        "attr_map": {
            "email": "email",
            "first_name": "first_name",
            "last_name": "last_name",
        },
        "create_users": True,
        "update_user_on_login": True,
        "sync_groups": False,
        "link_to_existing_user": True,  # Link SSO users to existing LDAP users
        "sync_ldap_groups_on_sso": True,  # Sync LDAP groups on SSO login
        "username_from_email": True,  # Extract username from email prefix
    }
    user_settings = getattr(settings, "FORMS_WORKFLOWS_SSO", {})
    return {**defaults, **user_settings}


def is_sso_available():
    """Check if SSO dependencies are installed."""
    try:
        import social_django  # noqa: F401

        return True
    except ImportError:
        return False


def is_saml_available():
    """Check if SAML dependencies are installed."""
    try:
        import onelogin.saml2  # noqa: F401

        return True
    except ImportError:
        return False


def get_enabled_providers():
    """
    Get list of enabled SSO providers.

    Returns:
        List of dicts with provider info: [{'name': 'google-oauth2', 'display_name': 'Google', ...}]
    """
    sso_settings = get_sso_settings()
    providers = []

    # Default provider configurations
    default_providers = {
        "google-oauth2": {
            "display_name": "Google",
            "icon_class": "bi-google",
            "button_class": "btn-outline-danger",
        },
        "google-saml": {
            "display_name": "Google Workspace (SAML)",
            "icon_class": "bi-building",
            "button_class": "btn-outline-primary",
        },
        "microsoft-graph": {
            "display_name": "Microsoft",
            "icon_class": "bi-microsoft",
            "button_class": "btn-outline-primary",
        },
        "azuread-oauth2": {
            "display_name": "Azure AD",
            "icon_class": "bi-microsoft",
            "button_class": "btn-outline-info",
        },
        "azuread-tenant-oauth2": {
            "display_name": "Azure AD",
            "icon_class": "bi-microsoft",
            "button_class": "btn-outline-info",
        },
        "okta-oauth2": {
            "display_name": "Okta",
            "icon_class": "bi-shield-lock",
            "button_class": "btn-outline-secondary",
        },
        "saml": {
            "display_name": "Enterprise SSO",
            "icon_class": "bi-shield-check",
            "button_class": "btn-outline-dark",
        },
    }

    configured_providers = sso_settings.get("providers", {})

    for name, config in configured_providers.items():
        if config.get("enabled", True):
            defaults = default_providers.get(name, {})
            provider_info = {
                "name": name,
                "display_name": config.get(
                    "display_name", defaults.get("display_name", name.title())
                ),
                "icon_class": config.get(
                    "icon_class", defaults.get("icon_class", "bi-box-arrow-in-right")
                ),
                "button_class": config.get(
                    "button_class",
                    defaults.get("button_class", "btn-outline-secondary"),
                ),
            }
            providers.append(provider_info)

    return providers


def sync_user_profile(backend, user, response, *args, **kwargs):
    """
    Pipeline function to sync SSO attributes to UserProfile.

    Add to your SOCIAL_AUTH_PIPELINE:
        'django_forms_workflows.sso_backends.sync_user_profile',

    This function maps SSO attributes to both User and UserProfile models
    based on the FORMS_WORKFLOWS_SSO['attr_map'] configuration.
    """
    from django_forms_workflows.models import UserProfile

    sso_settings = get_sso_settings()

    if not sso_settings.get("update_user_on_login", True):
        return

    attr_map = sso_settings.get("attr_map", {})
    details = kwargs.get("details", {})

    # Merge response data with details for maximum attribute coverage
    all_attrs = {**details}
    if isinstance(response, dict):
        all_attrs.update(response)

    # Update User model fields
    user_updated = False
    for django_field, sso_field in attr_map.items():
        if not django_field.startswith("profile."):
            value = all_attrs.get(sso_field)
            if value and hasattr(user, django_field):
                setattr(user, django_field, value)
                user_updated = True

    if user_updated:
        user.save()

    # Update UserProfile fields
    profile, created = UserProfile.objects.get_or_create(user=user)
    profile_updated = False

    for django_field, sso_field in attr_map.items():
        if django_field.startswith("profile."):
            profile_field = django_field.replace("profile.", "")
            value = all_attrs.get(sso_field)
            if value and hasattr(profile, profile_field):
                setattr(profile, profile_field, value)
                profile_updated = True

    if profile_updated or created:
        profile.save()

    logger.info(f"Synced SSO attributes for user: {user.username}")


def get_saml_config():
    """
    Build SAML configuration dict for python3-saml.

    This helper constructs the SAML settings from Django settings,
    providing sensible defaults for common use cases.

    Returns:
        dict: SAML configuration for OneLogin's python3-saml
    """
    if not is_saml_available():
        raise ImportError(
            "python3-saml is not installed. Install with: pip install python3-saml"
        )

    saml_settings = getattr(settings, "FORMS_WORKFLOWS_SAML", {})

    # Build SP (Service Provider) configuration
    sp_entity_id = saml_settings.get("sp_entity_id", "")
    sp_acs_url = saml_settings.get("sp_acs_url", "")
    sp_sls_url = saml_settings.get("sp_sls_url", "")

    # Build IdP (Identity Provider) configuration
    idp_entity_id = saml_settings.get("idp_entity_id", "")
    idp_sso_url = saml_settings.get("idp_sso_url", "")
    idp_slo_url = saml_settings.get("idp_slo_url", "")
    idp_x509_cert = saml_settings.get("idp_x509_cert", "")

    # Handle certificate that may be base64 encoded or have escaped newlines
    if idp_x509_cert:
        import base64

        # First, replace literal \n with actual newlines
        if "\\n" in idp_x509_cert:
            idp_x509_cert = idp_x509_cert.replace("\\n", "\n")

        # If it doesn't look like a PEM certificate, try base64 decoding
        if not idp_x509_cert.strip().startswith("-----BEGIN"):
            try:
                decoded = base64.b64decode(idp_x509_cert).decode("utf-8")
                if "-----BEGIN" in decoded:
                    idp_x509_cert = decoded
            except Exception:
                pass  # Keep original if decoding fails

    config = {
        "strict": saml_settings.get("strict", True),
        "debug": saml_settings.get("debug", settings.DEBUG),
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": sp_sls_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": idp_entity_id,
            "singleSignOnService": {
                "url": idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": idp_slo_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": idp_x509_cert,
        },
        "security": saml_settings.get(
            "security",
            {
                "authnRequestsSigned": False,
                "wantAssertionsSigned": True,
                "wantMessagesSigned": False,
                "wantNameIdEncrypted": False,
                "wantAttributeStatement": False,  # Don't require attributes (Google may not send them)
            },
        ),
    }

    return config


def link_to_existing_user(backend, details, user=None, *args, **kwargs):
    """
    Pipeline function to link SSO login to an existing user by username.

    This is critical for organizations that use both LDAP and SSO authentication,
    where the same user may authenticate via either method. This ensures:
    1. SSO users are linked to their existing LDAP accounts
    2. Group memberships from LDAP are preserved
    3. Users don't end up with duplicate accounts

    Add to SOCIAL_AUTH_PIPELINE before 'social_core.pipeline.user.create_user':
        'django_forms_workflows.sso_backends.link_to_existing_user',

    Configuration via FORMS_WORKFLOWS_SSO:
        link_to_existing_user: True (default) - Enable username matching
        username_from_email: True (default) - Extract username from email prefix

    Returns:
        dict with 'user' key if existing user found, empty dict otherwise
    """
    if user:
        # Already have a user, nothing to do
        return {"user": user}

    sso_settings = get_sso_settings()

    if not sso_settings.get("link_to_existing_user", True):
        return {}

    # Get email from SSO details
    email = details.get("email", "")
    if not email:
        return {}

    # Determine username to look for
    if sso_settings.get("username_from_email", True):
        # Extract username from email prefix (e.g., "mdavis@sjcme.edu" -> "mdavis")
        username = email.split("@")[0].lower()
    else:
        username = details.get("username", "").lower()

    if not username:
        return {}

    # Try to find existing user by username (case-insensitive)
    try:
        existing_user = User.objects.get(username__iexact=username)
        logger.info(
            f"SSO login linked to existing user '{existing_user.username}' "
            f"(email: {email}, backend: {backend.name})"
        )
        return {"user": existing_user, "is_new": False}
    except User.DoesNotExist:
        # Also try by email (case-insensitive)
        try:
            existing_user = User.objects.get(email__iexact=email)
            logger.info(
                f"SSO login linked to existing user '{existing_user.username}' "
                f"by email (email: {email}, backend: {backend.name})"
            )
            return {"user": existing_user, "is_new": False}
        except User.DoesNotExist:
            pass

    logger.debug(f"No existing user found for username '{username}' or email '{email}'")
    return {}


def sync_ldap_groups_on_sso(backend, user, response, *args, **kwargs):
    """
    Pipeline function to sync LDAP group memberships for SSO users.

    When a user logs in via SSO (Google, SAML, etc.), this function queries
    LDAP to get the user's group memberships and syncs them to Django groups.

    This ensures SSO users have the same permissions as LDAP users, even when
    Google Workspace is synced from Active Directory.

    Add to SOCIAL_AUTH_PIPELINE after user creation:
        'django_forms_workflows.sso_backends.sync_ldap_groups_on_sso',

    Configuration via FORMS_WORKFLOWS_SSO:
        sync_ldap_groups_on_sso: True (default) - Enable LDAP group sync

    Requires:
        - django-auth-ldap to be installed and configured
        - AUTH_LDAP_SERVER_URI and AUTH_LDAP_BIND_DN settings
    """
    if not user:
        return

    sso_settings = get_sso_settings()

    if not sso_settings.get("sync_ldap_groups_on_sso", True):
        return

    try:
        groups_synced = sync_user_ldap_groups(user)
        if groups_synced:
            logger.info(
                f"Synced LDAP groups for SSO user '{user.username}': {groups_synced} groups"
            )
    except Exception as e:
        logger.warning(
            f"Failed to sync LDAP groups for SSO user '{user.username}': {e}"
        )


def sync_user_ldap_groups(user):
    """
    Sync LDAP group memberships to Django groups for a specific user.

    This is a standalone utility function that can be called from:
    - SSO pipeline (sync_ldap_groups_on_sso)
    - Management commands
    - Signal handlers
    - Admin actions

    Args:
        user: Django User object

    Returns:
        int: Number of groups synced, or None if LDAP unavailable

    Raises:
        Exception: If LDAP query fails
    """
    from django.contrib.auth.models import Group

    # Check if LDAP is configured
    ldap_server = getattr(settings, "AUTH_LDAP_SERVER_URI", None)
    if not ldap_server:
        logger.debug("LDAP not configured, skipping group sync")
        return None

    try:
        import ldap
        from ldap.filter import escape_filter_chars
    except ImportError:
        logger.debug("python-ldap not installed, skipping group sync")
        return None

    # Get LDAP connection settings
    bind_dn = getattr(settings, "AUTH_LDAP_BIND_DN", "")
    bind_password = getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "")
    user_search_base = getattr(settings, "AUTH_LDAP_USER_SEARCH", None)

    # Try to get search base from user search configuration
    search_base = None
    if user_search_base:
        # AUTH_LDAP_USER_SEARCH is typically an LDAPSearch object
        if hasattr(user_search_base, "base_dn"):
            search_base = user_search_base.base_dn
        elif isinstance(user_search_base, tuple) and len(user_search_base) >= 1:
            search_base = user_search_base[0]

    if not search_base:
        # Fall back to extracting from bind DN
        search_base = getattr(settings, "AUTH_LDAP_USER_SEARCH_BASE", None)
        if not search_base and bind_dn:
            # Extract DC components from bind DN
            parts = bind_dn.split(",")
            dc_parts = [p for p in parts if p.strip().upper().startswith("DC=")]
            if dc_parts:
                search_base = ",".join(dc_parts)

    if not search_base:
        logger.warning("Could not determine LDAP search base, skipping group sync")
        return None

    # Connect to LDAP
    try:
        conn = ldap.initialize(ldap_server)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)

        # Configure TLS if needed
        import os

        tls_require_cert = os.getenv("LDAP_TLS_REQUIRE_CERT", "demand").lower()
        if tls_require_cert == "never":
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

        if bind_dn and bind_password:
            conn.simple_bind_s(bind_dn, bind_password)
        else:
            conn.simple_bind_s("", "")

    except ldap.LDAPError as e:
        logger.error(f"LDAP connection failed: {e}")
        raise

    try:
        # Search for the user
        search_filter = f"(sAMAccountName={escape_filter_chars(user.username)})"
        result = conn.search_s(
            search_base,
            ldap.SCOPE_SUBTREE,
            search_filter,
            ["memberOf", "dn"],
        )

        if not result:
            logger.debug(f"User '{user.username}' not found in LDAP")
            return 0

        # Get user's group memberships
        user_dn, user_attrs = result[0]
        member_of = user_attrs.get("memberOf", [])

        groups_synced = 0
        for group_dn in member_of:
            # Handle bytes vs string
            if isinstance(group_dn, bytes):
                group_dn = group_dn.decode("utf-8")

            # Extract CN from DN
            group_name = None
            for part in group_dn.split(","):
                if part.strip().upper().startswith("CN="):
                    group_name = part.strip()[3:]
                    break

            if group_name:
                # Create Django group if it doesn't exist
                group, created = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)
                groups_synced += 1

                if created:
                    logger.info(f"Created new group from LDAP: {group_name}")

        return groups_synced

    finally:
        conn.unbind_s()


# Pipeline for social-auth-app-django
# Recommended pipeline configuration:
#
# SOCIAL_AUTH_PIPELINE = (
#     'social_core.pipeline.social_auth.social_details',
#     'social_core.pipeline.social_auth.social_uid',
#     'social_core.pipeline.social_auth.auth_allowed',
#     'social_core.pipeline.social_auth.social_user',
#     'django_forms_workflows.sso_backends.link_to_existing_user',  # Link to LDAP user
#     'social_core.pipeline.user.get_username',
#     'social_core.pipeline.user.create_user',
#     'social_core.pipeline.social_auth.associate_user',
#     'social_core.pipeline.social_auth.load_extra_data',
#     'social_core.pipeline.user.user_details',
#     'django_forms_workflows.sso_backends.sync_user_profile',  # Sync profile
#     'django_forms_workflows.sso_backends.sync_ldap_groups_on_sso',  # Sync LDAP groups
# )

SOCIAL_AUTH_PIPELINE_EXTENSION = (
    # Link SSO users to existing LDAP users by username
    "django_forms_workflows.sso_backends.link_to_existing_user",
    # Sync SSO attributes to UserProfile
    "django_forms_workflows.sso_backends.sync_user_profile",
    # Sync LDAP group memberships for SSO users
    "django_forms_workflows.sso_backends.sync_ldap_groups_on_sso",
)
