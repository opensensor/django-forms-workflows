"""
Data migration: promote legacy flat workflows to staged workflows.

For each WorkflowDefinition that has approval_groups but NO WorkflowStage rows:

  * ``sequence`` logic → one WorkflowStage per group, ordered sequentially.
  * ``any`` / ``all`` logic → one WorkflowStage containing all groups.

Then for each FormField with ``approval_step`` set but ``workflow_stage`` null:
  * Map ``approval_step=N`` to the Nth WorkflowStage (by order).

Finally, backfill ``ApprovalTask.workflow_stage`` for any tasks that have a
``step_number`` / ``stage_number`` but no FK.

Reverse migration removes the auto-created stages and restores the flat groups.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    WorkflowDefinition = apps.get_model("django_forms_workflows", "WorkflowDefinition")
    WorkflowStage = apps.get_model("django_forms_workflows", "WorkflowStage")
    FormField = apps.get_model("django_forms_workflows", "FormField")
    ApprovalTask = apps.get_model("django_forms_workflows", "ApprovalTask")

    for wf in WorkflowDefinition.objects.filter(requires_approval=True):
        # Skip workflows that already have stages
        if wf.stages.exists():
            _backfill_fields_for_existing_stages(wf, FormField)
            _backfill_tasks_for_existing_stages(wf, ApprovalTask)
            continue

        groups = list(wf.approval_groups.all().order_by("id"))
        if not groups:
            continue

        if wf.approval_logic == "sequence":
            # One stage per group, sequential order
            stages = []
            for i, group in enumerate(groups, start=1):
                stage = WorkflowStage.objects.create(
                    workflow=wf,
                    name=f"{group.name} Review",
                    order=i,
                    approval_logic="all",
                    auto_created=True,
                )
                stage.approval_groups.add(group)
                stages.append(stage)
        else:
            # "any" or "all" → single stage with all groups
            stage = WorkflowStage.objects.create(
                workflow=wf,
                name="Review",
                order=1,
                approval_logic=wf.approval_logic,
                auto_created=True,
            )
            stage.approval_groups.set(groups)
            stages = [stage]

        # Map FormField.approval_step → workflow_stage
        _map_approval_step_fields(wf, stages, FormField)

        # Backfill ApprovalTask.workflow_stage
        _backfill_tasks(wf, stages, ApprovalTask)


def _backfill_fields_for_existing_stages(wf, FormField):
    """For workflows that already have stages, map any remaining
    approval_step integers to the corresponding stage."""
    stages = list(wf.stages.order_by("order", "id"))
    if not stages:
        return
    _map_approval_step_fields(wf, stages, FormField)


def _backfill_tasks_for_existing_stages(wf, ApprovalTask):
    """Backfill workflow_stage on tasks for workflows with existing stages."""
    stages = list(wf.stages.order_by("order", "id"))
    if not stages:
        return
    _backfill_tasks(wf, stages, ApprovalTask)


def _map_approval_step_fields(wf, stages, FormField):
    """Map FormField.approval_step=N to the Nth stage (1-indexed)."""
    fields = FormField.objects.filter(
        form_definition=wf.form_definition,
        approval_step__isnull=False,
        workflow_stage__isnull=True,
    )
    for field in fields.iterator():
        step = field.approval_step
        if 1 <= step <= len(stages):
            field.workflow_stage = stages[step - 1]
            field.save(update_fields=["workflow_stage"])


def _backfill_tasks(wf, stages, ApprovalTask):
    """Backfill ApprovalTask.workflow_stage from stage_number or step_number."""
    tasks = ApprovalTask.objects.filter(
        submission__form_definition=wf.form_definition,
        workflow_stage__isnull=True,
    )
    for task in tasks.iterator():
        num = task.stage_number or task.step_number
        if num and 1 <= num <= len(stages):
            task.workflow_stage = stages[num - 1]
            task.save(update_fields=["workflow_stage"])


def backwards(apps, schema_editor):
    WorkflowStage = apps.get_model("django_forms_workflows", "WorkflowStage")
    FormField = apps.get_model("django_forms_workflows", "FormField")
    ApprovalTask = apps.get_model("django_forms_workflows", "ApprovalTask")

    # Restore approval_step from workflow_stage order for fields that were mapped
    for stage in WorkflowStage.objects.filter(auto_created=True):
        FormField.objects.filter(workflow_stage=stage).update(workflow_stage=None)
        ApprovalTask.objects.filter(workflow_stage=stage).update(workflow_stage=None)

    # Delete auto-created stages
    WorkflowStage.objects.filter(auto_created=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0036_add_workflowstage_auto_created"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

