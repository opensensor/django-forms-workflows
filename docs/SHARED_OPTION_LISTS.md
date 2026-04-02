# Shared Option Lists

Shared option lists let you define a reusable set of choices once and reference it from any number of form fields. When you update the list, every field that uses it immediately reflects the change — no per-form editing needed.

## Model

### SharedOptionList

| Field | Type | Purpose |
|---|---|---|
| `name` | CharField | Human-readable name (e.g. "Departments") |
| `slug` | SlugField (unique) | Stable identifier for sync and API references |
| `items` | JSONField | Array of options (see format below) |
| `is_active` | BooleanField | When false, the list is hidden from the form builder |

#### Items format

Items can be either plain strings or value/label objects:

```json
["Engineering", "Marketing", "Sales"]
```

```json
[
  {"value": "eng", "label": "Engineering"},
  {"value": "mkt", "label": "Marketing"},
  {"value": "sales", "label": "Sales"}
]
```

Mixed formats are also supported. The `get_choices()` method returns Django-style `[(value, label), ...]` tuples from either format.

## FormField integration

`FormField` has a `shared_option_list` foreign key (nullable, SET_NULL on delete). When set, it overrides inline choices for any choice-based field type: `select`, `radio`, `multiselect`, `checkboxes`.

### Choice resolution priority

Both `DynamicForm` and `ApprovalStepForm` resolve choices in this order:

1. **Database prefill source** — if `prefill_source_config` is set and returns choices via `return_choices` queries
2. **Shared option list** — if `shared_option_list` is set, calls `get_choices()`
3. **Inline choices** — the `choices` field on the `FormField` definition

This means a shared option list always wins over inline choices, but a database-driven prefill source takes highest priority.

### What happens when a shared list is deleted

The foreign key uses `SET_NULL`, so the field reverts to its inline choices. No data is lost and no error occurs.

## Admin

### SharedOptionListAdmin

A full admin is registered with:

- List display: name, slug, option count, active status
- Search by name and slug
- Prepopulated slug from name
- JSON editor for items

### FormField admin

Both `FormFieldInline` (on FormDefinition) and standalone `FormFieldAdmin` include `shared_option_list` in their "Choices" fieldset.

## Form builder

Choice-based fields (select, radio, multiselect, checkboxes) show a "Shared Option List" dropdown in the field property editor. The dropdown lists all active shared lists with their option counts. Selecting a list overrides the inline choices textarea.

### Builder API endpoints

| URL | Method | Purpose |
|---|---|---|
| `builder/api/shared-lists/` | GET | List all active shared lists |
| `builder/api/shared-lists/save/` | POST | Create or update a shared list |
| `builder/api/shared-lists/delete/<id>/` | POST | Delete a shared list |

These endpoints require admin permissions.

## Sync and cloning

- **Sync export** serializes the `shared_option_list` reference by slug.
- **Sync import** resolves the slug to a `SharedOptionList` on the target instance. If the slug doesn't exist on the target, the field falls back to inline choices.
- **Clone forms** copies the `shared_option_list` FK reference (the cloned field points to the same shared list).

## Example usage

1. Create a shared list "Departments" with items `["Engineering", "Marketing", "Sales", "HR"]`.
2. On any form that needs a department selector, add a `select` field and set its shared option list to "Departments".
3. When a new department is added, update the shared list once — every form using it picks up the change.

## Related docs

- [Payments](PAYMENTS.md)
- [Workflows](WORKFLOWS.md)
- [Form Builder User Guide](FORM_BUILDER_USER_GUIDE.md)
- [Prefill Sources](PREFILL_SOURCES.md)
