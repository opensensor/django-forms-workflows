from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "django_forms_workflows",
            "0068_drop_legacy_notify_fields",
        ),
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
                    ("country", "Country Picker"),
                    ("us_state", "US State Picker"),
                    ("signature", "Signature"),
                ],
                max_length=20,
            ),
        ),
    ]

