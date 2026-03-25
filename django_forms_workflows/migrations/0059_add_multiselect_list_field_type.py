"""
Add multiselect_list field type.

Adds "Multiple Select (List)" as an alternative to the existing
"Multiple Select (Checkboxes)" (multiselect) field type.  The new type
renders using Django's SelectMultiple widget (<select multiple>) rather
than CheckboxSelectMultiple.

The label of the existing 'multiselect' choice is also updated from
"Multiple Select" to "Multiple Select (Checkboxes)" to make the
distinction clear in the admin UI.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0058_rename_assignee_email_field_add_lookup_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formfield",
            name="field_type",
            field=models.CharField(
                max_length=20,
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
                    ("multiselect", "Multiple Select (Checkboxes)"),
                    ("multiselect_list", "Multiple Select (List)"),
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
            ),
        ),
    ]

