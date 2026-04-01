# Visual Workflow Builder

The visual workflow builder is useful, but it does **not** yet expose every workflow feature the engine supports. This guide is meant to be honest about what works well today, what still lives in Django Admin, and where the sharp edges are.

## Best use of the builder today

Use the builder for the **first-pass shape** of a workflow:

- stage order and parallel stages
- stage approval logic (`all`, `any`, `sequence`)
- manager approval, send-back, reassign, reviewer edits
- dynamic assignee basics
- workflow deadlines and digest cadence
- post-submission actions
- email actions
- sub-workflow configuration

Then open the related `WorkflowDefinition` / `WorkflowStage` records in Django Admin for anything more advanced.

## What the builder currently supports

### Approval stages

- add/remove stages
- set stage `order`
- run parallel stages by reusing the same order number
- assign approval groups
- choose `all`, `any`, or `sequence`
- enable manager approval
- enable send-back targets
- enable reassignment
- allow reviewer edits to submission data
- set custom approve button labels
- configure dynamic assignees from a form field

### Workflow-level settings

- approval deadline
- reminder delay
- auto-approve delay
- notification cadence: `immediate`, `daily`, `weekly`, `monthly`, `form_field_date`

### Actions

- database / LDAP / API / custom post-submission actions
- email actions with static recipients, recipient fields, CC, subject/body template text, and template path

### Sub-workflows

- target workflow
- count field
- trigger timing
- label template / section label
- detached / reject-parent behavior

## What still requires Django Admin

- multiple `WorkflowDefinition` tracks on the same form
- workflow-level `trigger_conditions`
- stage-level `trigger_conditions`
- detailed notification recipients and event rules (`NotificationRule`)
- stage approval-group ordering via `StageApprovalGroup`
- approval-only form fields tied to a stage
- any workflow feature not shown directly in the builder properties panel

## Important limitations

### 1. Multi-track workflows

If a form has more than one workflow track, the builder currently edits only the **first** one. Use Django Admin for multi-track workflows.

### 2. Legacy node types

Older builder experiments included nodes like conditional branching or extra form steps. Those are **not** the authoritative way to model workflow conditions today. Use `trigger_conditions` on workflows/stages in Django Admin instead.

### 3. Builder is a convenience layer, not the full schema editor

The engine supports more than the canvas currently expresses. When in doubt, treat the builder as the fast visual editor and Django Admin as the complete editor.

## Recommended workflow for admins

1. Build the form in the visual form builder.
2. Open the visual workflow builder and lay out the main stages.
3. Save and verify the stage order / approval groups.
4. Open Django Admin for the saved workflow and add advanced conditions, notification rules, or extra stage fields.
5. Submit a test form and walk it through approvals.

## Related guides

- [Workflows Guide](WORKFLOWS.md)
- [Dynamic Assignees](DYNAMIC_ASSIGNEES.md)
- [Send Back for Correction](SEND_BACK.md)
- [Sub-Workflows](SUB_WORKFLOWS.md)
- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)