# Send Back for Correction

**Send Back for Correction** gives approvers a third decision path — alongside *Approve* and *Reject* — that returns a submission to any prior stage for revision without permanently terminating the workflow.

## Why Use It?

| Scenario | Without Send Back | With Send Back |
|---|---|---|
| Finance spot-checks a form and finds a typo | Must reject; submitter resubmits from scratch | Sends back to the submitter or an earlier stage; history is preserved |
| Stage 3 needs information that was supposed to be collected at Stage 1 | Workflow dead-ends | Stage 3 approver sends back to Stage 1 |
| Approval chain needs an extra sign-off before proceeding | No mechanism | Send to a prior stage; that stage re-approves and advances again |

---

## Model Changes (v0.32)

| Model | Field | Description |
|---|---|---|
| `WorkflowStage` | `allow_send_back` (`BooleanField`, default `False`) | Opts a stage in as a valid send-back target |
| `ApprovalTask` | `status = "returned"` | New terminal status — records the closed task without firing rejection hooks |
| `AuditLog` | `action = "send_back"` | Records who sent back, from which stage, to which target stage, and the reason |

---

## Admin Setup

### 1. Enable Send-Back on Eligible Stages

For each stage you want approvers to be able to send submissions *back to*:

1. Open **Django Admin → Workflow Definitions → [your workflow] → Workflow Stages**.
2. Select a stage (must have `order` lower than the stage where the approver acts).
3. Check **Allow Send Back**.
4. Save.

> Only stages with `allow_send_back=True` **and** a lower `order` than the current stage appear as target options in the approval UI.

### 2. No Additional Configuration Required

The approval view automatically renders the **Send Back for Correction** card when at least one prior stage has `allow_send_back=True`.

---

## Approver User Flow

1. Approver opens the approval screen for a pending submission.
2. A collapsible **Send Back for Correction** card (Bootstrap warning / amber colour) appears below the main decision buttons.
3. Approver expands the card, selects the target stage from a dropdown, and types a reason.
4. Approver clicks **Send Back**.
5. The system:
   - Cancels all sibling pending tasks at the current stage (sets `status = "returned"`).
   - Writes an `AuditLog` entry with `action = "send_back"`, target stage name, and the reason text.
   - Re-creates tasks at the selected target stage via `_create_stage_tasks`.
   - Leaves `FormSubmission.status = "pending_approval"` — the workflow continues.
6. The assignees at the target stage receive a new task notification email.

---

## Engine Functions

| Function | Description |
|---|---|
| `handle_send_back(submission, task, target_stage)` | Main handler for parent workflow send-backs |
| `handle_sub_workflow_send_back(task, target_stage)` | Same logic scoped to a `SubWorkflowInstance` |

Both functions are called from the `approve_submission` view when `decision=send_back` is posted.

---

## Constraints & Validation

The view enforces these constraints before calling `handle_send_back`:

- `target_stage` must belong to the **same `WorkflowDefinition`** as the current task.
- `target_stage.order` must be **strictly less than** the current stage order.
- `target_stage.allow_send_back` must be `True`.
- A non-empty **reason** string is required.

Any violation results in a validation error and no state change.

---

## Audit Trail

Every send-back produces an `AuditLog` record:

```
action:      send_back
submission:  <FormSubmission pk>
user:        <approver who triggered send-back>
detail:      "Sent back from 'Finance Review' to 'Department Head Review': Missing cost centre code"
ip_address:  <request IP>
```

---

## Interaction with Sub-Workflows

`handle_sub_workflow_send_back` mirrors the parent logic but operates on a `SubWorkflowInstance` rather than the parent `FormSubmission`. The parent submission status is not affected by a sub-workflow send-back.

---

## Related Docs

- [Dynamic Assignees](DYNAMIC_ASSIGNEES.md)
- [Workflow Configuration](CONFIGURATION.md)
- [Sub-Workflows](SUB_WORKFLOWS.md)

