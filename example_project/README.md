# Django Form Workflows - Farm Workflows Showcase

This example project is a comprehensive farm-themed demo for `django-forms-workflows`.

Instead of starting from a blank admin, it can seed a realistic showcase with:

- multi-step forms
- public/anonymous intake
- notifications and webhook configuration
- dynamic assignees, send-back, reassign, and editable approvals
- sequential + parallel workflow stages
- sub-workflows
- prefill sources and post-submission actions
- API-enabled forms and API token auth
- batch import and spreadsheet fields
- analytics-friendly demo submissions

## Quick start

1. **Install dependencies**

   ```bash
   pip install -e ..
   ```

2. **Run migrations**

   ```bash
   python manage.py migrate
   ```

3. **Seed the full demo**

   ```bash
   python manage.py seed_farm_demo
   ```

4. **Run the development server**

   ```bash
   python manage.py runserver
   ```

5. **Open the demo**

   - Home: http://localhost:8000/
   - Forms: http://localhost:8000/forms/
   - Approval inbox: http://localhost:8000/forms/approvals/
   - Analytics: http://localhost:8000/forms/analytics/
   - API docs: http://localhost:8000/api/docs/
   - Admin: http://localhost:8000/admin/

## Seeded demo accounts

All demo accounts use password `farm123`.

- `farmer_brown` — superuser / admin
- `farmer_jane` — normal submitter
- `mechanic_mike` — equipment operator approver
- `finance_faith` — finance approver
- `safety_sam` — safety approver
- `owner_olive` — executive/final approver
- `irrigation_ivan` — irrigation specialist
- `integration_ivy` — integration/API token user

The seed command also creates a `Farm Demo API Token` and prints it in the command output.

## Demo forms included

### 1. Equipment Repair Request

Shows:

- dynamic assignee by email
- send-back to prior stage
- reassign + editable approval data
- approval-step fields
- multifile uploads
- notification rules
- webhook endpoint configuration

### 2. Capital Purchase Request

Shows:

- multi-step layout
- conditional fields
- calculated fields
- API-enabled form access
- parallel approvals
- conditional executive approval stage
- bulk export / bulk PDF export
- approval-step fields
- notification rules + webhook endpoint

### 3. Irrigation Expansion Request

Shows:

- sequential approval logic
- detached sub-workflows
- child `Irrigation Zone Checklist` workflow generation

### 4. Safety Incident Report

Shows:

- public/anonymous form submission
- signature field
- conditional logic
- multifile evidence upload
- PDF generation anytime

### 5. Farmer Contact Update

Shows:

- prefill sources
- database post-submission action
- API post-submission action configuration

### 6. Harvest Batch Log

Shows:

- batch import
- Excel template generation

### 7. Sensor Data Upload

Shows:

- spreadsheet file field

## Recommended tour

1. Visit the home page and open a few showcase forms.
2. Sign in as `farmer_jane` and submit forms.
3. Sign in as `finance_faith`, `mechanic_mike`, or `owner_olive` to process approvals.
4. Explore `/forms/analytics/` to see seeded historical submissions.
5. Inspect Admin for:
   - Form Builder
   - Workflow Builder
   - Notification Rules
   - Webhook Endpoints
   - Webhook Delivery Logs
   - Post-Submission Actions
   - API Tokens

## Helpful docs

- [Quickstart](../docs/QUICKSTART.md)
- [Workflows](../docs/WORKFLOWS.md)
- [Notifications](../docs/NOTIFICATIONS.md)
- [Workflow Webhooks](../docs/WEBHOOKS.md)
- [Post-Submission Actions](../docs/POST_SUBMISSION_ACTIONS.md)
- [Visual Workflow Builder](../docs/VISUAL_WORKFLOW_BUILDER.md)