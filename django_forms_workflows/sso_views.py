"""
SSO Views for Django Form Workflows

This module provides views for Single Sign-On (SSO) authentication,
supporting both SAML 2.0 and OAuth2 flows.

URLs are typically mounted at:
    path('sso/', include('django_forms_workflows.sso_urls')),
"""

import logging

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .sso_backends import (
    get_enabled_providers,
    get_saml_config,
    is_saml_available,
    is_sso_available,
)

logger = logging.getLogger(__name__)


class SSOLoginView(View):
    """
    SSO login view that displays available SSO providers.

    If only one provider is configured, redirects directly to that provider.
    Otherwise, displays a selection page.
    """

    template_name = "django_forms_workflows/sso/login.html"

    def get(self, request):
        if not is_sso_available():
            return HttpResponseBadRequest(
                "SSO is not available. Install with: pip install django-forms-workflows[sso]"
            )

        providers = get_enabled_providers()

        if not providers:
            return HttpResponseBadRequest(
                "No SSO providers are configured. Check FORMS_WORKFLOWS_SSO settings."
            )

        # If only one provider, redirect directly
        if len(providers) == 1:
            provider = providers[0]
            return redirect("social:begin", backend=provider["name"])

        next_url = request.GET.get("next", settings.LOGIN_REDIRECT_URL)

        return render(
            request,
            self.template_name,
            {
                "providers": providers,
                "next": next_url,
            },
        )


class SAMLMetadataView(View):
    """
    SAML Service Provider metadata view.

    Returns XML metadata for configuring the IdP (Identity Provider).
    This URL should be provided to the IdP administrator.
    """

    def get(self, request):
        if not is_saml_available():
            return HttpResponseBadRequest(
                "SAML is not available. Install with: pip install python3-saml"
            )

        try:
            from onelogin.saml2.metadata import OneLogin_Saml2_Metadata
            from onelogin.saml2.settings import OneLogin_Saml2_Settings

            saml_config = get_saml_config()
            saml_settings = OneLogin_Saml2_Settings(saml_config)
            metadata = OneLogin_Saml2_Metadata.builder(saml_settings.get_sp_metadata())

            return HttpResponse(metadata, content_type="application/xml")
        except Exception as e:
            logger.error(f"Error generating SAML metadata: {e}")
            return HttpResponseBadRequest(f"Error generating SAML metadata: {e}")


