# SJCME Codebase Simplification Plan

## Overview

This document outlines what code can be removed from the SJCME `form-workflows/` implementation once it migrates to using the `django-forms-workflows` PyPI package.

## Current SJCME Codebase Structure

```
form-workflows/
├── workflows/                    # Django app
│   ├── models.py                # 350+ lines - REPLACE with package
│   ├── forms.py                 # 200+ lines - REPLACE with package
│   ├── views.py                 # 570+ lines - REPLACE with package
│   ├── admin.py                 # 300+ lines - REPLACE with package
│   ├── db_sources.py            # 420+ lines - MOSTLY REPLACE
│   ├── utils.py                 # 225+ lines - REPLACE with package
│   ├── tasks.py                 # 310+ lines - REPLACE with package
│   ├── urls.py                  # ~50 lines - SIMPLIFY
│   ├── ldap_backend.py          # ~100 lines - KEEP (customized)
│   └── models_user_profile.py   # ~50 lines - REPLACE with package
├── config/
│   ├── settings.py              # ~400 lines - SIMPLIFY
│   └── urls.py                  # ~30 lines - SIMPLIFY
├── templates/                   # EXTEND package templates
└── static/                      # KEEP custom CSS/JS
```

## Files to REMOVE (Complete Replacement)

### 1. `workflows/models.py` (350+ lines) → Package
**Reason**: Package provides all models

**SJCME Models** → **Package Models**:
- `FormDefinition` → `django_forms_workflows.models.FormDefinition`
- `FormField` → `django_forms_workflows.models.FormField`
- `WorkflowDefinition` → `django_forms_workflows.models.WorkflowDefinition`
- `FormSubmission` → `django_forms_workflows.models.FormSubmission`
- `ApprovalTask` → `django_forms_workflows.models.ApprovalTask`
- `AuditLog` → `django_forms_workflows.models.AuditLog`

**Code Reduction**: ~350 lines → 0 lines (import from package)

### 2. `workflows/forms.py` (200+ lines) → Package
**Reason**: Package provides DynamicForm

**SJCME Code**:
```python
class DynamicForm(forms.Form):
    def __init__(self, form_definition, user=None, initial_data=None, *args, **kwargs):
        # 200+ lines of field building logic
```

**Package Usage**:
```python
from django_forms_workflows.forms import DynamicForm
# Just import and use
```

**Code Reduction**: ~200 lines → 1 import line

### 3. `workflows/admin.py` (300+ lines) → Package
**Reason**: Package provides complete admin interface

**SJCME Code**:
```python
@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    # 300+ lines of admin configuration
```

**Package Usage**:
```python
# No custom admin needed - package provides everything
# Or extend if needed:
from django_forms_workflows.admin import FormDefinitionAdmin as BaseFormDefinitionAdmin

class FormDefinitionAdmin(BaseFormDefinitionAdmin):
    # Only add SJCME-specific customizations
    pass
```

**Code Reduction**: ~300 lines → 0-20 lines (if customization needed)

### 4. `workflows/views.py` (570+ lines) → Package
**Reason**: Package provides all views

**SJCME Views** → **Package Views**:
- `form_list` → `django_forms_workflows.views.form_list`
- `form_submit` → `django_forms_workflows.views.form_submit`
- `submission_detail` → `django_forms_workflows.views.submission_detail`
- `approval_dashboard` → `django_forms_workflows.views.approval_dashboard`
- `process_approval` → `django_forms_workflows.views.process_approval`

**Code Reduction**: ~570 lines → 0 lines (use package URLs)

### 5. `workflows/tasks.py` (310+ lines) → Package
**Reason**: Package provides Celery tasks

**SJCME Tasks** → **Package Tasks**:
- `send_submission_notification` → `django_forms_workflows.tasks.send_submission_notification`
- `send_approval_notification` → `django_forms_workflows.tasks.send_approval_notification`
- `send_rejection_notification` → `django_forms_workflows.tasks.send_rejection_notification`
- `check_approval_deadlines` → `django_forms_workflows.tasks.check_approval_deadlines`

