"""
Data migration: migrate all deprecated features to their modern replacements.

1. show_if_field / show_if_value  →  conditional_rules JSON
2. Flat WD.approval_groups (orphan M2M rows) → ensure WorkflowStage exists
3. enable_db_updates / db_update_mappings → PostSubmissionAction records
4. WD.escalation_field / escalation_threshold → logged warning (no auto-target)
5. Clear stale visual_workflow_data with old format (no "nodes" key)
6. WorkflowStage.auto_created = True → False  (they are real stages now)
7. Clear orphaned flat WD.approval_groups M2M entries
"""

import json
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    FormField = apps.get_model("django_forms_workflows", "FormField")
    WorkflowDefinition = apps.get_model(
        "django_forms_workflows", "WorkflowDefinition"
    )
    WorkflowStage = apps.get_model("django_forms_workflows", "WorkflowStage")
    PostSubmissionAction = apps.get_model(
        "django_forms_workflows", "PostSubmissionAction"
    )

    # ── 1. show_if_field / show_if_value → conditional_rules ─────────
    for field in FormField.objects.exclude(show_if_field="").exclude(
        show_if_field__isnull=True
    ):
        if field.show_if_value:
            new_rule = {
                "operator": "AND",
                "action": "show",
                "conditions": [
                    {
                        "field": field.show_if_field,
                        "operator": "equals",
                        "value": field.show_if_value,
                    }
                ],
            }
            # Merge into existing conditional_rules if present
            existing = field.conditional_rules or []
            if isinstance(existing, str):
                try:
                    existing = json.loads(existing)
                except (json.JSONDecodeError, TypeError):
                    existing = []
            if not isinstance(existing, list):
                existing = [existing] if existing else []
            existing.append(new_rule)
            field.conditional_rules = existing
            field.show_if_field = ""
            field.show_if_value = ""
            field.save(
                update_fields=[
                    "conditional_rules",
                    "show_if_field",
                    "show_if_value",
                ]
            )
            logger.info(
                "Migrated show_if on field %s (id=%d) to conditional_rules",
                field.field_name,
                field.id,
            )

    # ── 2. Flat approval_groups → ensure stages exist ────────────────
    for wf in WorkflowDefinition.objects.filter(requires_approval=True):
        flat_groups = list(wf.approval_groups.all().order_by("id"))
        if not flat_groups:
            continue
        if wf.stages.exists():
            # Stages already exist — just clear the orphan M2M
            wf.approval_groups.clear()
            logger.info(
                "Cleared orphan flat approval_groups for workflow %d "
                "(stages already exist)",
                wf.id,
            )
            continue
        # No stages yet — create them (safety net for missed 0037)
        if wf.approval_logic == "sequence":
            for i, group in enumerate(flat_groups, start=1):
                stage = WorkflowStage.objects.create(
                    workflow=wf,
                    name=f"{group.name} Review",
                    order=i,
                    approval_logic="all",
                    auto_created=False,
                )
                stage.approval_groups.add(group)
        else:
            stage = WorkflowStage.objects.create(
                workflow=wf,
                name="Review",
                order=1,
                approval_logic=wf.approval_logic,
                auto_created=False,
            )
            stage.approval_groups.set(flat_groups)
        wf.approval_groups.clear()
        logger.info(
            "Created stages from flat approval_groups for workflow %d", wf.id
        )

    # ── 3. enable_db_updates / db_update_mappings → PostSubmissionAction ──
    for wf in WorkflowDefinition.objects.filter(enable_db_updates=True):
        mappings = wf.db_update_mappings or []
        if not mappings:
            wf.enable_db_updates = False
            wf.save(update_fields=["enable_db_updates"])
            continue
        for mapping in mappings:
            form_field = mapping.get("form_field", "")
            db_target = mapping.get("db_target", "")
            PostSubmissionAction.objects.get_or_create(
                form_definition=wf.form_definition,
                name=f"DB Update: {form_field} → {db_target}",
                defaults={
                    "action_type": "database",
                    "trigger": "on_approve",
                    "is_active": True,
                    "config": mapping,
                    "order": 99,
                },
            )
            logger.info(
                "Migrated db_update_mapping %s → %s to PostSubmissionAction "
                "for workflow %d",
                form_field,
                db_target,
                wf.id,
            )
        wf.enable_db_updates = False
        wf.db_update_mappings = None
        wf.save(update_fields=["enable_db_updates", "db_update_mappings"])


    # ── 4. Escalation field/threshold → log warning ──────────────────
    #    Escalation doesn't have a clean 1:1 migration target (it could
    #    become a conditional stage or a post-action).  We log so admins
    #    know to recreate the rule in the new UI, then clear the fields.
    for wf in WorkflowDefinition.objects.exclude(escalation_field=""):
        logger.warning(
            "Workflow %d has escalation_field=%r, threshold=%s. "
            "Please recreate this as a conditional approval stage. "
            "The legacy escalation fields will be removed.",
            wf.id,
            wf.escalation_field,
            wf.escalation_threshold,
        )
        wf.escalation_field = ""
        wf.escalation_threshold = None
        wf.save(update_fields=["escalation_field", "escalation_threshold"])
    # Clear all escalation_groups M2M
    for wf in WorkflowDefinition.objects.all():
        if wf.escalation_groups.exists():
            logger.warning(
                "Clearing escalation_groups for workflow %d", wf.id
            )
            wf.escalation_groups.clear()

    # ── 5. Clear stale visual_workflow_data with old format ──────────
    for wf in WorkflowDefinition.objects.exclude(
        visual_workflow_data__isnull=True
    ):
        data = wf.visual_workflow_data
        if isinstance(data, dict) and "nodes" not in data:
            wf.visual_workflow_data = None
            wf.save(update_fields=["visual_workflow_data"])
            logger.info(
                "Cleared old-format visual_workflow_data for workflow %d",
                wf.id,
            )

    # ── 6. Mark auto_created stages as real ───────────────────────────
    count = WorkflowStage.objects.filter(auto_created=True).update(
        auto_created=False
    )
    if count:
        logger.info(
            "Marked %d auto_created stages as real (auto_created=False)",
            count,
        )

    # ── 7. Clear WD-level requires_manager_approval (migrated to stage)
    #    For any WD that has requires_manager_approval=True but already
    #    has a stage with requires_manager_approval=True, clear the WD flag.
    for wf in WorkflowDefinition.objects.filter(
        requires_manager_approval=True
    ):
        if wf.stages.filter(requires_manager_approval=True).exists():
            wf.requires_manager_approval = False
            wf.save(update_fields=["requires_manager_approval"])
        elif wf.stages.exists():
            # Stages exist but none have manager approval — add it to first
            first_stage = wf.stages.order_by("order").first()
            if first_stage:
                first_stage.requires_manager_approval = True
                first_stage.save(
                    update_fields=["requires_manager_approval"]
                )
                wf.requires_manager_approval = False
                wf.save(update_fields=["requires_manager_approval"])
                logger.info(
                    "Moved requires_manager_approval from workflow %d "
                    "to stage %d (%s)",
                    wf.id,
                    first_stage.id,
                    first_stage.name,
                )


def backwards(apps, schema_editor):
    # Data migrations are not easily reversible.
    # The schema migration (0041) will be the gate — if you revert 0041,
    # the fields come back but the data stays in the new format.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0039_update_help_text"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, elidable=True),
    ]