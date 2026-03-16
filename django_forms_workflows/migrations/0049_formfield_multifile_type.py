from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0048_workflowdefinition_trigger_conditions_and_more"),
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
                ],
            ),
        ),
    ]

