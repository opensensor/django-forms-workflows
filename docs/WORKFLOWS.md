# Workflows Guide

`django-forms-workflows` now supports much more than a single approver list. A form can have **multiple workflow tracks**, each track can have **staged or parallel approvals**, and each stage can carry its own routing, UI, and notification behavior.

## Core building blocks

| Model | Purpose |
|---|---|
| `WorkflowDefinition` | One approval track attached to a form. A form can have more than one. |
| `WorkflowStage` | A stage inside a workflow track. Stages with the same `order` run in parallel. |
| `StageApprovalGroup` | Through model that orders groups when a stage uses `sequence` logic. |
| `ApprovalTask` | The runtime approval task assigned to a user or group. |
| `NotificationRule` | Event-driven email rules for workflow and stage events. |
| `WebhookEndpoint` | Event-driven outbound webhooks for workflow lifecycle events. |

## How the engine runs

1. When a form is submitted, the engine loads **all** `WorkflowDefinition` rows for that form.
2. Workflow tracks whose `trigger_conditions` match the submission start in parallel.
3. Within each workflow track, the engine activates the lowest `order` stage(s).
4. Stages sharing the same `order` value run in parallel.
5. Each stage resolves according to its own `approval_logic`:
   - `all` — every task in the stage must approve
   - `any` — the first approval wins
   - `sequence` — groups are activated one at a time using `StageApprovalGroup.position`
6. When all active workflow tracks complete, the submission is finalized.

## What you can configure today

### Workflow-level features

- `name_label` for a user-facing track name such as “Finance Approval”
- `trigger_conditions` to skip entire workflow tracks unless submission data matches
- `approval_deadline_days` to place a `due_date` on created approval tasks
- `send_reminder_after_days` and `auto_approve_after_days` for deadline handling
- Notification cadence: `immediate`, `daily`, `weekly`, `monthly`, or `form_field_date`
- `hide_approval_history` for privacy-sensitive forms
- `collapse_parallel_stages` for a cleaner approval-history display
- `allow_bulk_export` and `allow_bulk_pdf_export` for submission list actions
- first-class webhook endpoints for `submission.created`, `task.created`, `submission.approved`, `submission.rejected`, and `submission.returned`

### Stage-level features

- Stage logic with `approval_logic = all | any | sequence`
- Parallel stages by giving multiple stages the same `order`
- Group routing through `approval_groups`
- Manager-first routing with `requires_manager_approval`
- Conditional stages with `trigger_conditions`
- Dynamic assignees using `assignee_form_field` + `assignee_lookup_type`
- Optional `validate_assignee_group` enforcement for dynamic assignees
- `allow_send_back` to make a stage a valid correction target
- `allow_reassign` so current reviewers can hand the task to another eligible user
- `allow_edit_form_data` so reviewers can update the original submission while approving
- `approve_label` to rename the Approve button (for example “Complete” or “Sign Off”)

### Approval-step fields

Approval-only form fields are supported too. Tie a `FormField` to a workflow stage via `FormField.workflow_stage` to collect approver-only data such as signatures, notes, dates, or confirmation checkboxes during that stage.

## Conditions format

Workflow and stage conditions use the same JSON structure:

```json
{
  "operator": "AND",
  "conditions": [
    {"field": "department", "operator": "equals", "value": "Finance"},
    {"field": "amount", "operator": "gt", "value": "1000"}
  ]
}
```

Supported operators are `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`, `contains`, and `in`.

## Recommended admin setup flow

1. Create the form and its submit/view/admin groups.
2. Create one or more `WorkflowDefinition` rows for the form.
3. Add `WorkflowStage` rows in execution order.
4. Attach approval groups to each stage.
5. Add optional routing features such as dynamic assignees, send-back, reassign, or editable form data.
6. Add `NotificationRule` rows for submission received, approval request, stage decision, final approval, rejection, or withdrawal.
7. Add `WebhookEndpoint` rows if external systems should receive signed workflow-event callbacks.
8. Add post-submission actions if approvals should update external systems.

## Visual builder vs. admin inline editing

The visual workflow builder is great for the common structure:

- workflow-level timing and notification settings
- stage names, order, logic, manager approval, send-back, and approve labels
- post-submission actions
- sub-workflow configuration

Advanced stage options such as **dynamic assignees**, **reassign**, **editable form data**, and detailed notification rules are still best configured in Django Admin after saving the basic flow.

For a builder-specific capability and limitation matrix, see [Visual Workflow Builder](VISUAL_WORKFLOW_BUILDER.md).

## Common patterns

### One linear approval chain

- Stage 1: Manager Review (`all`)
- Stage 2: Finance Review (`all`)
- Stage 3: VP Sign-Off (`any`)

### Parallel approvals inside one workflow track

Give both “Legal Review” and “Finance Review” `order = 2`. They will open together after stage 1 completes.

### Parallel workflow tracks on the same form

Create two `WorkflowDefinition` rows on the same form, for example:

- “Department Approval”
- “Security Review”

The submission stays `pending_approval` until both tracks complete.

### Route a stage to an individual named in the form

Set:

- `assignee_form_field = manager_email`
- `assignee_lookup_type = email`

If the lookup succeeds, the engine creates one personal task for that user instead of group tasks.

## Related guides

- [Quick Start](QUICKSTART.md)
- [Visual Workflow Builder](VISUAL_WORKFLOW_BUILDER.md)
- [Dynamic Assignees](DYNAMIC_ASSIGNEES.md)
- [Send Back for Correction](SEND_BACK.md)
- [Sub-Workflows](SUB_WORKFLOWS.md)
- [Notifications](NOTIFICATIONS.md)
- [Workflow Webhooks](WEBHOOKS.md)
- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)