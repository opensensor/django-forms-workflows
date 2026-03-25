# Calculated / Formula Fields & Spreadsheet Uploads

This guide covers two field types added in v0.33 that extend the form data model beyond simple scalar inputs.

---

## Calculated / Formula Fields

### Overview

A **calculated field** (`field_type = "calculated"`) produces a read-only value that is computed from other field values using a simple template formula.

```
Formula:  {first_name} {last_name}
Result:   "Jane Smith"   (auto-updated as the user types)
```

Calculated fields are:
- **Read-only** — displayed as plain text; not editable by the submitter.
- **Live-updating** — a small vanilla-JS snippet injected by `form_submit.html` watches for `input` / `change` events on dependency fields and updates the calculated field instantly.
- **Server-validated** — `_re_evaluate_calculated_fields()` is called after `serialize_form_data` at submit time so the stored value is always the authoritative server-computed result, regardless of what the client sent.

### Formula Syntax

Formulas use Python `str.format_map` style placeholders:

```
{field_name}
```

Multiple placeholders are supported:

| Formula | Description |
|---|---|
| `{first_name} {last_name}` | Concatenate two text fields |
| `{dept_code}-{job_code}` | Build a composite key |
| `{year}/{month}/{day}` | Compose a date string from separate fields |

> Placeholders that reference fields not yet filled in are left as empty strings (no error).

### Admin Setup

1. Open **Django Admin → Form Definitions → [your form] → Form Fields** inline.
2. Click **Add another Form Field**.
3. Set **Field Type** to **Calculated / Formula**.
4. In the **Formula** text box (in the "Choices & Defaults" fieldset), enter your formula using `{field_name}` placeholders.
5. Set **Required** to unchecked (the field is computed, not user-supplied).
6. Save.

Alternatively, open the field directly via **Admin → Form Fields** where the **Formula** fieldset is in its own collapsed section.

### How Server Re-evaluation Works

```python
# forms.py — called inside serialize_form_data()
def _re_evaluate_calculated_fields(fields, form_data):
    for field in fields.filter(field_type="calculated"):
        formula = field.formula or ""
        try:
            form_data[field.field_name] = formula.format_map(
                defaultdict(str, form_data)
            )
        except (KeyError, ValueError):
            pass  # leave existing value unchanged on error
```

`defaultdict(str, form_data)` ensures that missing keys resolve to `""` rather than raising `KeyError`.

### Approval Step Forms

Calculated fields are also rendered (read-only) inside `ApprovalStepForm`, so approvers can see computed values when reviewing stage-specific fields.

---

## Spreadsheet Upload Fields

### Overview

A **spreadsheet field** (`field_type = "spreadsheet"`) accepts a `.csv`, `.xls`, or `.xlsx` file uploaded by the submitter. The file is parsed server-side and stored as structured JSON in `form_data`.

### Stored Format

```json
{
  "headers": ["Employee ID", "Name", "Hours"],
  "rows": [
    {"Employee ID": "E001", "Name": "Alice", "Hours": "40"},
    {"Employee ID": "E002", "Name": "Bob",   "Hours": "38"}
  ]
}
```

### Supported Formats

| Format | Parser | Requirement |
|---|---|---|
| `.csv` | stdlib `csv` | No extra dependency |
| `.xls` / `.xlsx` | `openpyxl` | `pip install django-forms-workflows[excel]` |

### Admin Setup

1. Open the form's **Form Fields** inline.
2. Add a field with **Field Type = Spreadsheet Upload (CSV / Excel)**.
3. Optionally add help text: `"Upload a CSV or Excel file. First row must be the header."`

### Accessing Spreadsheet Data in Post-Submission Actions

The parsed `rows` list is available in `form_data` under the field's `field_name`:

```python
# In a custom post-submission action handler:
spreadsheet = submission.form_data.get("employees_upload", {})
for row in spreadsheet.get("rows", []):
    employee_id = row.get("Employee ID")
    hours = row.get("Hours")
    # ... write to HR database ...
```

### Approval Step Forms

Spreadsheet fields are also parsed and stored when uploaded during an approval step, consistent with normal submission behaviour.

---

## Related Docs

- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)
- [Form Builder User Guide](FORM_BUILDER_USER_GUIDE.md)
- [Configuration](CONFIGURATION.md)

