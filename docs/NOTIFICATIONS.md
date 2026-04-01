# Notification System

The notification system in `django-forms-workflows` provides flexible, event-driven email notifications throughout the lifecycle of a form submission. All notification configuration lives in a single model — `NotificationRule` — giving administrators a unified interface for controlling who receives which emails, when, and under what conditions.

## Architecture Overview

```
Form Submission Lifecycle
─────────────────────────
  Submitted ──► Stage 1 activates ──► Stage 1 completes ──► Stage 2 ──► Final Decision
     │              │                      │                    │            │
     ▼              ▼                      ▼                    ▼            ▼
 submission    approval_request      stage_decision      approval_request  workflow_approved
 _received                                                                workflow_denied
                                                                          form_withdrawn
```

All notifications are dispatched as **Celery tasks** (asynchronous when a broker is available, synchronous fallback otherwise) and are configured through a single model:

| Model | Description |
|-------|-------------|
| `NotificationRule` | One rule = one event + one set of recipient sources + optional conditions. Attach to a workflow, optionally scoped to a specific stage. |

## The `NotificationRule` Model

Each rule answers three questions:

1. **When?** — The `event` field selects which lifecycle event triggers the notification.
2. **Who?** — Six additive recipient sources determine who receives the email.
3. **Under what conditions?** — Optional `conditions` JSON evaluated against `form_data`.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow` | ForeignKey | The parent WorkflowDefinition (required) |
| `stage` | ForeignKey | Optional. Scopes recipient sources to a specific stage |
| `event` | Choice | Which lifecycle event triggers this rule |
| `conditions` | JSON | Optional conditions evaluated against `form_data` |
| `subject_template` | CharField | Custom subject line (supports `{form_name}`, `{submission_id}`, and any `{field_name}` token — see [Answer Piping](#answer-piping-in-subjects)) |
| `notify_submitter` | Boolean | Include the form submitter |
| `email_field` | CharField | Form field slug whose value is an email address |
| `static_emails` | CharField | Comma-separated fixed email addresses |
| `notify_stage_assignees` | Boolean | Include dynamically-assigned approvers |
| `notify_stage_groups` | Boolean | Include all users in stage approval groups |
| `notify_groups` | M2M → Group | Additional groups to notify (independent of stages) |

### Scope: Workflow-Level vs. Stage-Level

The `stage` field controls the scope of stage-aware recipient sources:

| `stage` value | `notify_stage_assignees` behavior | `notify_stage_groups` behavior |
|---------------|----------------------------------|-------------------------------|
| **null** (workflow-level) | Includes assignees from **all** stages | Includes users from **all** stages' groups |
| **set** (stage-level) | Includes only **that stage's** assignee | Includes only **that stage's** groups |

This gives you both "notify everyone" and "notify selectively" without separate models.

## Notification Events

| Event Key | When It Fires | Description |
|-----------|--------------|-------------|
| `submission_received` | Form is first submitted | The initial submission event |
| `approval_request` | A workflow stage activates | A new approval task has been created |
| `stage_decision` | An individual stage completes | All tasks in a stage are resolved |
| `workflow_approved` | Final approval | The entire workflow is approved |
| `workflow_denied` | Final rejection | The submission is rejected |
| `form_withdrawn` | Submitter withdraws | The submitter cancels their submission |

## Email Templates

| Event | Template |
|-------|----------|
| `submission_received` | `emails/submission_notification.html` |
| `approval_request` | `emails/approval_request.html` |
| `stage_decision` | `emails/approval_notification.html` |
| `workflow_approved` | `emails/approval_notification.html` |
| `workflow_denied` | `emails/rejection_notification.html` |
| `form_withdrawn` | `emails/withdrawal_notification.html` |
| Batched digest | `emails/notification_digest.html` |

Templates receive `submission`, `submission_url`, `approval_url`, `hide_approval_history`, and (where applicable) `task` in their context.

## Recipient Resolution

All recipient sources are combined additively and deduplicated. For a given rule:

1. **`notify_submitter`** → `submission.submitter.email`
2. **`email_field`** → The value of `form_data[slug]` (dynamic per submission)
3. **`static_emails`** → Comma-separated fixed addresses
4. **`notify_stage_assignees`** → `ApprovalTask.assigned_to.email` for dynamically-assigned users
5. **`notify_stage_groups`** → All users in the stage's `StageApprovalGroup` → `Group` → `User.email`
6. **`notify_groups`** → All users in the explicitly-listed M2M groups

At least one recipient source must be configured per rule (validated by `clean()`).

---

## Configuration Scenarios

### Scenario 1: Notify the Submitter on Final Decision

> "When approved or rejected, the submitter should get an email."

Create two `NotificationRule` records:
- `event=workflow_approved`, `notify_submitter=True`
- `event=workflow_denied`, `notify_submitter=True`

### Scenario 2: Notify an Advisor from Form Data

> "The form has an 'advisor_email' field. Notify the advisor on submission and final approval."

Create two rules:
- `event=submission_received`, `email_field=advisor_email`
- `event=workflow_approved`, `email_field=advisor_email`

### Scenario 3: Notify a Dynamically-Assigned Approver on Final Decision

> "Stage 1 assigns a reviewer by full name. That reviewer should be notified when the workflow finishes."

Create one stage-scoped rule:
- `event=workflow_approved`, `stage=Stage 1`, `notify_stage_assignees=True`

The reviewer's email comes from the Django `User` record resolved during dynamic assignment. No separate email field needed.

### Scenario 4: CC a Department on All Submissions


### Scenario 5: Conditional Notification to Dean

> "Only notify the dean if the department is 'Graduate Studies' AND the request amount exceeds $5,000."

Create one rule:
- `event=workflow_approved`, `static_emails=dean@example.edu`
- `conditions`:
  ```json
  {
    "operator": "AND",
    "conditions": [
      {"field": "department", "operator": "equals", "value": "Graduate Studies"},
      {"field": "amount", "operator": "gt", "value": "5000"}
    ]
  }
  ```

### Scenario 6: Multi-Stage with Selective Assignee Notifications

> "Three stages: Department Chair, HR Review, VP Approval. Only the Chair and VP should be notified on final decision — not HR."

Create two stage-scoped rules:
- `event=workflow_approved`, `stage=Department Chair`, `notify_stage_assignees=True`
- `event=workflow_approved`, `stage=VP Approval`, `notify_stage_assignees=True`

HR is excluded because there is no rule scoping to the HR stage. Compare this to a single workflow-level rule with `notify_stage_assignees=True` (no stage set), which would include **all** stages' assignees.

### Scenario 7: Notify an Entire Approval Group on Final Decision

> "The Finance Committee group reviews Stage 2. Everyone in that group should be emailed when the workflow is approved."

Create one stage-scoped rule:
- `event=workflow_approved`, `stage=Stage 2`, `notify_stage_groups=True`

All users in Stage 2's approval groups who have an email address will receive the notification.

### Scenario 8: Notify Arbitrary Groups (Not Tied to Any Stage)

> "The 'Executive Team' group should be notified whenever a high-value request is approved, regardless of which stages they're involved in."

Create one rule:
- `event=workflow_approved`, `notify_groups=[Executive Team]`
- `conditions`: `{"field": "amount", "operator": "gt", "value": "50000"}`

### Scenario 9: Stage Decision Notifications

> "When Stage 1 (Manager Review) completes, notify the submitter so they know their form is progressing."

Create one rule:
- `event=stage_decision`, `stage=Manager Review`, `notify_submitter=True`

### Scenario 10: Batched Daily Digest

> "Instead of individual emails, send the registrar a daily summary."

1. On the `WorkflowDefinition`: set `notification_cadence=daily`, `notification_cadence_time=08:00`
2. Create a rule: `event=submission_received`, `static_emails=registrar@example.edu`

All submissions are batched into a single digest email sent at 8:00 AM.

---

## Notification Batching

Workflows can opt into **digest-style batching** via `WorkflowDefinition.notification_cadence`:

| Cadence | Behavior |
|---------|----------|
| `immediate` | Each notification fires as a separate email right away (default) |
| `daily` | Queued and sent as a single digest once per day |
| `weekly` | Queued and sent once per week |
| `monthly` | Queued and sent once per month |
| `form_field_date` | Queued and sent on the date specified in a form field |

Additional settings: `notification_cadence_day`, `notification_cadence_time`, `notification_cadence_form_field`.

Queued notifications are stored in `PendingNotification` and dispatched by the `send_batched_notifications` periodic task.

---

## Privacy: Hiding Approval History

The `hide_approval_history` flag on `WorkflowDefinition` controls whether notification emails include the full approval history (approver names and comments). When enabled, the submitter only sees the final decision.

---

## Email Backend Configuration

| Backend | Setting | Use Case |
|---------|---------|----------|
| Console | `django.core.mail.backends.console.EmailBackend` | Development |
| SMTP | `django.core.mail.backends.smtp.EmailBackend` | Traditional SMTP relay |
| Gmail API | `django_forms_workflows.email_backends.GmailAPIBackend` | Google Workspace |

For Gmail API, also set `DEFAULT_FROM_EMAIL`, `GMAIL_DELEGATED_USER`, and `GMAIL_SERVICE_ACCOUNT_KEY_BASE64`.

---

## Troubleshooting

### No emails sent
- Check `EMAIL_BACKEND` is not console in production
- Check Celery is running (falls back to sync but verify)
- Check that at least one recipient resolves (no recipients = silently skipped)

### Dynamic assignee not receiving emails
- Check `notify_stage_assignees=True` on the relevant rule
- Check the stage has `assignee_form_field` configured
- Check the resolved `User` has a populated `email` field

### Group members not receiving emails
- Check `notify_stage_groups=True` or `notify_groups` is set
- Check users in the group have non-empty `email` fields

### Conditional notification not firing
- Check field names in conditions match form field slugs exactly
- Valid operators: `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`, `contains`, `in`

### Batched notifications not sending
- Check `send_batched_notifications` is in the Celery beat schedule
- Check `PendingNotification` records are being created

---

## Answer Piping in Subjects

`subject_template` supports **answer piping** — you can embed submitted form field values directly into the email subject line using `{field_name}` tokens.

### Syntax

```
{field_name}
```

`field_name` must match the **field slug** on `FormField` exactly (case-sensitive).

### Available tokens

| Token | Source |
|-------|--------|
| `{form_name}` | The form's display name |
| `{submission_id}` | The numeric ID of the submission |
| `{<any field slug>}` | The submitted value for that field |

### Behaviour

| Scenario | Result |
|----------|--------|
| Known field, scalar value | Replaced with the submitted value |
| Known field, list value (e.g. checkboxes) | Values joined with `", "` |
| Unknown field slug | Replaced with `""` (empty string, fail-open) |

### Examples

```
# Simple field piping
Subject: {form_name} — New request from {full_name}

# Multiple fields
Subject: #{submission_id}: {department} request approved — {position_title}

# List field
Subject: Courses selected: {course_selections}
```

### `form_data` in template context

In addition to subject piping, the full `form_data` dictionary is now passed to every notification email template as `form_data`. This allows HTML templates to reference field values directly:

```html
<!-- emails/approval_request.html -->
<p>Request from: <strong>{{ form_data.full_name }}</strong></p>
<p>Department: {{ form_data.department }}</p>
<p>Amount requested: ${{ form_data.amount }}</p>
```

---

## Migration from Legacy Models

`NotificationRule` replaces three older mechanisms:

| Legacy | Migrated To |
|--------|------------|
| `WorkflowNotification` | `NotificationRule` (stage=null) |
| `StageFormFieldNotification` | `NotificationRule` (stage=set) |
| `WorkflowStage.notify_assignee_on_final_decision` | `NotificationRule` with `notify_stage_assignees=True` |

Data migration `0075_migrate_to_notification_rules` automatically converts all existing records. The legacy models are retained for backward compatibility but will be removed in a future release.

