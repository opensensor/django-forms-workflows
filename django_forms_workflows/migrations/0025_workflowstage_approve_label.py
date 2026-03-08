from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0024_add_allow_resubmit"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowstage",
            name="approve_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text='Custom label for the approve/complete button shown to the approver (e.g. "Complete", "Confirm", "Sign Off"). Defaults to "Approve" when blank.',
                max_length=100,
            ),
        ),
    ]

