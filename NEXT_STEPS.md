# Next Steps: SJCME Migration to django-forms-workflows

## Quick Reference

This document provides actionable next steps for completing the migration.

## Phase 1: Package Enhancements (Current Phase)

### 1. Enhance UserProfile Model ⏱️ 2-3 days

**File**: `django_forms_workflows/models.py`

**Changes Needed**:
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='forms_profile')
    
    # Existing
    external_id = models.CharField(max_length=100, blank=True)
    
    # ADD THESE:
    id_number = models.CharField(max_length=50, blank=True, 
        help_text="From LDAP extensionAttribute1")
    department = models.CharField(max_length=200, blank=True,
        help_text="From LDAP department attribute")
    title = models.CharField(max_length=200, blank=True,
        help_text="From LDAP title attribute")
    phone = models.CharField(max_length=50, blank=True,
        help_text="From LDAP telephoneNumber attribute")
    manager_dn = models.CharField(max_length=500, blank=True,
        help_text="From LDAP manager attribute")
```

**New File**: `django_forms_workflows/signals.py`

**Create Signal**:
```python
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

@receiver(user_logged_in)
def sync_ldap_profile(sender, user, request, **kwargs):
    """Sync LDAP attributes to UserProfile on login"""
    # Implementation here
```

**Migration**:
```bash
python manage.py makemigrations django_forms_workflows
python manage.py migrate
```

**Testing**:
- [ ] Create migration
- [ ] Test signal on login
- [ ] Verify LDAP attributes sync
- [ ] Test with missing LDAP attributes

---

### 2. Add Database Introspection ⏱️ 2-3 days

**File**: `django_forms_workflows/data_sources/database_source.py`

**Add Methods**:
```python
class DatabaseDataSource(DataSource):
    # Existing methods...
    
    def get_available_tables(self, schema='dbo'):
        """Get list of tables in schema"""
        # Port from form-workflows/workflows/db_sources.py
        
    def get_table_columns(self, schema, table):
        """Get list of columns in table"""
        # Port from form-workflows/workflows/db_sources.py
        
    def test_connection(self):
        """Test database connection"""
        # Port from form-workflows/workflows/db_sources.py
```

**Source**: `form-workflows/workflows/db_sources.py` lines 190-253

**Testing**:
- [ ] Test with SQL Server
- [ ] Test with PostgreSQL
- [ ] Test with invalid credentials
- [ ] Test with missing database

---

### 3. Add Utility Functions ⏱️ 1-2 days

**New File**: `django_forms_workflows/utils.py`

**Functions to Add**:
```python
def user_can_submit_form(user, form_definition):
    """Check if user can submit form"""
    # Port from form-workflows/workflows/utils.py
    
def user_can_view_form(user, form_definition):
    """Check if user can view form"""
    # Port from form-workflows/workflows/utils.py
    
def user_can_approve(user, submission):
    """Check if user can approve submission"""
    # Port from form-workflows/workflows/utils.py
    
def check_escalation_needed(submission):
    """Check if submission needs escalation"""
    # Port from form-workflows/workflows/utils.py
    
def get_ldap_attribute(user, attr_name):
    """Get LDAP attribute for user"""
    # Port from form-workflows/workflows/utils.py
    
def get_user_manager(user):
    """Get user's manager from LDAP"""
    # Port from form-workflows/workflows/utils.py
```

**Source**: `form-workflows/workflows/utils.py`

**Testing**:
- [ ] Test permission checks
- [ ] Test LDAP attribute retrieval
- [ ] Test manager lookup
- [ ] Test escalation logic

---

### 4. Add Management Commands ⏱️ 2-3 days

**File**: `django_forms_workflows/management/commands/test_db_connection.py`

```python
from django.core.management.base import BaseCommand
from django_forms_workflows.data_sources.database_source import DatabaseDataSource

class Command(BaseCommand):
    help = 'Test external database connection'
    
    def add_arguments(self, parser):
        parser.add_argument('--database', type=str, default='campuscafe')
    
    def handle(self, *args, **options):
        # Test connection
        # Port from form-workflows/workflows/db_sources.py
```

**File**: `django_forms_workflows/management/commands/sync_ldap_profiles.py`

```python
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django_forms_workflows.models import UserProfile

class Command(BaseCommand):
    help = 'Sync LDAP attributes to UserProfile for all users'
    
    def handle(self, *args, **options):
        # Bulk sync all users
        # Similar to signal but for all users
```

**Testing**:
- [ ] Test `test_db_connection` command
- [ ] Test `sync_ldap_profiles` command
- [ ] Test with various options
- [ ] Document in README

---

### 5. Enhance Documentation ⏱️ 3-5 days

**File**: `docs/SQL_SERVER_SETUP.md` (NEW)

```markdown
# SQL Server Configuration

## Installation

```bash
pip install django-forms-workflows[mssql]
```

## Configuration

```python
DATABASES = {
    'campuscafe': {
        'ENGINE': 'mssql',
        'NAME': 'CampusCafe',
        'HOST': 'sql-server.example.com',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    }
}

FORMS_WORKFLOWS = {
    'DATABASE_SOURCE': {
        'database_alias': 'campuscafe',
        'user_id_field': 'id_number',
        'default_schema': 'dbo',
    }
}
```
```

**File**: `docs/LDAP_SETUP.md` (NEW)

```markdown
# LDAP Configuration

## Installation

```bash
pip install django-forms-workflows[ldap]
```