**Code Reduction**: ~310 lines → 0 lines (import from package)

### 6. `workflows/models_user_profile.py` (50+ lines) → Package
**Reason**: Package provides UserProfile model (after enhancement)

**Code Reduction**: ~50 lines → 0 lines

## Files to SIMPLIFY (Partial Replacement)

### 1. `workflows/db_sources.py` (420 lines) → Mostly Package

**Keep Only**:
- SJCME-specific database queries (if any)
- Custom Campus Cafe integration logic (if needed)

**Remove**:
- `get_user_data_by_id()` → Use package's DatabaseDataSource
- `get_user_row_by_id()` → Use package's DatabaseDataSource
- `update_user_data_by_id()` → Use package's DatabaseUpdateHandler
- `execute_db_updates()` → Use package's PostSubmissionAction

**Code Reduction**: ~420 lines → ~50 lines (90% reduction)

### 2. `workflows/utils.py` (225 lines) → Package

**Remove**:
- `user_can_submit_form()` → Package provides this
- `user_can_view_form()` → Package provides this
- `user_can_approve()` → Package provides this
- `check_escalation_needed()` → Package provides this

**Keep Only**:
- SJCME-specific utility functions (if any)

**Code Reduction**: ~225 lines → ~20 lines (90% reduction)

### 3. `workflows/urls.py` (50 lines) → Simplify

**SJCME Code**:
```python
urlpatterns = [
    path('', views.home, name='home'),
    path('forms/', views.form_list, name='form_list'),
    path('forms/<slug:slug>/', views.form_submit, name='form_submit'),
    # ... 20+ URL patterns
]
```

**Package Usage**:
```python
from django.urls import path, include

urlpatterns = [
    path('', include('django_forms_workflows.urls')),
    # Add only SJCME-specific URLs if needed
]
```

**Code Reduction**: ~50 lines → ~5 lines (90% reduction)

### 4. `config/settings.py` (400 lines) → Simplify

**Remove**:
- Custom form/workflow settings → Use `FORMS_WORKFLOWS` dict
- Duplicate middleware/apps → Package handles this

**Keep**:
- SJCME-specific settings (LDAP, databases, email)
- Deployment settings (static files, security)

**Add**:
```python
INSTALLED_APPS = [
    ...
    'django_forms_workflows',  # Add package
]

FORMS_WORKFLOWS = {
    'DATABASE_SOURCE': {
        'database_alias': 'campuscafe',
        'user_id_field': 'id_number',
        'default_schema': 'dbo',
    },
    'LDAP_SYNC': {
        'enabled': True,
        'sync_on_login': True,
    }
}
```

**Code Reduction**: ~400 lines → ~300 lines (25% reduction)

### 5. `config/urls.py` (30 lines) → Simplify

**SJCME Code**:
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('workflows.urls')),
]
```

**Package Usage**:
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('django_forms_workflows.urls')),
]
```

**Code Reduction**: ~30 lines → ~10 lines (65% reduction)

## Files to KEEP (SJCME-Specific)

### 1. `workflows/ldap_backend.py` (~100 lines)
**Reason**: SJCME-specific LDAP configuration

**Keep**:
- Custom LDAP attribute mappings
- SJCME-specific authentication logic

**Possible Enhancement**: Contribute generic parts to package

### 2. `templates/` (Custom Templates)
**Action**: Extend package templates instead of replacing

**Before**:
```html
<!-- templates/workflows/form_list.html -->
<html>
  <head>...</head>
  <body>
    <!-- 100+ lines of custom HTML -->
  </body>
</html>
```

**After**:
```html
<!-- templates/workflows/form_list.html -->
{% extends "django_forms_workflows/form_list.html" %}

{% block extra_header %}
  <!-- SJCME-specific header -->
{% endblock %}

{% block extra_content %}
  <!-- SJCME-specific content -->
{% endblock %}
```

**Code Reduction**: ~80% reduction in template code

