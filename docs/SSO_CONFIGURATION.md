# SSO Configuration Guide

This guide explains how to configure Single Sign-On (SSO) authentication for django-forms-workflows, supporting both SAML 2.0 and OAuth2 protocols.

## Installation

Install the SSO dependencies:

```bash
# For full SSO support (OAuth2 + SAML)
pip install django-forms-workflows[sso]

# For SAML only
pip install django-forms-workflows[saml]
```

## Quick Start

### 1. Add Required Apps

Add the required apps to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... your other apps ...
    'django_forms_workflows',
    'social_django',  # Required for OAuth2 providers
]
```

### 2. Add Authentication Backends

Configure the authentication backends in your settings:

```python
AUTHENTICATION_BACKENDS = [
    # Keep Django's default backend for username/password login
    'django.contrib.auth.backends.ModelBackend',

    # Add SSO backends as needed
    'social_core.backends.google.GoogleOAuth2',           # Google OAuth2
    'social_core.backends.google.GoogleOAuth2',           # Google SAML
    'social_core.backends.microsoft.MicrosoftOAuth2',     # Microsoft
    'social_core.backends.azuread.AzureADOAuth2',         # Azure AD
    'social_core.backends.okta.OktaOAuth2',               # Okta
]
```

### 3. Add URL Patterns

Include the SSO URLs in your project:

```python
from django.urls import path, include

urlpatterns = [
    # ... your other urls ...

    # Django Forms Workflows (includes SSO if available)
    path('forms/', include('django_forms_workflows.urls')),

    # python-social-auth URLs (required for OAuth2)
    path('oauth/', include('social_django.urls', namespace='social')),
]
```

### 4. Configure SSO Settings

```python
FORMS_WORKFLOWS_SSO = {
    'providers': {
        'google-oauth2': {
            'enabled': True,
            'display_name': 'Google',
            'icon_class': 'bi-google',
            'button_class': 'btn-outline-danger',
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
```

## Google OAuth2 Configuration

### 1. Create OAuth2 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth client ID**
5. Select **Web application**
6. Add authorized redirect URI: `https://your-domain.com/oauth/complete/google-oauth2/`
7. Copy the Client ID and Client Secret

### 2. Django Settings

```python
# Google OAuth2 settings
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = 'your-client-id.apps.googleusercontent.com'
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = 'your-client-secret'

# Scopes (optional - default scopes work for most cases)
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'openid',
    'email',
    'profile',
]

# Enable SSO provider
FORMS_WORKFLOWS_SSO = {
    'providers': {
        'google-oauth2': {
            'enabled': True,
            'display_name': 'Sign in with Google',
        },
    },
}
```

## Google SAML Configuration (Google Workspace)

For enterprise environments using Google Workspace (formerly G Suite).

### 1. Configure SAML App in Google Admin

1. Go to [Google Admin Console](https://admin.google.com/)
2. Navigate to **Apps > Web and mobile apps**
3. Click **Add app > Add custom SAML app**
4. Fill in the app details
5. Download the IdP metadata or note the following:
   - SSO URL
   - Entity ID
   - Certificate

### 2. Django Settings

```python
FORMS_WORKFLOWS_SAML = {
    'strict': True,
    'debug': False,

    # Service Provider (your app) settings
    'sp_entity_id': 'https://your-domain.com/sso/saml/metadata/',
    'sp_acs_url': 'https://your-domain.com/sso/saml/acs/',
    'sp_sls_url': 'https://your-domain.com/sso/saml/sls/',


## Social Auth Pipeline Configuration

To sync SSO user attributes to UserProfile, add the custom pipeline step:

```python
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',

    # Add this line to sync attributes to UserProfile
    'django_forms_workflows.sso_backends.sync_user_profile',
)
```

## Attribute Mapping

Map SSO provider attributes to Django User and UserProfile fields:

```python
FORMS_WORKFLOWS_SSO = {
    'attr_map': {
        # User model fields
        'email': 'email',
        'first_name': 'first_name',
        'last_name': 'last_name',

        # UserProfile fields (prefixed with 'profile.')
        'profile.department': 'department',
        'profile.title': 'title',
        'profile.phone': 'phone',
        'profile.employee_id': 'employee_id',
    },
}
```

## Redirect Settings

Configure where users are redirected after login/logout:

```python
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/forms/'
LOGOUT_REDIRECT_URL = '/'

# For social-auth
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/forms/'
SOCIAL_AUTH_LOGIN_ERROR_URL = '/accounts/login/'
```

## Security Settings

```python
# Require HTTPS for OAuth callbacks in production
SOCIAL_AUTH_REDIRECT_IS_HTTPS = True

# Allowed hosts for OAuth (whitelist your domain)
SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS = ['your-domain.com']

# Session settings
SOCIAL_AUTH_SESSION_EXPIRATION = False
```

## Troubleshooting

### Common Issues

1. **"CSRF verification failed"**
   - Ensure `SOCIAL_AUTH_REDIRECT_IS_HTTPS = True` in production
   - Check that your redirect URLs match exactly

2. **"User not found" after login**
   - Verify `create_users` is set to `True` in settings
   - Check the pipeline configuration

3. **"Invalid redirect URI"**
   - Ensure the redirect URI in your OAuth provider matches your Django URL

### Debug Mode

Enable debug logging for SSO:

```python
LOGGING = {
    'loggers': {
        'django_forms_workflows.sso_backends': {
            'level': 'DEBUG',
        },
        'social_core': {
            'level': 'DEBUG',
        },
    },
}
```

## Available SSO Providers

The following providers are pre-configured with display settings:

| Provider Key | Display Name | Backend Class |
|-------------|--------------|---------------|
| `google-oauth2` | Google | `social_core.backends.google.GoogleOAuth2` |
| `google-saml` | Google Workspace (SAML) | Custom SAML |
| `microsoft-graph` | Microsoft | `social_core.backends.microsoft.MicrosoftOAuth2` |
| `azuread-oauth2` | Azure AD | `social_core.backends.azuread.AzureADOAuth2` |
| `okta-oauth2` | Okta | `social_core.backends.okta.OktaOAuth2` |
| `saml` | Enterprise SSO | Custom SAML |

## SAML Endpoints

When using SAML, the following endpoints are available:

- **Metadata**: `/sso/saml/metadata/` - Provide this to your IdP administrator
- **ACS**: `/sso/saml/acs/` - Assertion Consumer Service (receives SAML responses)
- **Login**: `/sso/saml/login/` - Initiates SAML login
- **SLS**: `/sso/saml/sls/` - Single Logout Service
