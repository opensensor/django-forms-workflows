# Sub-Workflows Guide

Sub-workflows let a parent submission spawn **N repeated child approval flows**. They are ideal when one submission needs several follow-up approvals such as payment installments, equipment line items, or reviewer-by-reviewer sign-off.

## What a sub-workflow does

A `SubWorkflowDefinition` links a parent `WorkflowDefinition` to another workflow template and tells the engine:

- **which** child workflow to use
- **how many** instances to create (`count_field`)
- **when** to spawn them (`on_submission` or `on_approval`)
- **how** to label them in the UI (`section_label`, `label_template`)
- **whether** child completion affects the parent (`detached`, `reject_parent`)

Each spawned `SubWorkflowInstance` gets its own approval tasks and status.

## Key fields

| Field | Meaning |
|---|---|
| `sub_workflow` | The child workflow template to run for each instance |
| `count_field` | Parent form field whose integer value decides how many child instances to create |
| `trigger` | `on_submission` or `on_approval` |
| `section_label` | Heading shown in the parent submission detail/history UI |
| `label_template` | Per-instance label such as `Payment {index}` |
| `data_prefix` | Optional field prefix used to slice parent form data per instance |
| `detached` | If true, child workflows do not hold the parent open |
| `reject_parent` | If true, one rejected child rejects the parent and cancels siblings |

## Recommended setup

1. Create the **parent form** and its workflow.
2. Create the **child form** and configure its workflow stages just like any other approval flow.
3. Add a numeric field on the parent form that will drive `count_field`.
4. Create a `SubWorkflowDefinition` linking the parent workflow to the child workflow.
5. Choose whether child instances should spawn on submission or only after parent approval.

## Trigger behavior

| Trigger | When child instances are created |
|---|---|
| `on_submission` | Immediately after the parent submission enters the engine |
| `on_approval` | After the parent workflow reaches final approval |

## Parent/child completion behavior

| Setting | Result |
|---|---|
| `detached = True` | Child instances run independently; the parent does not wait for them |
| `detached = False` | The parent remains `pending_approval` until child instances finish |
| `reject_parent = False` | A rejected child is treated as complete work; the parent can still finish once all children are done |
| `reject_parent = True` | A rejected child immediately rejects the parent and cancels sibling child instances |

## Data slicing with `data_prefix`

Use `data_prefix` when the parent stores repeated field sets such as:

- `payment_type_1`, `payment_amount_1`
- `payment_type_2`, `payment_amount_2`

With `data_prefix = payment`, child instance 1 can work from the `_1` fields while child instance 2 works from the `_2` fields.

## Approval behavior inside child workflows

Child workflows use the same engine features as parent workflows:

- staged approvals with `all` / `any` / `sequence`
- dynamic assignees
- manager approval
- send-back to prior stages
- workflow deadlines and reminders

That means you can model a parent approval that explodes into many smaller approval chains without losing any stage behavior.

## UI behavior

- Each child instance is shown using `label_template` (for example `Payment 1`, `Payment 2`)
- The parent submission detail page groups child instances under `section_label`
- Child approval tasks appear in the same approval inbox flow as other tasks
- Send-back in a child workflow uses the same correction flow as a parent workflow

## Current constraints

- The parent workflow and child workflow must already exist before the sub-workflow config is saved.
- `count_field` must resolve to an integer-like value at runtime.
- One `SubWorkflowDefinition` attaches to one parent `WorkflowDefinition`.

## Related guides

- [Workflows Guide](WORKFLOWS.md)
- [Send Back for Correction](SEND_BACK.md)
- [Dynamic Assignees](DYNAMIC_ASSIGNEES.md)
- [Notifications](NOTIFICATIONS.md)