@method_decorator(csrf_exempt, name="dispatch")
class SAMLACSView(View):
    """
    SAML Assertion Consumer Service (ACS) view.

    Receives SAML responses from the IdP and authenticates the user.
    """

    def _prepare_django_request(self, request):
        """
        Prepare a Django request for python3-saml.

        Returns a dict with the request data in the format expected by OneLogin_Saml2_Auth.
        Handles reverse proxy scenarios where X-Forwarded-* headers indicate the real protocol.
        """
        # Check if request is secure (handles reverse proxy via X-Forwarded-Proto)
        is_secure = request.is_secure()
        if not is_secure:
            # Check X-Forwarded-Proto header for reverse proxy
            forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
            is_secure = forwarded_proto.lower() == "https"

        # Get the host without port (proxy may forward with port)
        http_host = request.META.get("HTTP_HOST", "")
        # Strip port if present to avoid mismatches
        if ":" in http_host:
            http_host = http_host.split(":")[0]

        return {
            "https": "on" if is_secure else "off",
            "http_host": http_host,
            "script_name": request.META["PATH_INFO"],
            "server_port": "443" if is_secure else "80",
            "get_data": request.GET.copy(),
            "post_data": request.POST.copy(),
        }

    def post(self, request):
        if not is_saml_available():
            return HttpResponseBadRequest(
                "SAML is not available. Install with: pip install python3-saml"
            )

        try:
            from django.contrib.auth import get_user_model
            from onelogin.saml2.auth import OneLogin_Saml2_Auth

            saml_config = get_saml_config()
            req = self._prepare_django_request(request)
            auth = OneLogin_Saml2_Auth(req, saml_config)

            auth.process_response()
            errors = auth.get_errors()

            if errors:
                last_error_reason = auth.get_last_error_reason()
                logger.error(f"SAML authentication errors: {errors}")
                logger.error(f"SAML last error reason: {last_error_reason}")
                return HttpResponseBadRequest(
                    f"SAML authentication failed: {errors}. Reason: {last_error_reason}"
                )

            if not auth.is_authenticated():
                return HttpResponseBadRequest("SAML authentication failed")

            # Get user attributes from SAML response
            # Note: Google SAML may not include AttributeStatement, so attributes may be empty
            attributes = auth.get_attributes() or {}
            name_id = auth.get_nameid()

            # Try to get email from attributes, fall back to NameID
            email = None
            for attr_name in ["email", "Email", "emailAddress", "mail"]:
                if attr_name in attributes and attributes[attr_name]:
                    email = attributes[attr_name][0]
                    break
            if not email:
                email = name_id  # NameID should be the email for Google SAML

            if not email:
                return HttpResponseBadRequest("SAML response missing email/NameID")

            # Get first/last name from attributes if available
            first_name = ""
            for attr_name in ["firstName", "FirstName", "first_name", "givenName"]:
                if attr_name in attributes and attributes[attr_name]:
                    first_name = attributes[attr_name][0]
                    break

            last_name = ""
            for attr_name in ["lastName", "LastName", "last_name", "sn", "surname"]:
                if attr_name in attributes and attributes[attr_name]:
                    last_name = attributes[attr_name][0]
                    break

            # Find or create user - try to link to existing user first
            user_model = get_user_model()
            user = None
            created = False

            # Extract username from email
            username = email.split("@")[0].lower()

            # Try to find existing user by username (case-insensitive)
            # This links SSO users to their existing LDAP accounts
            try:
                user = user_model.objects.get(username__iexact=username)
                logger.info(
                    f"SAML login linked to existing user '{user.username}' "
                    f"(email: {email})"
                )
            except user_model.DoesNotExist:
                # Try by email
                try:
                    user = user_model.objects.get(email__iexact=email)
                    logger.info(
                        f"SAML login linked to existing user '{user.username}' "
                        f"by email (email: {email})"
                    )
                except user_model.DoesNotExist:
                    # Create new user
                    user = user_model.objects.create(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    user.set_unusable_password()
                    user.save()
                    created = True
                    logger.info(f"Created new user from SAML: {user.username}")

            # Update user attributes if they logged in with existing account
            if not created and (first_name or last_name):
                updated = False
                if first_name and not user.first_name:
                    user.first_name = first_name
                    updated = True
                if last_name and not user.last_name:
                    user.last_name = last_name
                    updated = True
                if updated:
                    user.save()

            # Sync LDAP groups for this user
            try:
                from .sso_backends import sync_user_ldap_groups

                groups_synced = sync_user_ldap_groups(user)
                if groups_synced:
                    logger.info(
                        f"Synced {groups_synced} LDAP groups for SAML user '{user.username}'"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to sync LDAP groups for SAML user '{user.username}': {e}"
                )

            # Log user in
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            logger.info(f"SAML login successful for: {user.username}")

            # Redirect to target URL
            relay_state = request.POST.get("RelayState", settings.LOGIN_REDIRECT_URL)
            return HttpResponseRedirect(relay_state)

        except Exception as e:
            logger.error(f"SAML ACS error: {e}")
            return HttpResponseBadRequest(f"SAML authentication error: {e}")


class SAMLLoginView(View):
    """
    SAML login initiation view.

    Redirects user to the IdP for authentication.
    """

    def get(self, request):
        if not is_saml_available():
            return HttpResponseBadRequest(
                "SAML is not available. Install with: pip install python3-saml"
            )

        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth

            saml_config = get_saml_config()
            req = {
                "https": "on" if request.is_secure() else "off",
                "http_host": request.META["HTTP_HOST"],
                "script_name": request.META["PATH_INFO"],
                "server_port": request.META.get(
                    "SERVER_PORT", "443" if request.is_secure() else "80"
                ),
                "get_data": request.GET.copy(),
                "post_data": request.POST.copy(),
            }
            auth = OneLogin_Saml2_Auth(req, saml_config)

            # Use 'next' parameter as RelayState
            relay_state = request.GET.get("next", settings.LOGIN_REDIRECT_URL)
            redirect_url = auth.login(return_to=relay_state)

            return HttpResponseRedirect(redirect_url)

        except Exception as e:
            logger.error(f"SAML login error: {e}")
            return HttpResponseBadRequest(f"SAML login error: {e}")


@method_decorator(csrf_exempt, name="dispatch")
class SAMLSLSView(View):
    """
    SAML Single Logout Service (SLS) view.

    Handles logout requests and responses from the IdP.
    """

    def get(self, request):
        return self._handle_logout(request)

    def post(self, request):
        return self._handle_logout(request)

    def _handle_logout(self, request):
        if not is_saml_available():
            return HttpResponseBadRequest(
                "SAML is not available. Install with: pip install python3-saml"
            )

        try:
            from django.contrib.auth import logout
            from onelogin.saml2.auth import OneLogin_Saml2_Auth

            saml_config = get_saml_config()
            req = {
                "https": "on" if request.is_secure() else "off",
                "http_host": request.META["HTTP_HOST"],
                "script_name": request.META["PATH_INFO"],
                "server_port": request.META.get(
                    "SERVER_PORT", "443" if request.is_secure() else "80"
                ),
                "get_data": request.GET.copy(),
                "post_data": request.POST.copy(),
            }
            auth = OneLogin_Saml2_Auth(req, saml_config)

            # Process logout request/response
            url = auth.process_slo()
            errors = auth.get_errors()

            if errors:
                logger.error(f"SAML SLS errors: {errors}")
                return HttpResponseBadRequest(f"SAML logout failed: {errors}")

            # Logout locally
            logout(request)
            logger.info("SAML logout successful")

            if url:
                return HttpResponseRedirect(url)

            return redirect(settings.LOGOUT_REDIRECT_URL or "/")

        except Exception as e:
            logger.error(f"SAML SLS error: {e}")
            return HttpResponseBadRequest(f"SAML logout error: {e}")
