# Porting Analysis: SJCME form-workflows → django-forms-workflows

## Executive Summary

This document analyzes the original SJCME implementation (`form-workflows/`) and identifies features that need to be ported to the published `django-forms-workflows` package (v0.3.0) to enable the SJCME codebase to use the PyPI package and simplify their implementation.

## Current Status

### Published Package (django-forms-workflows v0.3.0)
- ✅ Core form builder with 15+ field types
- ✅ Workflow engine with approval logic (all/any/sequence)
- ✅ Data sources framework (LDAP, Database, User)
- ✅ Post-submission actions framework (Database, LDAP, API handlers)
- ✅ Multi-step forms with client-side enhancements
- ✅ PrefillSource model for configurable pre-fills
- ✅ Celery task integration
- ✅ Audit logging
- ✅ Admin interface with form builder

### Original SJCME Implementation (form-workflows/)
- ✅ All core features above
- ✅ Campus Cafe database integration (SQL Server)
- ✅ LDAP authentication with django-auth-ldap
- ✅ UserProfile model with ID number sync
- ✅ Database prefill with `{{ dbo.STBIOS.COLUMN }}` syntax
- ✅ Post-approval database updates
- ✅ Email notifications via Celery
- ✅ Deployment configuration (Docker, K8s)

## Features to Port

### 1. UserProfile Model Enhancements ⚠️ CRITICAL

**Status**: Partially implemented in package

**SJCME Implementation** (`form-workflows/workflows/models_user_profile.py`):
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    id_number = models.CharField(max_length=50, blank=True)  # From LDAP extensionAttribute1
    department = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    manager_dn = models.CharField(max_length=500, blank=True)
```

**Package Implementation** (`django_forms_workflows/models.py`):
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='forms_profile')
    external_id = models.CharField(max_length=100, blank=True)
    # Missing: department, title, phone, manager_dn
```

**Action Required**:
- ✅ Add LDAP attribute fields to UserProfile
- ✅ Add signal to auto-sync LDAP attributes on login
- ✅ Add management command to bulk sync user profiles

### 2. Database Source Improvements ⚠️ NEEDS ENHANCEMENT

**SJCME Implementation** (`form-workflows/workflows/db_sources.py`):
- Helper functions: `get_user_data_by_id()`, `get_user_row_by_id()`
- Table/column introspection: `get_available_tables()`, `get_table_columns()`
- Update functions: `update_user_data_by_id()`, `execute_db_updates()`
- Connection testing: `test_connection()`

**Package Implementation** (`django_forms_workflows/data_sources/database_source.py`):
- ✅ Basic database querying
- ❌ Missing introspection helpers
- ❌ Missing connection testing utilities

**Action Required**:
- Add database introspection utilities for admin UI
- Add connection testing functionality
- Document configuration for SQL Server (mssql-django)

### 3. Legacy db_update_mappings Support ✅ IMPLEMENTED

**Status**: Already supported in package via `WorkflowDefinition.db_update_mappings`

The package's `workflow_engine.py` already has backward compatibility:
```python
def execute_post_approval_updates(submission: FormSubmission) -> None:
    # Execute new post-submission actions
    execute_post_submission_actions(submission, "on_approve")
    
    # Legacy support for db_update_mappings
    if workflow and getattr(workflow, "enable_db_updates", False):
        mappings = getattr(workflow, "db_update_mappings", None)
```

**Action Required**: ✅ None - already implemented

### 4. Email Template Improvements 📧

**SJCME Implementation** (`form-workflows/templates/emails/`):
- `approval_request.html`
- `approval_notification.html`
- `rejection_notification.html`
- `approval_reminder.html`
- `escalation_notification.html`
- `submission_notification.html`

**Package Implementation** (`django_forms_workflows/templates/`):
- ✅ Has email templates
- ⚠️ May need review for completeness

**Action Required**:
- Review and enhance email templates
- Ensure all notification types are covered
- Add customization documentation

### 5. Management Commands 🛠️

**SJCME Implementation**:
- `test_workflow.py` - Create test workflows
- `sync_ldap_groups.py` - Sync LDAP groups
- `check_db_connection.py` - Test database connections

**Package Implementation**:
- ✅ `seed_farm_demo.py` - Demo data seeding

