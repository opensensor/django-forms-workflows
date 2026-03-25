from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "django_forms_workflows",
            "0061_add_country_us_state_field_types",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="allow_batch_import",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow users to download a pre-filled Excel template and upload it to "
                    "submit multiple form entries at once. Each row is validated against the "
                    "same rules as the individual form. File upload fields are excluded from "
                    "batch import."
                ),
            ),
        ),
    ]

