# Notification System

The notification system in `django-forms-workflows` provides flexible, event-driven email notifications throughout the lifecycle of a form submission. Notifications can be configured at multiple levels of granularity — from workflow-wide rules to per-stage controls — allowing administrators to precisely target who receives which emails and when.

## Architecture Overview

```
Form Submission Lifecycle
─────────────────────────
  Submitted ──► Stage 1 activates ──► Stage 2 activates ──► Final Decision
     │              │                      │                     │
     ▼              ▼                      ▼                     ▼
 submission    approval_request      approval_request      approval_notification
 _received     (stage-level)         (stage-level)         rejection_notification
                                                           withdrawal_notification
```

Notifications are dispatched as **Celery tasks** (asynchronous when a broker is available, synchronous fallback otherwise). The system supports three independent notification layers that fire in parallel:

| Layer | Model | Scope | Typical Use |
|-------|-------|-------|-------------|
| **Workflow Notifications** | `WorkflowNotification` | Workflow-wide events | Notify submitter, static CC lists, or form-field-based recipients on final decisions |
| **Stage Form-Field Notifications** | `StageFormFieldNotification` | Per-stage events | Notify a dynamic recipient (e.g., advisor email from form data) when a stage activates or on final decision |
| **Stage Assignee Notifications** | `WorkflowStage.notify_assignee_on_final_decision` | Per-stage flag | Automatically include the stage's dynamically-assigned approver in final decision emails |

## Notification Events

| Event Key | When It Fires | Available On |
|-----------|--------------|--------------|
| `submission_received` | Form is first submitted | WorkflowNotification, StageFormFieldNotification |
| `approval_request` | A workflow stage activates (task created) | StageFormFieldNotification |
| `approval_notification` | Submission receives final approval | WorkflowNotification, StageFormFieldNotification |
| `rejection_notification` | Submission is rejected | WorkflowNotification, StageFormFieldNotification |
| `withdrawal_notification` | Submitter withdraws the submission | WorkflowNotification |

## Email Templates

Each event type maps to a dedicated HTML template:

| Event | Template |
|-------|----------|
| `submission_received` | `emails/submission_notification.html` |
| `approval_request` | `emails/approval_request.html` |
| `approval_notification` | `emails/approval_notification.html` |
| `rejection_notification` | `emails/rejection_notification.html` |
| `withdrawal_notification` | `emails/withdrawal_notification.html` |
| Batched digest | `emails/notification_digest.html` |

All templates extend a shared `emails/email_styles.html` for consistent branding. Templates receive the `submission`, `submission_url`, and (where applicable) `approval_url` and `task` in their context.

## Recipient Resolution

Every notification rule resolves recipients through a common function (`_collect_notification_recipients`) that combines multiple sources in order:

1. **Submitter** — If `notify_submitter = True`, the `submission.submitter.email` is included.
2. **Dynamic assignees** — For `approval_notification` and `rejection_notification` events, all stages with `notify_assignee_on_final_decision = True` contribute their resolved approver's email (from `ApprovalTask.assigned_to.email`).
3. **Email field** — A form field slug (e.g., `advisor_email`) whose submitted value is an email address. Resolved from `form_data` at send time, so it varies per submission.
4. **Static emails** — A comma-separated list of fixed addresses (e.g., `registrar@example.edu, dean@example.edu`).

Recipients are deduplicated; no address receives the same notification twice.

---

## Layer 1: Workflow Notifications (`WorkflowNotification`)

