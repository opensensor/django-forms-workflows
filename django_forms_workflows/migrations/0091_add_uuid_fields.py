"""
Add UUID fields to FormDefinition, WorkflowDefinition, WorkflowStage,
and SubWorkflowDefinition for stable cross-instance sync identity.

Three-step approach: add nullable → backfill existing rows → make non-null + unique.
"""

import uuid

from django.db import migrations, models


def backfill_uuids(apps, schema_editor):
    """Assign a unique UUID to every existing row that lacks one."""
    for model_name in (
        "FormDefinition",
        "WorkflowDefinition",
        "WorkflowStage",
        "SubWorkflowDefinition",
    ):
        Model = apps.get_model("django_forms_workflows", model_name)
        for obj in Model.objects.filter(uuid__isnull=True).iterator():
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0090_alter_stageapprovalgroup_options_and_more"),
    ]

    operations = [
        # Step 1: Add nullable UUID fields with no default (so existing rows get NULL)
        migrations.AddField(
            model_name="formdefinition",
            name="uuid",
            field=models.UUIDField(
                null=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AddField(
            model_name="workflowdefinition",
            name="uuid",
            field=models.UUIDField(
                null=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AddField(
            model_name="workflowstage",
            name="uuid",
            field=models.UUIDField(
                null=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AddField(
            model_name="subworkflowdefinition",
            name="uuid",
            field=models.UUIDField(
                null=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        # Step 2: Backfill existing rows
        migrations.RunPython(backfill_uuids, migrations.RunPython.noop),
        # Step 3: Make non-null and unique
        migrations.AlterField(
            model_name="formdefinition",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4, unique=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AlterField(
            model_name="workflowdefinition",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4, unique=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AlterField(
            model_name="workflowstage",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4, unique=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
        migrations.AlterField(
            model_name="subworkflowdefinition",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4, unique=True, editable=False, db_index=True,
                help_text="Stable identity for cross-instance sync.",
            ),
        ),
    ]