**Action Required**:
- Add `test_db_connection` management command
- Add `sync_ldap_profiles` management command
- Document management commands in README

### 6. Utility Functions 🔧

**SJCME Implementation** (`form-workflows/workflows/utils.py`):
```python
def get_ldap_attribute(user, attr_name)
def get_user_manager(user)
def sync_ldap_groups()
def user_can_submit_form(user, form_definition)
def user_can_view_form(user, form_definition)
def user_can_approve(user, submission)
def check_escalation_needed(submission)
```

**Package Implementation**:
- ✅ Permission checks in views
- ❌ Missing standalone utility functions
- ❌ Missing LDAP helper functions

**Action Required**:
- Extract permission checks to `utils.py`
- Add LDAP utility functions
- Add escalation checking utilities

### 7. Documentation 📚

**SJCME Implementation**:
- `DATABASE_PREFILL_GUIDE.md` - Comprehensive prefill guide
- `POST_APPROVAL_DB_UPDATES_GUIDE.md` - Database update guide
- `DEPLOYMENT.md` - Deployment instructions
- `QUICKSTART.md` - Quick start guide

**Package Implementation**:
- ✅ `docs/PREFILL_SOURCES.md`
- ✅ `docs/POST_SUBMISSION_ACTIONS.md`
- ✅ `docs/QUICKSTART.md`
- ⚠️ May need SJCME-specific examples

**Action Required**:
- Add SQL Server configuration examples
- Add LDAP configuration examples
- Add Campus Cafe-style database integration guide
- Create migration guide from SJCME to package

## Migration Path for SJCME

### Phase 1: Package Enhancements (1-2 weeks)
1. ✅ Add UserProfile LDAP fields
2. ✅ Add LDAP sync signals and management commands
3. ✅ Add database introspection utilities
4. ✅ Add utility functions for permissions and LDAP
5. ✅ Enhance documentation with SQL Server examples

### Phase 2: SJCME Migration (1 week)
1. Install `django-forms-workflows` package
2. Update `settings.py` to configure package
3. Migrate models to use package models
4. Update views to use package views
5. Migrate templates to extend package templates
6. Test all workflows

### Phase 3: Cleanup (1 week)
1. Remove duplicate code from SJCME
2. Keep only SJCME-specific customizations
3. Update deployment configuration
4. Final testing and validation

## Dependencies to Add

The package already has most dependencies, but ensure these are documented:

```toml
[tool.poetry.extras]
ldap = ["django-auth-ldap", "python-ldap"]
mssql = ["mssql-django", "pyodbc"]
```

## Configuration Example for SJCME

```python
# settings.py
INSTALLED_APPS = [
    ...
    'django_forms_workflows',
]

FORMS_WORKFLOWS = {
    'DATABASE_SOURCE': {
        'database_alias': 'campuscafe',
        'user_id_field': 'id_number',
        'default_schema': 'dbo',
        'lookup_field': 'ID_NUMBER',
    },
    'LDAP_SYNC': {
        'enabled': True,
        'sync_on_login': True,
        'attributes': {
            'id_number': 'extensionAttribute1',
            'department': 'department',
            'title': 'title',
            'phone': 'telephoneNumber',
            'manager_dn': 'manager',
        }
    }
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        ...
    },
    'campuscafe': {
        'ENGINE': 'mssql',
        'NAME': 'CampusCafe',
        'HOST': 'sql-server.sjcme.edu',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    }
}
```

## Estimated Effort

- **Package Enhancements**: 40-60 hours
- **SJCME Migration**: 20-30 hours
- **Testing & Documentation**: 20-30 hours
- **Total**: 80-120 hours (2-3 weeks)

## Success Criteria

1. ✅ SJCME can install django-forms-workflows from PyPI
2. ✅ All existing SJCME forms work with the package
3. ✅ Database prefill works with Campus Cafe
4. ✅ Post-approval database updates work
5. ✅ LDAP authentication and sync work
6. ✅ Email notifications work
7. ✅ SJCME codebase is simplified (50%+ code reduction)
8. ✅ All tests pass
9. ✅ Documentation is complete

## Next Steps

1. Review this analysis with stakeholders
2. Prioritize features to port
3. Create detailed implementation tasks
4. Begin Phase 1 enhancements
5. Test with SJCME staging environment
6. Execute migration plan

