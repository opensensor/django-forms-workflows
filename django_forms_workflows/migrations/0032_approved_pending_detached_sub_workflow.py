from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0031_sub_workflows"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formsubmission",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("pending_approval", "Pending Approval"),
                    ("approved", "Approved"),
                    ("approved_pending", "Approved \u2013 Pending Completion"),
                    ("rejected", "Rejected"),
                    ("withdrawn", "Withdrawn"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="subworkflowdefinition",
            name="detached",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When True, sub-workflows are spawned independently and do not "
                    "affect the parent submission status. When False (default), the "
                    "parent moves to 'Approved \u2013 Pending Completion' until all "
                    "sub-workflow instances finish."
                ),
            ),
        ),
    ]

