# Django Form Workflows - Example Project

This is a minimal Django project demonstrating how to use the `django-forms-workflows` package.

## Quick Start

1. **Install dependencies**
   ```bash
   pip install django-forms-workflows
   # Or with LDAP support:
   pip install django-forms-workflows[ldap]
   ```

2. **Run migrations**
   ```bash
   python manage.py migrate
   ```

3. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

4. **Run the development server**
   ```bash
   python manage.py runserver
   ```

5. **Access the application**
   - Admin: http://localhost:8000/admin
   - Forms: http://localhost:8000/forms/

## What's Included

This example project demonstrates:

- ✅ Basic Django Form Workflows setup
- ✅ Form creation through Django Admin
- ✅ Simple approval workflow
- ✅ User authentication
- ✅ Form submission and approval views

## Creating Your First Form

1. Log in to Django Admin at http://localhost:8000/admin
2. Go to "Form Definitions" and click "Add Form Definition"
3. Fill in the form details:
   - **Name**: Contact Request
   - **Slug**: contact-request
   - **Description**: A simple contact form
   - **Is Active**: ✓

4. Add form fields:
   - Field 1: Name (text, required)
   - Field 2: Email (email, required)
   - Field 3: Message (textarea, required)

5. Save the form

6. Visit http://localhost:8000/forms/ to see your form

## Configuration

See `settings.py` for configuration options:

- `FORMS_WORKFLOWS_LDAP_ATTR_MAP` - LDAP attribute mapping
- `FORMS_WORKFLOWS_LDAP_SYNC_GROUPS` - Enable/disable group sync
- `FORMS_WORKFLOWS_LDAP_PROFILE_MODEL` - User profile model

## Next Steps

- Read the [Configuration Guide](../docs/CONFIGURATION.md)
- Explore the [Quickstart Guide](../docs/QUICKSTART.md)
- Check out the [Value Proposition](../docs/VALUE_PROPOSITION.md)

## Project Structure

```
example_project/
├── manage.py           # Django management script
├── example/            # Project settings
│   ├── settings.py     # Django settings
│   ├── urls.py         # URL configuration
│   └── wsgi.py         # WSGI configuration
└── README.md           # This file
```

