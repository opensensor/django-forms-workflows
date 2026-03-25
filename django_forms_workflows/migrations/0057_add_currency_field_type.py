"""
Migration 0057 — Add 'currency' field type.

Changes:
  * FormField.field_type — extend choices to include 'currency' (Currency ($)).
    The label for 'decimal' is also updated from 'Decimal/Currency' to
    'Decimal Number' now that currency has its own dedicated type.

Note: CharField choices are metadata only — no database schema change occurs.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0056_calculated_formula_spreadsheet"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formfield",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Single Line Text"),
                    ("phone", "Phone Number"),
                    ("textarea", "Multi-line Text"),
                    ("number", "Whole Number"),
                    ("decimal", "Decimal Number"),
                    ("currency", "Currency ($)"),
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

