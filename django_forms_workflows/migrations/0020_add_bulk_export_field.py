from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0019_add_ldap_group_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowdefinition",
            name="allow_bulk_export",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow users to select and bulk-export submissions for this form "
                    "into an Excel spreadsheet from the approval and submissions list views."
                ),
            ),
        ),
    ]

