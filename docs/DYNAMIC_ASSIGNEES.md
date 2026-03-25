# Dynamic Assignees

Dynamic assignees let the workflow engine resolve an **individual approver** at submission time from a value the submitter entered in the form — rather than routing to a fixed approval group.

## How It Works

When a `WorkflowStage` has `assignee_form_field` set, the engine:

1. Reads `form_data[assignee_form_field]` from the submission.
2. Looks up a `User` using the configured `assignee_lookup_type`.
3. If the lookup succeeds, creates a single `ApprovalTask` with `assigned_to=<user>` instead of group tasks.
4. If the lookup fails (user not found, blank value), falls back to the stage's normal `approval_groups`.

> **Prerequisite:** The stage must still have at least one `approval_group` configured.  
> The engine checks for non-empty groups *before* calling `_create_stage_tasks`, so a stage with no groups and no `requires_manager_approval` is silently skipped regardless of `assignee_form_field`.

---

## Configuration

### Stage Fields

| Field | Type | Description |
|---|---|---|
| `assignee_form_field` | `CharField` | The `field_name` of the form field that holds the assignee value |
| `assignee_lookup_type` | `CharField` | One of `email`, `username`, `full_name`, `ldap` |
| `validate_assignee_group` | `BooleanField` | When `True` (default), the resolved user must belong to at least one `approval_group` on the stage; if not, falls back to group tasks |

### Admin Setup

1. Open **Django Admin → Workflow Definitions** and select (or create) a workflow.
2. In the **Workflow Stages** inline, add or edit a stage.
3. Set **Assignee Form Field** to the `field_name` of the form field that will hold the approver value (e.g. `manager_email`).
4. Set **Assignee Lookup Type** to the appropriate resolver.
5. Add at least one **Approval Group** (used as fallback and for group-validation).
6. Save.

---

## Lookup Types

### `email`

Looks up `User.objects.get(email=value)`.  The value must contain `@`; otherwise the lookup returns `None` and the engine falls back to group tasks.

**Best for:** forms where the submitter selects or types the approver's email address.

```
Form field name: manager_email
Field label:     Manager Email
Field type:      Email Address
```

### `username`

Looks up `User.objects.get(username=value)`.

**Best for:** internal-facing forms where the submitter knows the Django username.

### `full_name`

Splits the value on the last space to derive `first_name` and `last_name`, then calls:

```python
User.objects.get(first_name=first_name, last_name=last_name)
```

Returns `None` if more than one user matches.

**Best for:** dropdown/select fields populated from a list of employee display names.

### `ldap`

Looks up the user via `get_ldap_attribute(user, assignee_form_field)` — reads the LDAP attribute named by `assignee_form_field` on the *submitting user's* LDAP record and maps it to a `User`.  Useful when the form field holds an LDAP DN or employee ID that identifies the manager.

**Best for:** LDAP/AD environments where manager information is stored as a directory attribute.

---

## Group Validation

When `validate_assignee_group=True` (default), the resolved user is checked against the stage's `approval_groups`:

```python
if not dynamic_assignee.groups.filter(pk__in=group_ids).exists():
    dynamic_assignee = None  # fall back to group tasks
```

Set `validate_assignee_group=False` on the stage to allow *any* resolved user regardless of group membership.

---

## Examples

### Travel Request — Manager Approval by Email

```
Form fields:
  destination      (text)
  start_date       (date)
  manager_email    (email)   ← submitter enters their manager's email

Workflow Stage:
  name:                    Manager Approval
  assignee_form_field:     manager_email
  assignee_lookup_type:    email
  approval_groups:         [All Managers]   ← required for pre-check & fallback
  validate_assignee_group: True
```

The submitter types `jane.smith@acme.com`. At submission time the engine looks up `User(email="jane.smith@acme.com")`, verifies Jane is in **All Managers**, and creates a task assigned directly to her.

### Expense Report — Approver by Full Name (Dropdown)

```
Form field:
  approver_name   (select)   choices: "Alice Brown", "Bob Chen", "Carol Davis"

Workflow Stage:
  assignee_form_field:    approver_name
  assignee_lookup_type:   full_name
  approval_groups:        [Finance Approvers]
  validate_assignee_group: False
```

Because `validate_assignee_group=False`, any resolvable user is accepted even if they haven't been added to the Finance Approvers group yet.

---

## Fallback Behaviour Summary

| Scenario | Result |
|---|---|
| `assignee_form_field` not set | Normal group-task creation |
| Field value present, user found, group-check passes | Personal task assigned to resolved user |
| Field value present, user found, group-check fails (`validate_assignee_group=True`) | Falls back to group tasks |
| Field value present but no matching user | Falls back to group tasks |
| Field value blank / missing | Falls back to group tasks |
| No groups **and** resolution fails | Stage treated as empty → skipped |

---

## Related Docs

- [Workflow Configuration](CONFIGURATION.md)
- [Sub-Workflows](SUB_WORKFLOWS.md)
- [Send Back for Correction](SEND_BACK.md)

