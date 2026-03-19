"""
Migration 0056 — Calculated/Formula fields + Spreadsheet upload field type.

Changes:
  * FormField.formula  — new TextField (blank, default='') for the {token} formula.
  * FormField.field_type — extend choices to include 'calculated' and 'spreadsheet'
    (VARCHAR only; no DB constraint enforced on choices).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0055_add_send_back"),
    ]

    operations = [
        # FormField.formula
        migrations.AddField(
            model_name="formfield",
            name="formula",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    'For "Calculated / Formula" fields: use {field_name} tokens to '
                    "reference other fields. Supports literal text and concatenation. "
                    "Example: {dept_code} - {job_type}"
                ),
            ),
        ),
        # FormField.field_type — extend choices
        migrations.AlterField(
            model_name="formfield",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Single Line Text"),
                    ("phone", "Phone Number"),
                    ("textarea", "Multi-line Text"),
                    ("number", "Whole Number"),
                    ("decimal", "Decimal/Currency"),
                    ("date", "Date"),
                    ("datetime", "Date and Time"),
                    ("time", "Time"),
                    ("email", "Email Address"),
                    ("url", "Website URL"),
                    ("select", "Dropdown Select"),
                    ("multiselect", "Multiple Select"),
                    ("radio", "Radio Buttons"),
                    ("checkbox", "Single Checkbox"),
                    ("checkboxes", "Multiple Checkboxes"),
                    ("file", "File Upload"),
                    ("multifile", "Multi-File Upload"),
                    ("hidden", "Hidden Field"),
                    ("section", "Section Header (not a field)"),
                    ("calculated", "Calculated / Formula"),
                    ("spreadsheet", "Spreadsheet Upload (CSV / Excel)"),
                ],
                max_length=20,
            ),
        ),
    ]

