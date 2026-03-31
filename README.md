# Django Forms Workflows

**Enterprise-grade, database-driven form builder with multi-stage approval workflows, external data integration, and cross-instance sync**

[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Django Version](https://img.shields.io/badge/django-5.2%2B-green)](https://www.djangoproject.com/)
[![Version](https://img.shields.io/badge/version-0.37.8-orange)](https://github.com/opensensor/django-forms-workflows)

## Overview

Django Forms Workflows bridges the gap between simple form libraries (like Crispy Forms) and expensive SaaS solutions (like JotForm, Formstack). It provides:

- 📝 **Database-Driven Forms** — Define forms in the database, not code. 25+ field types including calculated/formula fields and spreadsheet uploads.
- 🔄 **Multi-Stage Approval Workflows** — Sequential, parallel, or hybrid approval flows with configurable stages and conditional trigger logic.
- ↩️ **Send Back for Correction** — Approvers can return a submission to any prior stage without terminating the workflow.
- 🎯 **Dynamic Assignees** — Resolve individual approvers at submit time from form field values (email, username, full name, or LDAP lookup).
- 🔀 **Sub-Workflows** — Spawn child workflows from a parent submission (e.g. one form creates N payment approvals).
- 🔌 **External Data Integration** — Prefill fields from LDAP, databases, REST APIs, or the Django user model.
- ⚡ **Post-Submission Actions** — Trigger emails, database writes, LDAP updates, or custom Python handlers on submit/approve/reject.
- 🔄 **Cross-Instance Sync** — Push/pull form definitions between environments directly from the Django Admin.
- 🔒 **Enterprise Security** — LDAP/AD & SSO authentication, RBAC with four permission tiers, complete audit trails.
- 🌐 **REST API** — Opt-in Bearer-token API: list forms, fetch field schema, submit (or save draft), poll status. OpenAPI 3.0 schema + Swagger UI included.
- 📁 **Managed File Uploads** — File uploads with approval, rejection, and version tracking per submission.
- 🧮 **Formula Fields** — Calculated fields that compute values live from other field values using a template formula.
- 🏠 **Self-Hosted** — No SaaS fees, full data control.

## Key Features

### 🎯 No-Code Form Creation
Business users create and modify forms through Django Admin:
- **25+ field types:** text, email, phone, select, radio, checkbox, checkboxes, multiselect, date, time, datetime, decimal, currency, number, URL, file, multi-file, textarea, hidden, section headers, **calculated/formula**, **spreadsheet upload (CSV/Excel)**, country picker, US state picker, **signature (draw or type)**
- Field ordering with explicit `order` integer
- Column-width layout per field: full, half, one-third, one-quarter
- Validation rules (required, regex, min/max length, min/max value)
- Conditional field visibility (`show_if_field` / `show_if_value`)
- Custom help text, placeholders, and CSS classes
- Read-only and pre-filled fields
- Draft saving with auto-save support

### 🔄 Multi-Stage Approval Workflows
Flexible approval engine built on `WorkflowStage` records:
- Each stage has its own approval groups and logic (`any` / `all` / `sequence`)
- Stages execute in order; next stage unlocks when the current one completes
- **Conditional stages** — each stage can carry `trigger_conditions` JSON; stages whose conditions don't match the submission data are automatically skipped
- **Workflow-level trigger conditions** — entire parallel approval tracks are skipped when their workflow `trigger_conditions` don't match (e.g. only trigger a Finance track when `amount > 10000`)
- **Dynamic individual assignees** — set `assignee_form_field` + `assignee_lookup_type` (`email` / `username` / `full_name` / `ldap`) on a stage to resolve the approver from a form field value at runtime; falls back to group tasks when the value cannot be resolved
- **Send Back for Correction** — approvers can return a submission to any prior stage that has `allow_send_back` enabled without terminating the workflow; full audit entry recorded
- Stage-specific form fields (e.g. approver notes, signature date) appear only during that stage
- Configurable approval deadline (`approval_deadline_days`) sets `due_date` on created tasks
- Email notifications and configurable reminder cadence (`daily` / `weekly` / `none`)
- Escalation routing when a form field exceeds a threshold (e.g. amount > $5 000)
- Rejection handling with per-stage or global rejection semantics
- Complete audit trail on every approval, rejection, send-back, and status change

### 🔀 Sub-Workflows
Spawn child workflow instances from a parent submission:
- `SubWorkflowDefinition` links a parent workflow to a child form definition
- `count_field` controls how many sub-workflows to create (driven by a form field value)
- `data_prefix` slices the parent's form data to populate each child
- Triggered `on_approval`, `on_submit`, or `manual`
- `detached` mode lets child instances complete independently of the parent
- Parent submission status reflects aggregate child completion when not detached
- Sub-workflows support the same send-back mechanism via `handle_sub_workflow_send_back`

See [Sub-Workflows Guide](docs/SUB_WORKFLOWS.md) for a full walkthrough.

### 🧮 Calculated / Formula Fields
Auto-compute field values from other field inputs:
- `field_type = "calculated"` with a `formula` template string (e.g. `{first_name} {last_name}`)
- Live client-side evaluation updates the read-only field as the user types
- Authoritative server-side re-evaluation on submit prevents tampering
- Available in both regular form submission and approval step forms

See [Calculated Fields Guide](docs/CALCULATED_FIELDS.md).

### 📊 Spreadsheet Upload Fields
Accept CSV or Excel files as structured form input:
- `field_type = "spreadsheet"` with accept `.csv`, `.xls`, `.xlsx`
- Parsed and stored as `{"headers": [...], "rows": [{...}, ...]}` in `form_data`
- Available during initial submission and approval step forms

### 🔌 Configurable Prefill Sources
Populate form fields automatically from reusable `PrefillSource` records:
- **User model** — `user.email`, `user.first_name`, `user.username`, etc.
- **LDAP / Active Directory** — any LDAP attribute (department, title, manager, custom)
- **External databases** — schema/table/column lookup with template support for multi-column composition
- **Custom database queries** — reference a named query via `database_query_key`
- **System values** — `current_date`, `current_time`

### ⚡ Post-Submission Actions
Automatically run side-effects after a submission event:

| Trigger | Description |
|---------|-------------|
| `on_submit` | Runs immediately on form submission |
| `on_approve` | Runs when the submission is approved |
| `on_reject` | Runs when the submission is rejected |
| `on_complete` | Runs when the entire workflow completes |

**Action types:** `email`, `database`, `ldap`, `api`, `custom`

**Features:**
- Conditional execution with 10 operators (`equals`, `not_equals`, `greater_than`, `less_than`, `contains`, `not_contains`, `is_empty`, `is_not_empty`, `is_true`, `is_false`, plus date comparisons)
- Automatic retries with configurable `max_retries`
- Execution ordering for dependent actions
- Idempotent locking (`is_locked`) to prevent double-execution
- Full execution logging via `ActionExecutionLog`
- Pluggable handler architecture — register custom handlers for new action types

### 🔄 Cross-Instance Form Sync
Move form definitions between environments from the Django Admin:
- **Pull from Remote** — connect to a configured remote instance and import selected forms
- **Push to Remote** — select forms and push to any destination
- **Import / Export JSON** — portable `.json` snapshots
- **Conflict modes** — `update`, `skip`, or `new_slug`
- **`FORMS_SYNC_REMOTES`** setting — pre-configure named instances (URL + token)
- HTTP endpoints protected by Bearer token for CI/scripted use

### 📁 Managed File Uploads
- `FileUploadConfig` per form definition (allowed extensions, max size)
- `ManagedFile` records with approval/rejection/supersede lifecycle
- Version tracking with `is_current` flag

### 🔒 Enterprise-Ready Security
- LDAP/Active Directory authentication with auto-sync of profile attributes
- SSO integration (SAML, OAuth) with attribute mapping to `UserProfile`
- Role-based access — four permission tiers on `FormDefinition`:
  - `submit_groups` — can see and submit the form
  - `view_groups` — prerequisite gate for form access
  - `reviewer_groups` — read-only view of all submissions and approval history
  - `admin_groups` — full administrative view of all submissions
- Group-based approval routing via `WorkflowStage.approval_groups`
- Complete audit logging (`AuditLog` — who, what, when, IP address)
- `UserProfile` auto-created on first login with LDAP/SSO sync

## Quick Start

### Installation

```bash
pip install django-forms-workflows
```

### Setup

1. Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'crispy_forms',
    'crispy_bootstrap5',
    'django_forms_workflows',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
```

2. Include URLs and run migrations:

```python
# urls.py
urlpatterns = [
    path('forms/', include('django_forms_workflows.urls')),
]
```

```bash
python manage.py migrate django_forms_workflows
```

3. Create your first form in Django Admin!

### Optional Settings

```python
FORMS_WORKFLOWS = {
    # Branding — replaces "Django Forms Workflows" across all templates
    "SITE_NAME": "Acme Corp Workflows",

    # LDAP attribute sync on every login
    "LDAP_SYNC": {
        "enabled": True,
        "attributes": {
            "department": "department",
            "title": "title",
            "employee_id": "extensionAttribute1",
        },
    },
}

# Cross-instance form sync
FORMS_SYNC_API_TOKEN = "shared-secret"
FORMS_SYNC_REMOTES = {
    "production": {
        "url": "https://prod.example.com/forms-sync/",
        "token": "prod-token",
    },
}

# Context processor — injects site_name into every template
TEMPLATES = [
    {
        "OPTIONS": {
            "context_processors": [
                # ... standard processors ...
                "django_forms_workflows.context_processors.forms_workflows",
            ]
        }
    }
]
```
```

## Architecture

```mermaid
graph TB
    subgraph UI["User Interface"]
        FB["Form Builder<br/>(Admin)"]
        FV["Form Viewer<br/>(End User)"]
        AU["Approval UI<br/>(Approvers)"]
    end

    subgraph Core["Django Forms Workflows"]
        FD["FormDefinition<br/>+ FormField"]
        WF["WorkflowDefinition<br/>+ WorkflowStage"]
        PS["PrefillSource"]
        PA["PostSubmissionAction<br/>+ Executor"]
        SYNC["Sync API<br/>(Push/Pull)"]
    end

    subgraph External["External Systems"]
        AD["LDAP / AD"]
        DB["External<br/>Databases"]
        API["REST APIs"]
        SSO["SSO<br/>(SAML/OAuth)"]
    end

    FB --> FD
    FV --> FD
    AU --> WF
    FD --> PS
    FD --> PA
    FD --> SYNC
    PS --> AD
    PS --> DB
    PA --> DB
    PA --> AD
    PA --> API
    SSO --> Core
```

## Use Cases

- **HR** — Onboarding, time-off requests, expense reports, status changes
- **IT** — Access requests, equipment requests, change management
- **Finance** — Purchase orders, invoice approvals, budget requests
- **Education** — Student applications, course registrations, facility booking
- **Healthcare** — Patient intake, referrals, insurance claims
- **Government** — Permit applications, FOIA requests, citizen services

## Comparison

| Feature | Django Forms Workflows | Crispy Forms | FormStack | Django-Formtools |
|---------|----------------------|--------------|-----------|------------------|
| Database-driven forms | ✅ | ❌ | ✅ | ❌ |
| No-code form creation | ✅ | ❌ | ✅ | ❌ |
| Self-hosted | ✅ | ✅ | ❌ | ✅ |
| Multi-stage approval workflows | ✅ | ❌ | ⚠️ | ❌ |
| Sub-workflows | ✅ | ❌ | ❌ | ❌ |
| Post-submission actions | ✅ | ❌ | ⚠️ | ❌ |
| External data prefill | ✅ | ❌ | ⚠️ | ❌ |
| REST API (Bearer token) | ✅ | ❌ | ✅ | ❌ |
| Bulk export (Excel / CSV) | ✅ | ❌ | ✅ | ❌ |
| Cross-instance sync | ✅ | ❌ | ❌ | ❌ |
| LDAP/AD + SSO integration | ✅ | ❌ | ❌ | ❌ |
| Managed file uploads | ✅ | ❌ | ✅ | ❌ |
| Audit trail | ✅ | ❌ | ✅ | ❌ |
| Open source | ✅ | ✅ | ❌ | ✅ |

## Requirements

- Python 3.10+
- Django 5.2+
- PostgreSQL, MySQL, or SQLite (PostgreSQL recommended for production)
- Optional: Celery 5.0+ with Redis/Valkey for background task processing
- Optional: `openpyxl` for Excel spreadsheet field support (`pip install django-forms-workflows[excel]`)
- Optional: `django-auth-ldap` for LDAP/AD integration (`pip install django-forms-workflows[ldap]`)
- Optional: WeasyPrint for PDF export (`pip install django-forms-workflows[pdf]`)

## Testing

```bash
cd django-forms-workflows
pip install pytest pytest-django
python -m pytest tests/ -v
```

The test suite covers models, forms, workflow engine (including dynamic assignees, conditional stages, multi-workflow parallel tracks, sub-workflows), sync API, post-submission action executor, views, signals, conditions, and utilities — **298 tests**.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

GNU Lesser General Public License v3.0 (LGPLv3) — see [LICENSE](LICENSE) for details.

## Support

- 📖 [Documentation](https://django-forms-workflows.readthedocs.io/)
- 💬 [Discussions](https://github.com/opensensor/django-forms-workflows/discussions)
- 🐛 [Issue Tracker](https://github.com/opensensor/django-forms-workflows/issues)

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full prioritized roadmap with rationale and implementation notes.

### ✅ Delivered (through v0.37)
- [x] Database-driven form definitions with 25+ field types
- [x] Dynamic form rendering with Crispy Forms + Bootstrap 5
- [x] Multi-stage approval workflows (any/all/sequence logic per stage)
- [x] Conditional workflow & stage trigger logic
- [x] Dynamic individual assignee resolution (email / username / full name / LDAP)
- [x] Send Back for Correction (return to any prior stage without terminating)
- [x] Sub-workflow support (spawn N child instances from a parent)
- [x] Calculated / formula fields with live client-side evaluation
- [x] Spreadsheet upload fields (CSV, XLS, XLSX)
- [x] LDAP/AD integration with profile sync
- [x] SSO attribute mapping (SAML/OAuth)
- [x] Configurable prefill sources (user, LDAP, database, API, system values)
- [x] Post-submission actions with conditional execution, ordering & retries
- [x] Cross-instance form sync (push/pull/JSON import-export)
- [x] Managed file uploads with approval lifecycle and S3/Spaces presigned URLs
- [x] Conditional field visibility (client-side JS, no page reload)
- [x] Form templates and cloning
- [x] Nested category hierarchy with group-based access control
- [x] WeasyPrint PDF export with multi-column layout
- [x] Column-picker approval inbox with DataTables
- [x] Complete audit logging (who, what, when, IP)
- [x] Configurable site branding via `FORMS_WORKFLOWS['SITE_NAME']`
- [x] Comprehensive test suite (298 tests)
- [x] REST API — Bearer-token authenticated endpoints: list forms, fetch field schema, submit (JSON or multipart, including `?draft=1`), poll submission status; OpenAPI 3.0 schema + Swagger UI
- [x] Bulk export — Excel and CSV export of submission data from the approval inbox (`allow_bulk_export` / `allow_bulk_pdf_export` per workflow)
- [x] Four-tier RBAC — `submit_groups`, `view_groups`, `reviewer_groups` (read-only submission history), `admin_groups` (full submission view) with consistent enforcement across all list and detail views
- [x] Auto-save with configurable interval; Save Draft bypasses required-field validation without storing browser internals (CSRF token, button names)

### 🚧 Near-term (next 1–3 releases)
- [ ] Webhook delivery on workflow events (submit / approve / reject)
- [ ] Dashboard analytics (submission counts, approval times, bottleneck stages)

### 📋 Planned (medium-term)
- [x] Signature field type (drawn or typed) — ✅ Shipped in v0.45.0
- [ ] Form versioning — immutable snapshots with diff viewer
- [ ] Advanced reporting (submission analytics, bottleneck analysis, custom report builder)
- [ ] Multi-tenancy support (organisation-scoped form libraries)
- [ ] Plugin / custom handler marketplace

## Credits

Built with ❤️ by the Django community.

Special thanks to:
- [Django Crispy Forms](https://github.com/django-crispy-forms/django-crispy-forms)
- [Celery](https://github.com/celery/celery)
- [django-auth-ldap](https://github.com/django-auth-ldap/django-auth-ldap)
