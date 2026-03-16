from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0050_workflowdefinition_collapse_parallel_stages"),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="is_listed",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When disabled, the form is hidden from the form list page but "
                    "remains accessible to permitted users via its direct slug URL."
                ),
            ),
        ),
    ]

