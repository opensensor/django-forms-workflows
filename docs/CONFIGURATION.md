# Configuration Guide

This guide covers all configuration options for Django Forms Workflows.

## Table of Contents

- [Basic Setup](#basic-setup)
- [Data Sources](#data-sources)
- [LDAP Integration](#ldap-integration)
- [Database Integration](#database-integration)
- [Workflows](#workflows)
- [Email Notifications](#email-notifications)
- [File Uploads](#file-uploads)
- [Security](#security)
- [Advanced Options](#advanced-options)

---

## Basic Setup

### 1. Install the Package

```bash
# Basic installation
pip install django-forms-workflows

# With LDAP support
pip install django-forms-workflows[ldap]

# With MS SQL Server support
pip install django-forms-workflows[mssql]

# With PostgreSQL support
pip install django-forms-workflows[postgresql]

# With all optional dependencies
pip install django-forms-workflows[all]
```

### 2. Add to INSTALLED_APPS

```python
# settings.py

INSTALLED_APPS = [
    # Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'crispy_forms',
    'crispy_bootstrap5',

    # Django Forms Workflows
    'django_forms_workflows',

    # Your apps
    # ...
]
```

### 3. Configure Crispy Forms

```python
# settings.py

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
```

### 4. Run Migrations

```bash
python manage.py migrate django_forms_workflows
```

### 5. Include URLs

```python
# urls.py

from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('forms/', include('django_forms_workflows.urls')),
    # ...
]
```

---

## Data Sources

Django Forms Workflows supports multiple data sources for prefilling form fields.

### Configuration

```python
# settings.py

FORMS_WORKFLOWS = {
    # Enable/disable features
    'ENABLE_APPROVALS': True,
    'ENABLE_AUDIT_LOG': True,
    'ENABLE_FILE_UPLOADS': True,

    # File upload settings
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
    'ALLOWED_FILE_EXTENSIONS': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'png'],

    # Data source configuration
    'DATABASE_SOURCE': {
        'database_alias': 'external_db',  # Django database alias
        'user_id_field': 'external_id',   # UserProfile field for lookups
        'default_schema': 'dbo',          # Default schema if not specified
    },
}
```

### Built-in Data Sources

1. **User Data Source** (`user.*`)
   - `user.email`
   - `user.first_name`
   - `user.last_name`
   - `user.full_name`
   - `user.username`

2. **LDAP Data Source** (`ldap.*`)
   - `ldap.department`
   - `ldap.title`
   - `ldap.manager`
   - `ldap.phone`
   - `ldap.employee_id`

3. **Database Data Source** (`{{ db.schema.table.column }}`)
   - Query external databases
   - Requires configuration (see below)

### Custom Data Sources

You can register custom data sources:

```python
# myapp/data_sources.py

from django_forms_workflows.data_sources import DataSource, register_data_source

class SalesforceSource(DataSource):
    def get_value(self, user, field_name, **kwargs):
        # Query Salesforce API
        from simple_salesforce import Salesforce
        sf = Salesforce(...)
        contact = sf.Contact.get_by_custom_id('Email', user.email)
        return contact.get(field_name)

    def is_available(self):
        from django.conf import settings
        return hasattr(settings, 'SALESFORCE_CONFIG')

# Register the source
register_data_source('salesforce', SalesforceSource)
```

Then use in forms:
```
prefill_source = "salesforce.AccountName"
```

---

## LDAP Integration

### Installation

```bash
pip install django-forms-workflows[ldap]
```

### Configuration

```python
# settings.py

import ldap
from django_auth_ldap.config import LDAPSearch, ActiveDirectoryGroupType

# LDAP Server Configuration
AUTH_LDAP_SERVER_URI = "ldap://ldap.example.com:389"
AUTH_LDAP_BIND_DN = "CN=Service Account,OU=Service Accounts,DC=example,DC=com"
AUTH_LDAP_BIND_PASSWORD = "your-password"

# Connection options
AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_DEBUG_LEVEL: 0,
    ldap.OPT_REFERRALS: 0,
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_NEVER,
    ldap.OPT_NETWORK_TIMEOUT: 5,  # 5 second timeout
    ldap.OPT_TIMEOUT: 5,
}

# User search
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    "DC=example,DC=com",
    ldap.SCOPE_SUBTREE,
    "(sAMAccountName=%(user)s)"  # For Active Directory
)

# Attribute mapping
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}

# Group search (optional)
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    "DC=example,DC=com",
    ldap.SCOPE_SUBTREE,
    "(objectClass=group)"
)
AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()

# Mirror groups to Django
AUTH_LDAP_MIRROR_GROUPS = True

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django_auth_ldap.backend.LDAPBackend',
    'django.contrib.auth.backends.ModelBackend',  # Fallback
]
```

### Syncing LDAP Attributes to User Profile

Create a custom LDAP backend:

```python
# myapp/ldap_backend.py

from django_auth_ldap.backend import LDAPBackend
from django_forms_workflows.models import UserProfile

class CustomLDAPBackend(LDAPBackend):
    def authenticate_ldap_user(self, ldap_user, password):
        user = super().authenticate_ldap_user(ldap_user, password)

        if user:
            # Sync LDAP attributes to UserProfile
            profile, created = UserProfile.objects.get_or_create(user=user)

            if hasattr(ldap_user, 'attrs'):
                attrs = ldap_user.attrs
                profile.employee_id = attrs.get('employeeID', [''])[0]
                profile.department = attrs.get('department', [''])[0]
                profile.title = attrs.get('title', [''])[0]
                profile.phone = attrs.get('telephoneNumber', [''])[0]
                profile.save()

        return user
```

Then use your custom backend:

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    'myapp.ldap_backend.CustomLDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]
```

---

## Database Integration

### Configuration

```python
# settings.py

DATABASES = {
    'default': {
        # Your primary database (PostgreSQL recommended)
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'forms_db',
        'USER': 'postgres',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5432',
    },
    'external_db': {
        # External database for prefill data
        'ENGINE': 'mssql',  # or 'django.db.backends.mysql', etc.
        'NAME': 'legacy_db',
        'USER': 'readonly_user',
        'PASSWORD': 'password',
        'HOST': 'legacy-server.example.com',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 18 for SQL Server',
            'extra_params': 'TrustServerCertificate=yes',
        },
    },
}

# Configure database source
FORMS_WORKFLOWS = {
    'DATABASE_SOURCE': {
        'database_alias': 'external_db',
        'user_id_field': 'external_id',  # UserProfile field
        'default_schema': 'dbo',
    },
}
```

### Using Database Prefill

In Django Admin, set the `prefill_source` field:

```
{{ db.hr.employees.department }}
{{ db.hr.staff.phone_number }}
{{ employees.email }}  # Uses default schema
```

The system will:
1. Get the user's `external_id` from their UserProfile
2. Query: `SELECT [column] FROM [schema].[table] WHERE ID_NUMBER = ?`
3. Return the value to prefill the form field

