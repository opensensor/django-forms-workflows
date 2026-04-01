# Quick Start Guide

Get Django Forms Workflows up and running in 10 minutes!

> **Current release:** v0.48.0 · [Changelog](../CHANGELOG.md) · [Full Docs index](../README.md)

## Prerequisites

- Python 3.10 or higher
- Django 5.2 or higher
- PostgreSQL 14+ (recommended) or MySQL 8.0+

## Installation

### 1. Install the Package

```bash
# Core package
pip install django-forms-workflows

# With Excel spreadsheet field support
pip install "django-forms-workflows[excel]"

# With LDAP/AD support
pip install "django-forms-workflows[ldap]"

# With PDF export support
pip install "django-forms-workflows[pdf]"

# Everything
pip install "django-forms-workflows[all]"
```

### 2. Update Django Settings

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
    
    # Required dependencies
    'crispy_forms',
    'crispy_bootstrap5',
    
    # Django Forms Workflows
    'django_forms_workflows',
    
    # Your apps
    # ...
]

# Crispy Forms Configuration
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Forms Workflows Configuration (optional)
FORMS_WORKFLOWS = {
    # Replace "Django Forms Workflows" branding across all templates
    'SITE_NAME': 'My Org Workflows',
    'ENABLE_APPROVALS': True,
    'ENABLE_AUDIT_LOG': True,
    'ENABLE_FILE_UPLOADS': True,
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
}

# Optional context processor — injects site_name into templates
# Add this to your TEMPLATES setting:
# 'django_forms_workflows.context_processors.forms_workflows'
```

### 3. Update URLs

```python
# urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('forms/', include('django_forms_workflows.urls')),
]
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
python manage.py runserver
```

## Create Your First Form

### 1. Access Django Admin

Navigate to `http://localhost:8000/admin/` and log in.

### 2. Create a Form Definition

1. Go to **Forms Workflows** → **Form Definitions**
2. Click **Add Form Definition**
3. Fill in:
   - **Name**: Travel Request
   - **Slug**: travel-request
   - **Description**: Request approval for business travel
   - **Is Active**: ✓ (checked)

### 3. Add Form Fields

In the **Form Fields** inline section, add these fields:

#### Field 1: Destination
- **Field Name**: destination
- **Field Label**: Destination
- **Field Type**: Single Line Text
- **Required**: ✓
- **Order**: 1

#### Field 2: Start Date
- **Field Name**: start_date
- **Field Label**: Start Date
- **Field Type**: Date
- **Required**: ✓
- **Order**: 2

#### Field 3: End Date
- **Field Name**: end_date
- **Field Label**: End Date
- **Field Type**: Date
- **Required**: ✓
- **Order**: 3

#### Field 4: Purpose
- **Field Name**: purpose
- **Field Label**: Purpose of Travel
- **Field Type**: Multi-line Text
- **Required**: ✓
- **Order**: 4

#### Field 5: Estimated Cost
- **Field Name**: estimated_cost
- **Field Label**: Estimated Cost
- **Field Type**: Decimal/Currency
- **Required**: ✓
- **Order**: 5

### 4. Save the Form

Click **Save** at the bottom of the page.

### 5. View Your Form

Navigate to `http://localhost:8000/forms/travel-request/`

You should see your form rendered beautifully with Bootstrap styling!

## Add Approval Workflow

### 1. Create Approval Groups

1. Go to **Authentication and Authorization** → **Groups**
2. Create a **Travel Approvers** group
3. Optionally create a **Finance Approvers** group for a second stage
4. Add your reviewer users to the appropriate groups

### 2. Create a Workflow Definition

1. Go to **Forms Workflows** → **Workflow Definitions**
2. Click **Add Workflow Definition**
3. Fill in:
   - **Form Definition**: Travel Request
   - **Requires Approval**: ✓
   - **Name Label**: Travel Approval
   - **Approval Deadline Days**: 5 *(optional)*
   - **Notification Cadence**: Immediate

### 3. Add Workflow Stages

In the **Workflow Stages** inline, add:

#### Stage 1: Manager Review
- **Name**: Manager Review
- **Order**: 1
- **Approval Logic**: All must approve
- **Approval Groups**: Travel Approvers
- **Allow Send Back**: ✓ *(optional, makes this a correction target for later stages)*

#### Stage 2: Finance Review
- **Name**: Finance Review
- **Order**: 2
- **Approval Logic**: All must approve
- **Approval Groups**: Finance Approvers
- **Approve Label**: Sign Off *(optional)*

### 4. Optional Advanced Stage Features

