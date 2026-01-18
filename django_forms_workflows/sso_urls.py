"""
SSO URL Configuration for Django Form Workflows

Include these URLs in your project's urlpatterns:

    from django.urls import path, include

    urlpatterns = [
        # ... your other urls ...

        # SSO authentication URLs
        path('sso/', include('django_forms_workflows.sso_urls')),

        # python-social-auth URLs (required for OAuth2 providers)
        path('oauth/', include('social_django.urls', namespace='social')),
    ]

SAML endpoints:
    - /sso/login/             - SSO provider selection or redirect
    - /sso/saml/login/        - SAML login initiation
    - /sso/saml/acs/          - SAML Assertion Consumer Service
    - /sso/saml/metadata/     - SP metadata for IdP configuration
    - /sso/saml/sls/          - Single Logout Service
"""

from django.urls import path

from .sso_views import (
    SAMLACSView,
    SAMLLoginView,
    SAMLMetadataView,
    SAMLSLSView,
    SSOLoginView,
)

app_name = "forms_workflows_sso"

urlpatterns = [
    # Main SSO login (shows provider selection or redirects to single provider)
    path("login/", SSOLoginView.as_view(), name="login"),
    # SAML endpoints
    path("saml/login/", SAMLLoginView.as_view(), name="saml_login"),
    path("saml/acs/", SAMLACSView.as_view(), name="saml_acs"),
    path("saml/metadata/", SAMLMetadataView.as_view(), name="saml_metadata"),
    path("saml/sls/", SAMLSLSView.as_view(), name="saml_sls"),
]
