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
    """Get SSO settings with defaults."""
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
            },
        ),
    }

    return config


# Pipeline for social-auth-app-django
SOCIAL_AUTH_PIPELINE_EXTENSION = (
    # Adds sync_user_profile to sync attributes to UserProfile
    "django_forms_workflows.sso_backends.sync_user_profile",
)