After saving the basic workflow, you can enable richer routing per stage:

- **Dynamic assignee** — set `assignee_form_field` + `assignee_lookup_type`
- **Conditional stage** — add `trigger_conditions` JSON
- **Reassignment** — enable `allow_reassign`
- **Editable submission data** — enable `allow_edit_form_data`
- **Manager-first approval** — enable `requires_manager_approval`

You can also create multiple `WorkflowDefinition` rows on the same form if you want **parallel approval tracks**.

### 5. Test the Workflow

1. Submit the form as a regular user
2. Log in as an approver
3. Go to `http://localhost:8000/forms/approvals/`
4. Approve or reject the submission
5. If you created multiple stages, confirm stage 2 is only created after stage 1 completes

For a full explanation of staged, parallel, conditional, and dynamic workflows, see [Workflows Guide](WORKFLOWS.md).

## Add Prefill from User Profile

### 1. Edit a Form Field

1. Go back to your **Travel Request** form
2. Add a new field:
   - **Field Name**: requester_email
   - **Field Label**: Your Email
   - **Field Type**: Email Address
   - **Prefill Source**: Current User - Email
   - **Order**: 0

### 2. Test Prefill

When you view the form while logged in, the email field will be automatically filled with your email address!

## Next Steps

### Enable LDAP Integration

See [LDAP Configuration Guide](CONFIGURATION.md#ldap-integration) to:
- Authenticate users against Active Directory
- Prefill fields from LDAP attributes (department, title, manager, etc.)
- Use `assignee_lookup_type = "ldap"` for manager-routing on approval stages

### Enable Dynamic Assignees

See [Dynamic Assignees](DYNAMIC_ASSIGNEES.md) to route approval tasks to the specific individual named in a form field (by email, username, or display name).

### Model Richer Approval Flows

See [Workflows Guide](WORKFLOWS.md) for multi-stage, parallel-track, conditional, reassignment, editable-review, and deadline/reminder features.

### Use the Visual Workflow Builder Safely

See [Visual Workflow Builder](VISUAL_WORKFLOW_BUILDER.md) for what the builder supports today versus which advanced workflow settings still need Django Admin.

### Use Calculated / Formula Fields

See [Calculated Fields Guide](CALCULATED_FIELDS.md) to auto-compute read-only values from other field inputs, including spreadsheet-structured file uploads.

### Enable Send Back for Correction

See [Send Back for Correction](SEND_BACK.md) to let approvers return submissions to any prior stage without terminating the workflow.

### Spawn Child Approval Flows

See [Sub-Workflows Guide](SUB_WORKFLOWS.md) to create repeated child approval chains from a single parent submission.

### Enable Database Prefill

See [Database Integration Guide](CONFIGURATION.md#database-integration) to:
- Query external databases for prefill data
- Use syntax like `{{ db.hr.employees.department }}`

### Customize Templates

Copy templates from the package to your project:

```bash
mkdir -p templates/django_forms_workflows
python -c "import django_forms_workflows, os; print(os.path.dirname(django_forms_workflows.__file__))"
# Copy from the path printed above/templates/ to your templates/django_forms_workflows/
```

Then customize as needed!

### Add Celery for Background Tasks

For async email notifications, batched digests, reminders, and deadline checks:

```bash
pip install celery redis
```

```python
# settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

```bash
# Run Celery worker
celery -A your_project worker -l info

# Run Celery beat scheduler (for reminders, auto-approval, and digest checks)
celery -A your_project beat -l info
```

## Common Issues

### Forms not showing up

- Check that `is_active=True` on the Form Definition
- Check that you have permission to view the form
- Check the URL matches the form slug

### Prefill not working

- Check that the user is authenticated
- Check that the prefill source is configured correctly
- Check logs for errors: `python manage.py runserver --verbosity=2`

### Approvals not working

- Check that a Workflow Definition exists for the form
- Check that the workflow has at least one stage
- Check that approval groups are configured
- Check that approvers are in the correct groups

## Getting Help

- 📖 [Full Documentation](../README.md)
- 💬 [GitHub Discussions](https://github.com/opensensor/django-forms-workflows/discussions)
- 🐛 [Issue Tracker](https://github.com/opensensor/django-forms-workflows/issues)

## Example Project

Check out the example project in the repository:

```bash
git clone https://github.com/opensensor/django-forms-workflows.git
cd django-forms-workflows/example_project
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The example project includes:
- Pre-configured forms
- Sample workflows
- LDAP integration example
- Database prefill example
- Custom data source example