### 3. `static/` (Custom CSS/JS)
**Keep**: SJCME branding and custom styles

**Action**: Override package static files as needed

### 4. Deployment Files
**Keep**:
- `Dockerfile`
- `docker-compose.yml`
- `k8s/` directory
- `requirements.txt` (but simplify)

**Simplify `requirements.txt`**:
```txt
# Before: 30+ dependencies
# After: ~10 dependencies + package

django-forms-workflows[ldap,mssql]>=0.3.0
gunicorn>=22.0.0
whitenoise>=6.6.0
# ... SJCME-specific dependencies only
```

## Total Code Reduction

| Category | Before | After | Reduction |
|----------|--------|-------|-----------|
| Models | 350 lines | 0 lines | 100% |
| Forms | 200 lines | 0 lines | 100% |
| Views | 570 lines | 0 lines | 100% |
| Admin | 300 lines | 0 lines | 100% |
| Tasks | 310 lines | 0 lines | 100% |
| DB Sources | 420 lines | 50 lines | 88% |
| Utils | 225 lines | 20 lines | 91% |
| URLs | 50 lines | 5 lines | 90% |
| Settings | 400 lines | 300 lines | 25% |
| Templates | ~500 lines | ~100 lines | 80% |
| **TOTAL** | **~3,325 lines** | **~475 lines** | **86%** |

## Migration Checklist

### Phase 1: Preparation
- [ ] Review PORTING_ANALYSIS.md
- [ ] Ensure package has all needed features
- [ ] Create backup of current SJCME codebase
- [ ] Set up test environment

### Phase 2: Installation
- [ ] Install `django-forms-workflows` package
- [ ] Update `requirements.txt`
- [ ] Update `settings.py` with `FORMS_WORKFLOWS` config
- [ ] Run migrations

### Phase 3: Code Removal
- [ ] Remove `workflows/models.py` (import from package)
- [ ] Remove `workflows/forms.py` (import from package)
- [ ] Remove `workflows/views.py` (use package views)
- [ ] Remove `workflows/admin.py` (use package admin)
- [ ] Remove `workflows/tasks.py` (import from package)
- [ ] Simplify `workflows/db_sources.py`
- [ ] Simplify `workflows/utils.py`
- [ ] Update `workflows/urls.py` to use package URLs
- [ ] Update `config/urls.py`

### Phase 4: Template Migration
- [ ] Extend package templates instead of custom templates
- [ ] Keep only SJCME-specific template overrides
- [ ] Test all pages render correctly

### Phase 5: Testing
- [ ] Test form creation in admin
- [ ] Test form submission
- [ ] Test approval workflows
- [ ] Test database prefill
- [ ] Test post-approval database updates
- [ ] Test email notifications
- [ ] Test LDAP authentication
- [ ] Run full test suite

### Phase 6: Deployment
- [ ] Update deployment configuration
- [ ] Deploy to staging
- [ ] Validate in staging
- [ ] Deploy to production
- [ ] Monitor for issues

## Benefits

1. **Maintainability**: 86% less code to maintain
2. **Updates**: Get package updates automatically
3. **Bug Fixes**: Benefit from community bug fixes
4. **Features**: Get new features from package
5. **Documentation**: Use package documentation
6. **Testing**: Package is tested independently
7. **Community**: Contribute back to open source

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Package missing features | Complete porting analysis first |
| Breaking changes | Pin package version, test thoroughly |
| Custom logic lost | Document all customizations |
| Migration complexity | Phased approach, extensive testing |
| Downtime | Blue-green deployment |

## Timeline

- **Phase 1-2**: 1 week (preparation + installation)
- **Phase 3-4**: 1 week (code removal + templates)
- **Phase 5**: 1 week (testing)
- **Phase 6**: 1 week (deployment)
- **Total**: 4 weeks (with buffer)

## Success Metrics

- ✅ 80%+ code reduction achieved
- ✅ All existing forms work
- ✅ All workflows function correctly
- ✅ No regression in functionality
- ✅ Deployment successful
- ✅ Team trained on package usage