Workflow Notifications are attached to a `WorkflowDefinition` and fire on workflow-level events. They are the primary mechanism for notifying the submitter, static CC lists, and form-field-based recipients.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow` | ForeignKey | The parent WorkflowDefinition |
| `notification_type` | Choice | Which event triggers this rule |
| `notify_submitter` | Boolean | Include the form submitter as a recipient |
| `email_field` | CharField | Form field slug containing a recipient email |
| `static_emails` | CharField | Comma-separated fixed email addresses |
| `subject_template` | CharField | Custom subject line (supports `{form_name}`, `{submission_id}` placeholders) |
| `conditions` | JSONField | Optional conditions evaluated against `form_data` |

### Validation

At least one recipient source (`notify_submitter`, `email_field`, or `static_emails`) must be set. The `clean()` method enforces this.

### Admin Configuration

Workflow Notifications appear as an inline on the WorkflowDefinition admin page. Multiple rules can be created per workflow, each targeting different events and recipient groups.

---

## Layer 2: Stage Form-Field Notifications (`StageFormFieldNotification`)

Stage Form-Field Notifications are attached to a `WorkflowStage` and support all four event types including `approval_request` (stage activation). They are ideal for notifying external parties whose email is captured in the form.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `stage` | ForeignKey | The parent WorkflowStage |
| `notification_type` | Choice | Which event triggers this rule |
| `email_field` | CharField | Form field slug containing a recipient email |
| `static_emails` | CharField | Comma-separated fixed email addresses |
| `subject_template` | CharField | Custom subject line (supports `{form_name}`, `{submission_id}`) |
| `conditions` | JSONField | Optional conditions evaluated against `form_data` |

### Key Difference from Workflow Notifications

- Supports `approval_request` event type (fires when the stage activates).
- Does **not** have `notify_submitter` — use a WorkflowNotification rule for that.
- Always fires immediately regardless of the workflow's `notification_cadence` setting.

---

## Layer 3: Stage Assignee Notifications (`notify_assignee_on_final_decision`)

When a workflow stage uses **dynamic assignment** (`assignee_form_field` + `assignee_lookup_type`), the system resolves a form field value (e.g., a full name like "Jane Smith") to a Django `User` and assigns the approval task to that user.

The `notify_assignee_on_final_decision` boolean on `WorkflowStage` controls whether that resolved user is automatically included as a recipient on final approval/rejection notifications.

### How It Works

1. At **stage creation time**, the workflow engine reads the form field value and resolves it to a `User` via the configured lookup type (`email`, `username`, `full_name`, or `ldap`).
2. The resolved `User` is stored as `ApprovalTask.assigned_to`.
3. At **notification time**, if `notify_assignee_on_final_decision = True`, the system queries all approval tasks for the submission where the stage has this flag set, and adds each `assigned_to.email` to the recipient list.

### Prerequisites

- The stage must have `assignee_form_field` configured.
- The resolved `User` must have a populated `email` field.
- For `full_name` lookup: the user must exist in Django with matching `first_name`/`last_name`, or be JIT-provisioned via LDAP fallback.

### Admin Configuration

The flag appears in the WorkflowStage inline (alongside `validate_assignee_group`) and in the standalone WorkflowStage admin under "Dynamic Assignment".

---

## Conditional Notifications

All notification rules support optional **conditions** — a JSON structure evaluated against `form_data` before sending. This uses the same format as `WorkflowStage.trigger_conditions`:

```json
{
  "operator": "AND",
  "conditions": [
    {"field": "department", "operator": "equals", "value": "Graduate Studies"},
    {"field": "amount", "operator": "gt", "value": "5000"}
  ]
}
```


Batching applies to **Workflow Notifications** and **approval request** emails. Stage Form-Field Notifications (`StageFormFieldNotification`) always fire immediately.

Queued notifications are stored in the `PendingNotification` model and dispatched by the `send_batched_notifications` periodic Celery task.

Additional batching controls on `WorkflowDefinition`:

| Field | Description |
|-------|-------------|
| `notification_cadence_day` | Day of week (0=Mon–6=Sun) for weekly, or day of month (1–31) for monthly |
| `notification_cadence_time` | Time of day to send the digest (defaults to 08:00) |
| `notification_cadence_form_field` | For `form_field_date`: the slug of the date field to read |

---

## Privacy: Hiding Approval History

The `hide_approval_history` flag on `WorkflowDefinition` controls whether rejection/approval notification emails include the full approval history (individual approver names and comments). When enabled:

- The submitter only sees the final decision (approved/rejected).
- Approvers and admins can still see the full history in the admin.
- The `hide_approval_history` context variable is passed to all notification templates.

---

## Configuration Scenarios

### Scenario 1: Simple — Notify the Submitter on Approval/Rejection

> "When a form is approved or rejected, the person who submitted it should get an email."

**Configuration:**
1. Create a `WorkflowNotification` with:
   - `notification_type` = `approval_notification`
   - `notify_submitter` = ✅
2. Create another `WorkflowNotification` with:
   - `notification_type` = `rejection_notification`
   - `notify_submitter` = ✅

No `email_field` or `static_emails` needed.

---

### Scenario 2: Notify an Advisor from Form Data

> "The form has an 'Advisor Email' field. When submitted, the advisor should get a notification. When approved, the advisor should also be told."

**Configuration:**
1. On Stage 1, create a `StageFormFieldNotification`:
   - `notification_type` = `submission_received`
   - `email_field` = `advisor_email`
2. On Stage 1, create another `StageFormFieldNotification`:
   - `notification_type` = `approval_notification`
   - `email_field` = `advisor_email`

The email address is read from the form's submitted data each time.

---

### Scenario 3: Notify the Dynamically-Assigned Approver on Final Decision

> "Stage 1 assigns a reviewer by full name (e.g., 'Jane Smith' selected from a dropdown). That reviewer should be notified when the workflow reaches its final decision."

**Configuration:**
1. On `WorkflowStage` (Stage 1):
   - `assignee_form_field` = `reviewer_name`
   - `assignee_lookup_type` = `full_name`
   - `notify_assignee_on_final_decision` = ✅
2. Create a `WorkflowNotification` with:
   - `notification_type` = `approval_notification`
   - `notify_submitter` = ✅ (optional — if the submitter should also be notified)

The reviewer's email is resolved from the Django `User` record that matched the full name lookup. No separate email field is needed on the form.

---

### Scenario 4: CC a Department on All Submissions

> "Every time this form is submitted, the registrar's office should get a copy."

**Configuration:**
1. Create a `WorkflowNotification` with:
   - `notification_type` = `submission_received`
   - `static_emails` = `registrar@example.edu`

---

### Scenario 5: Conditional Notification to Dean

> "Only notify the dean if the department is 'Graduate Studies' AND the request amount exceeds $5,000."

**Configuration:**
1. Create a `WorkflowNotification` with:
   - `notification_type` = `approval_notification`
   - `static_emails` = `dean@example.edu`
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

The dean only receives the email if both conditions are met.

---

### Scenario 6: Multi-Stage with Selective Assignee Notifications

> "A three-stage workflow: Stage 1 (Department Chair), Stage 2 (HR Review), Stage 3 (VP Approval). Only the Department Chair and VP should be notified on final decision — not HR."

**Configuration:**
1. Stage 1 (`Department Chair`):
   - `assignee_form_field` = `department_chair`
   - `assignee_lookup_type` = `full_name`
   - `notify_assignee_on_final_decision` = ✅
2. Stage 2 (`HR Review`):
   - Assign via approval groups (no dynamic assignee)
   - `notify_assignee_on_final_decision` = ❌ (or leave default `False`)
3. Stage 3 (`VP Approval`):
   - `assignee_form_field` = `vp_name`
   - `assignee_lookup_type` = `full_name`
   - `notify_assignee_on_final_decision` = ✅
4. Create a `WorkflowNotification`:
   - `notification_type` = `approval_notification`
   - `notify_submitter` = ✅

Result: On final approval, the submitter, Department Chair, and VP all receive emails. HR does not.

---

### Scenario 7: Batched Daily Digest

> "Instead of sending an email for every submission, send the registrar a daily summary."

**Configuration:**
1. On the `WorkflowDefinition`:
   - `notification_cadence` = `daily`
   - `notification_cadence_time` = `08:00`
2. Create a `WorkflowNotification`:
   - `notification_type` = `submission_received`
   - `static_emails` = `registrar@example.edu`

All submissions throughout the day are batched into a single digest email sent at 8:00 AM.

---

### Scenario 8: Custom Subject Line

> "Approval emails should say 'Your Leave Request Has Been Approved' instead of the default."

**Configuration:**
1. On the `WorkflowNotification`:
   - `subject_template` = `Your Leave Request Has Been Approved (ID {submission_id})`

Placeholders `{form_name}` and `{submission_id}` are available.

---

## Email Backend Configuration

The system supports multiple email backends:

| Backend | Setting | Use Case |
|---------|---------|----------|
| Console | `django.core.mail.backends.console.EmailBackend` | Development/testing — prints to stdout |
| SMTP | `django.core.mail.backends.smtp.EmailBackend` | Traditional SMTP relay |
| Gmail API | `django_forms_workflows.email_backends.GmailAPIBackend` | Google Workspace with service account |

Configure via the `EMAIL_BACKEND` environment variable. For Gmail API, also set:
- `DEFAULT_FROM_EMAIL` — sender address (e.g., `donotreply@example.edu`)
- `GMAIL_DELEGATED_USER` — the user to impersonate
- `GMAIL_SERVICE_ACCOUNT_KEY_BASE64` — base64-encoded service account JSON key

---

## Troubleshooting

### No emails are being sent

1. **Check `EMAIL_BACKEND`** — ensure it's not set to `console` in production.
2. **Check Celery** — notifications are dispatched as Celery tasks. If Celery is not running, the system falls back to synchronous dispatch, but verify `CELERY_TASK_ALWAYS_EAGER` is set appropriately.
3. **Check recipient resolution** — if no recipients resolve (empty `email_field` value, no `static_emails`, `notify_submitter` is `False`), the notification is silently skipped. Check logs for "no recipients resolved" messages.

### Dynamic assignee not receiving final decision emails

1. **Check `notify_assignee_on_final_decision`** — must be `True` on the relevant stage.
2. **Check `assignee_form_field`** — the stage must use dynamic assignment.
3. **Check User.email** — the resolved Django User must have a populated email field.
4. **Check lookup resolution** — if using `full_name`, the user must exist with matching `first_name`/`last_name`, or LDAP fallback must be configured.

### Conditional notification not firing

1. **Check the conditions JSON** — ensure field names match form field slugs exactly.
2. **Check operator syntax** — valid operators: `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`, `contains`, `in`.
3. **Check logs** — condition evaluation errors are logged as warnings.

### Batched notifications not sending

1. **Check `send_batched_notifications` periodic task** — must be in the Celery beat schedule.
2. **Check `PendingNotification` records** — query the table to see if notifications are being queued.
3. **Check cadence settings** — `notification_cadence_day` and `notification_cadence_time` must be set correctly for weekly/monthly.

## Notification Batching

Workflows can opt into **digest-style batching** instead of immediate delivery via the `notification_cadence` field on `WorkflowDefinition`:

| Cadence | Behavior |
|---------|----------|
| `immediate` | Each notification fires as a separate email right away (default) |
| `daily` | Notifications are queued and sent as a single digest email once per day |
| `weekly` | Queued and sent once per week on the configured day |
| `monthly` | Queued and sent once per month on the configured day |
| `form_field_date` | Queued and sent on the date specified in a form field |

