# Quick Start Guide

Get Django Forms Workflows up and running in 10 minutes!

## Prerequisites

- Python 3.10 or higher
- Django 5.1 or higher
- PostgreSQL 12+ (recommended) or MySQL 8.0+

## Installation

### 1. Install the Package

```bash
pip install django-forms-workflows
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
    'ENABLE_APPROVALS': True,
    'ENABLE_AUDIT_LOG': True,
    'ENABLE_FILE_UPLOADS': True,
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
}
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

### 1. Create a Workflow Definition

1. Go to **Forms Workflows** → **Workflow Definitions**
2. Click **Add Workflow Definition**
3. Fill in:
   - **Form Definition**: Travel Request
   - **Requires Approval**: ✓
   - **Approval Logic**: Any can approve (OR)
   - **Notify on Submission**: ✓
   - **Notify on Approval**: ✓

### 2. Assign Approvers

1. Create a group in Django Admin: **Travel Approvers**
2. Add users to this group
3. In the Workflow Definition, select **Travel Approvers** in **Approval Groups**

### 3. Test the Workflow

1. Submit the form as a regular user
2. Log in as an approver
3. Go to `http://localhost:8000/forms/approvals/`
4. Approve or reject the submission

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

### Enable Database Prefill

See [Database Integration Guide](CONFIGURATION.md#database-integration) to:
- Query external databases for prefill data
- Use syntax like `{{ db.hr.employees.department }}`

### Customize Templates

Copy templates from the package to your project:

```bash
mkdir -p templates/django_forms_workflows
cp -r venv/lib/python3.10/site-packages/django_forms_workflows/templates/* templates/django_forms_workflows/
```

Then customize as needed!

### Add Celery for Background Tasks

For email notifications and scheduled tasks:

```bash
pip install celery redis
```

```python
# settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
```

```bash
# Run Celery worker
celery -A your_project worker -l info
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
- Check that approval groups are configured
- Check that approvers are in the correct groups

## Getting Help

- 📖 [Full Documentation](README.md)
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

