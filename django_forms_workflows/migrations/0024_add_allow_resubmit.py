from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0023_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="allow_resubmit",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow submitters to start a new pre-filled submission from a "
                    "rejected or withdrawn submission"
                ),
            ),
        ),
    ]