## Configuration

[Complete LDAP setup guide]
```

**File**: `docs/SJCME_MIGRATION.md` (NEW)

```markdown
# Migrating from SJCME Custom Implementation

Step-by-step guide for SJCME to migrate to the package.

[Complete migration guide]
```

**Tasks**:
- [ ] Create SQL Server setup guide
- [ ] Create LDAP setup guide
- [ ] Create SJCME migration guide
- [ ] Update main README
- [ ] Add examples to docs

---

## Phase 2: SJCME Migration (After Phase 1)

### Week 1: Installation & Configuration

**Day 1-2**: Install Package
```bash
# In SJCME environment
pip install django-forms-workflows[ldap,mssql]>=0.4.0
```

**Update settings.py**:
```python
INSTALLED_APPS = [
    # ... existing apps
    'django_forms_workflows',  # ADD THIS
]

# ADD THIS:
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

**Run migrations**:
```bash
python manage.py migrate django_forms_workflows
```

**Tasks**:
- [ ] Install package
- [ ] Update settings
- [ ] Run migrations
- [ ] Test basic functionality

---

**Day 3-4**: Remove Duplicate Code

**Files to DELETE**:
- [ ] `workflows/models.py` (import from package)
- [ ] `workflows/forms.py` (import from package)
- [ ] `workflows/views.py` (use package views)
- [ ] `workflows/admin.py` (use package admin)
- [ ] `workflows/tasks.py` (import from package)
- [ ] `workflows/models_user_profile.py` (use package)

**Files to SIMPLIFY**:
- [ ] `workflows/db_sources.py` (keep only custom queries)
- [ ] `workflows/utils.py` (keep only SJCME-specific)
- [ ] `workflows/urls.py` (use package URLs)

**Update imports**:
```python
# OLD:
from workflows.models import FormDefinition, FormSubmission
from workflows.forms import DynamicForm

# NEW:
from django_forms_workflows.models import FormDefinition, FormSubmission
from django_forms_workflows.forms import DynamicForm
```

---

**Day 5**: Testing

**Test Checklist**:
- [ ] Admin interface loads
- [ ] Can create forms
- [ ] Can submit forms
- [ ] Workflows execute correctly
- [ ] Database prefill works
- [ ] Post-approval updates work
- [ ] Email notifications work
- [ ] LDAP authentication works
- [ ] All existing forms work

---

## Phase 3: Deployment

### Week 1: Staging & Production

**Staging Deployment**:
- [ ] Deploy to staging
- [ ] Run full test suite
- [ ] User acceptance testing
- [ ] Performance testing
- [ ] Fix any issues

**Production Deployment**:
- [ ] Create backup
- [ ] Deploy to production
- [ ] Monitor for issues
- [ ] Validate functionality
- [ ] Document any issues

**Cleanup**:
- [ ] Remove old code
- [ ] Update documentation
- [ ] Train team
- [ ] Celebrate! 🎉

---

## Checklist Summary

### Phase 1: Package Enhancements
- [ ] Enhance UserProfile model (2-3 days)
- [ ] Add database introspection (2-3 days)
- [ ] Add utility functions (1-2 days)
- [ ] Add management commands (2-3 days)
- [ ] Enhance documentation (3-5 days)
- [ ] Release v0.4.0

### Phase 2: SJCME Migration
- [ ] Install package (1 day)
- [ ] Remove duplicate code (2 days)
- [ ] Test thoroughly (2 days)

### Phase 3: Deployment
- [ ] Deploy to staging (2 days)
- [ ] Deploy to production (2 days)
- [ ] Cleanup & training (1 day)

---

## Resources

### Documentation
- [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) - High-level overview
- [PORTING_ANALYSIS.md](PORTING_ANALYSIS.md) - Detailed analysis
- [FEATURE_COMPARISON.md](FEATURE_COMPARISON.md) - Feature comparison
- [SJCME_SIMPLIFICATION_PLAN.md](SJCME_SIMPLIFICATION_PLAN.md) - Code removal plan

### Code References
- **SJCME Implementation**: `form-workflows/workflows/`
- **Package Code**: `django_forms_workflows/`
- **Package Docs**: `docs/`

### Support
- **GitHub Issues**: https://github.com/opensensor/django-forms-workflows/issues
- **Email**: matteius@gmail.com

---

## Success Metrics

Track these metrics throughout the migration:

- [ ] Code reduction: Target 86% (3,325 → 475 lines)
- [ ] All forms working: Target 100%
- [ ] All workflows working: Target 100%
- [ ] Test coverage: Target 80%+
- [ ] Documentation complete: Target 100%
- [ ] Team trained: Target 100%
- [ ] Zero downtime deployment: Target 100%

---

## Timeline

```
Week 1-2: Package Enhancements (Core Features)
Week 3:   Package Enhancements (Documentation)
Week 4:   SJCME Migration
Week 5:   Deployment

Total: 5 weeks
```

---

## Getting Started

**Today**:
1. Review all documentation
2. Get stakeholder approval
3. Set up project tracking
4. Allocate resources

**This Week**:
1. Start UserProfile enhancements
2. Set up development environment
3. Create feature branch
4. Begin implementation

**Next Week**:
1. Continue implementation
2. Write tests
3. Update documentation
4. Prepare for review

---

## Questions?

If you have questions about any of these steps, refer to the detailed documentation or contact the package maintainer.

Good luck with the migration! 🚀

