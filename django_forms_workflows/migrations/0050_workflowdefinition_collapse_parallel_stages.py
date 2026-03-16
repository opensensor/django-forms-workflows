from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0049_formfield_multifile_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowdefinition",
            name="collapse_parallel_stages",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, parallel stages that share the same order number are "
                    "collapsed into a single combined table in the approval history, "
                    "instead of each appearing as its own card."
                ),
            ),
        ),
    ]

