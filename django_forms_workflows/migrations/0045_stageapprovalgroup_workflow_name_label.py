"""
Create StageApprovalGroup through model for ordered approval groups,
add name_label to WorkflowDefinition, and migrate existing M2M data.
"""

from django.db import migrations, models
import django.db.models.deletion


def migrate_m2m_data(apps, schema_editor):
    """Copy existing auto M2M rows into the new through table."""
    WorkflowStage = apps.get_model("django_forms_workflows", "WorkflowStage")
    StageApprovalGroup = apps.get_model(
        "django_forms_workflows", "StageApprovalGroup"
    )
    # The old auto-created M2M table
    db_alias = schema_editor.connection.alias
    for stage in WorkflowStage.objects.using(db_alias).all():
        # Read from the OLD auto-table which still exists at this point
        old_through = stage.approval_groups.through
        old_rows = (
            old_through.objects.using(db_alias)
            .filter(workflowstage_id=stage.pk)
            .order_by("group_id")
        )
        for position, row in enumerate(old_rows):
            StageApprovalGroup.objects.using(db_alias).get_or_create(
                stage_id=stage.pk,
                group_id=row.group_id,
                defaults={"position": position},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("django_forms_workflows", "0044_remove_subworkflowinstance_label"),
    ]

    operations = [
        # 1. Create the through model table
        migrations.CreateModel(
            name="StageApprovalGroup",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "position",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Order in which this group is processed (lower = first)",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="auth.group",
                    ),
                ),
                (
                    "stage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="django_forms_workflows.workflowstage",
                    ),
                ),
            ],
            options={
                "verbose_name": "Stage Approval Group",
                "verbose_name_plural": "Stage Approval Groups",
                "ordering": ["position"],
                "unique_together": {("stage", "group")},
            },
        ),
        # 2. Copy existing M2M data into the through table
        migrations.RunPython(migrate_m2m_data, migrations.RunPython.noop),
        # 3. Remove the old auto-created M2M field
        migrations.RemoveField(
            model_name="workflowstage",
            name="approval_groups",
        ),
        # 4. Re-add the M2M field with the explicit through model
        migrations.AddField(
            model_name="workflowstage",
            name="approval_groups",
            field=models.ManyToManyField(
                blank=True,
                help_text="Groups that participate in this stage",
                related_name="workflow_stages",
                through="django_forms_workflows.StageApprovalGroup",
                to="auth.group",
            ),
        ),
        # 5. Add name_label to WorkflowDefinition
        migrations.AddField(
            model_name="workflowdefinition",
            name="name_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "User-facing label for this workflow shown in the submission "
                    'detail header (e.g. "Contract Approval"). When blank, falls '
                    "back to the form definition name."
                ),
                max_length=200,
            ),
        ),
    ]

