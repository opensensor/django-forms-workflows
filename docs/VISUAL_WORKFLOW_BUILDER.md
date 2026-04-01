# Visual Workflow Builder

The visual workflow builder is useful, but it does **not** yet expose every workflow feature the engine supports. This guide is meant to be honest about what works well today, what still lives in Django Admin, and where the sharp edges are.

## Best use of the builder today

Use the builder for the **first-pass shape** of a workflow:

- stage order and parallel stages
- stage approval logic (`all`, `any`, `sequence`)
- switching between existing workflow tracks on the same form
- manager approval, send-back, reassign, reviewer edits
- dynamic assignee basics
- workflow and stage trigger conditions
- notification rules and recipients
- approval-only stage fields
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
- reorder approval groups for sequential stages
- assign approval-only fields to a stage
- choose `all`, `any`, or `sequence`
- enable manager approval
- enable send-back targets
- enable reassignment
- allow reviewer edits to submission data
- set custom approve button labels
- configure dynamic assignees from a form field

### Workflow-level settings

- workflow track label (`name_label`)
- approval deadline
- reminder delay
- auto-approve delay
- notification cadence: `immediate`, `daily`, `weekly`, `monthly`, `form_field_date`
- trigger conditions
- notification rules, event targeting, recipient sources, and rule conditions

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

- any workflow feature not shown directly in the builder properties panel

## Important limitations

### 1. Multi-track workflows

If a form has more than one workflow track, the builder can now switch between and edit the existing tracks one at a time. Creating brand-new tracks is still easiest in Django Admin.

### 2. Legacy node types

Older builder experiments included nodes like extra form steps and visual branch nodes. Workflow conditions are now best managed from the workflow settings and stage property panels rather than separate graph branch nodes.

### 3. Builder is a convenience layer, not the full schema editor

The engine supports more than the canvas currently expresses. When in doubt, treat the builder as the fast visual editor and Django Admin as the complete editor.

### 4. Save validation is intentionally opinionated

The builder now blocks save for common misconfigurations such as:

- stages with no approver source
- duplicate approval-only field assignments across stages
- invalid notification cadence settings
- notification rules or email actions that reference missing recipient fields

Warnings are shown inline when the configuration is technically savable but likely incomplete or confusing.

## Recommended workflow for admins

1. Build the form in the visual form builder.
2. Open the visual workflow builder and lay out the main stages.
3. Use the inline validation summary to fix any blocking errors before saving.
4. Save and verify the stage order / approval groups.
5. Open Django Admin for any advanced workflow behavior that is still not exposed in the builder.
6. Submit a test form and walk it through approvals.

## Related guides

- [Workflows Guide](WORKFLOWS.md)
- [Dynamic Assignees](DYNAMIC_ASSIGNEES.md)
- [Send Back for Correction](SEND_BACK.md)
- [Sub-Workflows](SUB_WORKFLOWS.md)
- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)