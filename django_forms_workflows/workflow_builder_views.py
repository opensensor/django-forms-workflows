"""
Visual Workflow Builder Views

API endpoints for the visual workflow builder interface.
"""

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_time
from django.views.decorators.http import require_GET, require_POST

from .models import (
    FormDefinition,
    NotificationRule,
    PostSubmissionAction,
    StageApprovalGroup,
    SubWorkflowDefinition,
    WorkflowDefinition,
    WorkflowStage,
)

logger = logging.getLogger(__name__)

SUPPORTED_CONDITION_OPERATORS = {
    "equals",
    "not_equals",
    "gt",
    "lt",
    "gte",
    "lte",
    "contains",
    "in",
    "is_empty",
    "not_empty",
}


def _workflow_display_name(workflow, index=None, include_form=False):
    label = workflow.name_label or (
        f"Workflow {index}" if index is not None else f"Workflow #{workflow.id}"
    )
    if include_form:
        return f"{workflow.form_definition.name} — {label}"
    return label


def _resolve_builder_workflow(
    form_definition, workflow_id=None, create_if_missing=False
):
    workflows = list(form_definition.workflows.order_by("id"))
    selected_workflow = None

    if workflow_id not in (None, ""):
        selected_workflow = get_object_or_404(
            WorkflowDefinition, id=workflow_id, form_definition=form_definition
        )
    elif workflows:
        selected_workflow = workflows[0]

    if selected_workflow is None and create_if_missing:
        selected_workflow = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=False
        )
        workflows = [selected_workflow]

    return selected_workflow, workflows


def _normalize_trigger_conditions(raw_conditions):
    if not raw_conditions:
        return None

    if isinstance(raw_conditions, str):
        try:
            raw_conditions = json.loads(raw_conditions)
        except json.JSONDecodeError:
            return None

    if isinstance(raw_conditions, list):
        group_operator = "AND"
        condition_list = raw_conditions
    elif isinstance(raw_conditions, dict):
        if isinstance(raw_conditions.get("conditions"), list):
            group_operator = str(raw_conditions.get("operator", "AND")).upper()
            condition_list = raw_conditions.get("conditions", [])
        elif "field" in raw_conditions:
            group_operator = "AND"
            condition_list = [raw_conditions]
        else:
            return None
    else:
        return None

    group_operator = "OR" if group_operator == "OR" else "AND"
    normalized = []

    for condition in condition_list:
        if not isinstance(condition, dict):
            continue
        field_name = str(condition.get("field", "")).strip()
        operator = str(condition.get("operator", "equals")).strip()
        if not field_name or operator not in SUPPORTED_CONDITION_OPERATORS:
            continue

        normalized_condition = {
            "field": field_name,
            "operator": operator,
        }
        if operator not in {"is_empty", "not_empty"}:
            normalized_condition["value"] = condition.get("value", "")

        normalized.append(normalized_condition)

    if not normalized:
        return None

    return {
        "operator": group_operator,
        "conditions": normalized,
    }


def _serialize_stage_approval_groups(stage):
    return [
        {"id": sag.group_id, "name": sag.group.name, "position": sag.position}
        for sag in stage.stageapprovalgroup_set.select_related("group").order_by(
            "position", "group__name"
        )
    ]


def _serialize_stage_approval_fields(stage):
    return [
        {
            "id": field.id,
            "field_name": field.field_name,
            "field_label": field.field_label,
            "field_type": field.field_type,
            "order": field.order,
        }
        for field in stage.approval_fields.order_by("order", "id")
    ]


def _resolve_form_field_ids(form_definition, raw_entries):
    if not raw_entries:
        return []

    candidate_ids = []
    candidate_names = []
    for entry in raw_entries:
        if isinstance(entry, dict):
            if entry.get("id"):
                candidate_ids.append(entry["id"])
            elif entry.get("field_name"):
                candidate_names.append(entry["field_name"])
        elif isinstance(entry, int):
            candidate_ids.append(entry)
        elif isinstance(entry, str):
            candidate_names.append(entry)

    resolved = []
    if candidate_ids:
        resolved.extend(
            list(
                form_definition.fields.filter(id__in=candidate_ids).values_list(
                    "id", flat=True
                )
            )
        )
    if candidate_names:
        resolved.extend(
            list(
                form_definition.fields.filter(
                    field_name__in=candidate_names
                ).values_list("id", flat=True)
            )
        )

    # Preserve first occurrence order while removing duplicates.
    deduped = []
    seen = set()
    for field_id in resolved:
        if field_id not in seen:
            seen.add(field_id)
            deduped.append(field_id)
    return deduped


def _collect_visual_workflow_errors(workflow_data, form_definition, workflow=None):
    nodes = workflow_data.get("nodes", []) or []
    stage_nodes = [node for node in nodes if node.get("type") == "stage"]
    settings_nodes = [node for node in nodes if node.get("type") == "workflow_settings"]
    email_nodes = [node for node in nodes if node.get("type") == "email"]
    action_nodes = [node for node in nodes if node.get("type") == "action"]
    sub_workflow_nodes = [node for node in nodes if node.get("type") == "sub_workflow"]

    field_records = list(
        form_definition.fields.values("id", "field_name", "field_label")
    )
    field_names = {field["field_name"] for field in field_records}
    field_ids = {field["id"] for field in field_records}
    group_ids = set(Group.objects.values_list("id", flat=True))
    existing_stage_ids = (
        set(workflow.stages.values_list("id", flat=True))
        if workflow is not None
        else set()
    )
    stage_node_ids = {node.get("id") for node in stage_nodes if node.get("id")}
    errors = []
    field_assignments = {}

    def add_error(message):
        errors.append(message)

    def field_reference_exists(value):
        if value in (None, ""):
            return True
        return value in field_names

    def normalize_stage_field_refs(raw_entries):
        resolved_keys = []
        invalid_refs = []
        for entry in raw_entries or []:
            if isinstance(entry, dict):
                if entry.get("id") in field_ids:
                    resolved_keys.append(
                        ("id", entry["id"], entry.get("field_name") or str(entry["id"]))
                    )
                elif entry.get("field_name") in field_names:
                    resolved_keys.append(
                        ("field_name", entry["field_name"], entry["field_name"])
                    )
                else:
                    invalid_refs.append(
                        entry.get("field_name") or entry.get("id") or entry
                    )
            elif isinstance(entry, int):
                if entry in field_ids:
                    resolved_keys.append(("id", entry, str(entry)))
                else:
                    invalid_refs.append(entry)
            elif isinstance(entry, str):
                if entry in field_names:
                    resolved_keys.append(("field_name", entry, entry))
                else:
                    invalid_refs.append(entry)
        return resolved_keys, invalid_refs

    for index, stage_node in enumerate(stage_nodes, start=1):
        stage_data = stage_node.get("data", {})
        stage_label = stage_data.get("name") or f"Stage {index}"
        group_entries = [
            g for g in stage_data.get("approval_groups", []) if g.get("id")
        ]
        has_approver_source = bool(
            group_entries
            or stage_data.get("requires_manager_approval")
            or stage_data.get("assignee_form_field")
        )

        if not str(stage_data.get("name", "")).strip():
            add_error(f"Stage {index} is missing a name.")
        if not has_approver_source:
            add_error(
                f"{stage_label} must define at least one approver source: approval groups, manager approval, or a dynamic assignee field."
            )
        if stage_data.get("assignee_form_field") and not field_reference_exists(
            stage_data.get("assignee_form_field")
        ):
            add_error(
                f"{stage_label} references an unknown assignee form field: {stage_data.get('assignee_form_field')}."
            )
        if (
            stage_data.get("validate_assignee_group", True)
            and stage_data.get("assignee_form_field")
            and not group_entries
        ):
            add_error(
                f"{stage_label} requires approval groups when 'Require Assignee to Belong to Stage Groups' is enabled."
            )

        invalid_group_ids = [
            g.get("id") for g in group_entries if g.get("id") not in group_ids
        ]
        if invalid_group_ids:
            add_error(
                f"{stage_label} references unknown approval group IDs: {', '.join(str(gid) for gid in invalid_group_ids)}."
            )

        normalized_field_refs, invalid_field_refs = normalize_stage_field_refs(
            stage_data.get("approval_fields", [])
        )
        if invalid_field_refs:
            add_error(
                f"{stage_label} references unknown approval-only fields: {', '.join(str(ref) for ref in invalid_field_refs)}."
            )
        for key_type, key_value, label in normalized_field_refs:
            field_key = (key_type, key_value)
            previous_stage = field_assignments.get(field_key)
            if previous_stage and previous_stage != stage_label:
                add_error(
                    f"Approval-only field '{label}' is assigned to multiple stages: {previous_stage} and {stage_label}."
                )
            else:
                field_assignments[field_key] = stage_label

    settings_data = settings_nodes[0].get("data", {}) if settings_nodes else {}
    cadence = settings_data.get("notification_cadence") or "immediate"
    cadence_day = settings_data.get("notification_cadence_day")
    cadence_field = settings_data.get("notification_cadence_form_field")

    if cadence == "weekly" and cadence_day not in range(0, 7):
        add_error("Weekly notification cadence requires a digest day between 0 and 6.")
    if cadence == "monthly" and cadence_day not in range(1, 32):
        add_error(
            "Monthly notification cadence requires a digest day between 1 and 31."
        )
    if cadence == "form_field_date":
        if not cadence_field:
            add_error(
                "Notification cadence 'On Date From Form Field' requires selecting a date field."
            )
        elif cadence_field not in field_names:
            add_error(
                f"Notification cadence references an unknown date field: {cadence_field}."
            )

    for rule_index, rule_data in enumerate(
        settings_data.get("notification_rules", []) or [], start=1
    ):
        stage_node_id = rule_data.get("stage_node_id")
        stage_id = rule_data.get("stage_id")
        if stage_node_id and stage_node_id not in stage_node_ids:
            add_error(
                f"Notification rule {rule_index} references a stage that is not present in the builder graph."
            )
        if stage_id and stage_id not in existing_stage_ids and not stage_node_id:
            add_error(
                f"Notification rule {rule_index} references an unknown workflow stage ID: {stage_id}."
            )

        has_recipients = bool(
            rule_data.get("notify_submitter")
            or rule_data.get("email_field")
            or rule_data.get("static_emails")
            or rule_data.get("notify_stage_assignees")
            or rule_data.get("notify_stage_groups")
            or (rule_data.get("notify_groups") or [])
        )
        if not has_recipients:
            add_error(
                f"Notification rule {rule_index} must define at least one recipient source."
            )
        if rule_data.get("email_field") and not field_reference_exists(
            rule_data.get("email_field")
        ):
            add_error(
                f"Notification rule {rule_index} references an unknown email field: {rule_data.get('email_field')}."
            )

        invalid_notify_group_ids = []
        for group in rule_data.get("notify_groups", []) or []:
            group_id = group.get("id") if isinstance(group, dict) else group
            if group_id and group_id not in group_ids:
                invalid_notify_group_ids.append(group_id)
        if invalid_notify_group_ids:
            add_error(
                f"Notification rule {rule_index} references unknown notify-group IDs: {', '.join(str(gid) for gid in invalid_notify_group_ids)}."
            )

    for email_index, node in enumerate(email_nodes, start=1):
        email_data = node.get("data", {})
        if not (email_data.get("email_to") or email_data.get("email_to_field")):
            add_error(
                f"Email notification {email_index} must define static recipients or a recipient form field."
            )
        if email_data.get("email_to_field") and not field_reference_exists(
            email_data.get("email_to_field")
        ):
            add_error(
                f"Email notification {email_index} references an unknown recipient field: {email_data.get('email_to_field')}."
            )
        if email_data.get("email_cc_field") and not field_reference_exists(
            email_data.get("email_cc_field")
        ):
            add_error(
                f"Email notification {email_index} references an unknown CC field: {email_data.get('email_cc_field')}."
            )

    for action_index, node in enumerate(action_nodes, start=1):
        action_data = node.get("data", {})
        config = action_data.get("config")
        if isinstance(config, str) and config.strip():
            try:
                json.loads(config)
            except json.JSONDecodeError:
                add_error(f"Action {action_index} has invalid JSON configuration.")

    for sub_index, node in enumerate(sub_workflow_nodes, start=1):
        sub_data = node.get("data", {})
        if not sub_data.get("sub_workflow_id"):
            add_error(f"Sub-workflow {sub_index} must select a target workflow.")
        if sub_data.get("count_field") and not field_reference_exists(
            sub_data.get("count_field")
        ):
            add_error(
                f"Sub-workflow {sub_index} references an unknown count field: {sub_data.get('count_field')}."
            )

    return errors


def _validate_visual_workflow(workflow_data, form_definition, workflow=None):
    errors = _collect_visual_workflow_errors(workflow_data, form_definition, workflow)
    if errors:
        raise ValidationError(errors)


def _serialize_notification_rule(rule, stage_node_id=None):
    return {
        "rule_id": rule.id,
        "stage_id": rule.stage_id,
        "stage_node_id": stage_node_id,
        "event": rule.event,
        "conditions": rule.conditions,
        "subject_template": rule.subject_template,
        "notify_submitter": rule.notify_submitter,
        "email_field": rule.email_field,
        "static_emails": rule.static_emails,
        "notify_stage_assignees": rule.notify_stage_assignees,
        "notify_stage_groups": rule.notify_stage_groups,
        "notify_groups": [
            {"id": group.id, "name": group.name}
            for group in rule.notify_groups.order_by("name")
        ],
    }


@staff_member_required
@require_GET
def workflow_builder_view(request, form_id):
    """
    Main workflow builder page.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)
    workflow_id = request.GET.get("workflow_id")
    workflow, workflows = _resolve_builder_workflow(
        form_definition, workflow_id=workflow_id, create_if_missing=True
    )
    workflow_tracks = [
        {
            "id": wf.id,
            "label": _workflow_display_name(wf, index=idx),
        }
        for idx, wf in enumerate(workflows, start=1)
    ]
    selected_index = next(
        (idx for idx, wf in enumerate(workflows, start=1) if wf.id == workflow.id), None
    )

    context = {
        "form_definition": form_definition,
        "form_id": form_id,
        "workflow_id": workflow.id,
        "workflow_count": len(workflows),
        "workflow_tracks": workflow_tracks,
        "selected_workflow_label": _workflow_display_name(
            workflow, index=selected_index
        ),
    }

    return render(
        request, "admin/django_forms_workflows/workflow_builder.html", context
    )


@staff_member_required
@require_GET
def workflow_builder_load(request, form_id):
    """
    API endpoint to load workflow data as JSON.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)
    workflow_id = request.GET.get("workflow_id")
    workflow, workflows = _resolve_builder_workflow(
        form_definition, workflow_id=workflow_id, create_if_missing=True
    )

    # Get form fields for condition/action configuration
    fields = []
    for field in form_definition.fields.all().order_by("order"):
        fields.append(
            {
                "id": field.id,
                "field_name": field.field_name,
                "field_label": field.field_label,
                "field_type": field.field_type,
                "order": field.order,
                "workflow_stage_id": field.workflow_stage_id,
            }
        )

    # Get available groups
    groups = []
    for group in Group.objects.all().order_by("name"):
        groups.append(
            {
                "id": group.id,
                "name": group.name,
            }
        )

    # Legacy additional-form support in the builder.
    forms = []
    for form in FormDefinition.objects.filter(is_active=True).order_by("name"):
        forms.append(
            {
                "id": form.id,
                "name": form.name,
                "slug": form.slug,
                "field_count": form.fields.count(),
            }
        )

    workflow_targets = []
    eligible_workflows = (
        WorkflowDefinition.objects.select_related("form_definition")
        .filter(form_definition__is_active=True)
        .exclude(form_definition_id=form_definition.id)
        .order_by("form_definition__name", "id")
    )
    for idx, target_workflow in enumerate(eligible_workflows, start=1):
        workflow_targets.append(
            {
                "workflow_id": target_workflow.id,
                "workflow_label": _workflow_display_name(
                    target_workflow, index=idx, include_form=True
                ),
                "form_id": target_workflow.form_definition_id,
                "form_name": target_workflow.form_definition.name,
                "field_count": target_workflow.form_definition.fields.count(),
            }
        )

    # Build workflow data
    workflow_data = {
        "nodes": [],
        "connections": [],
    }

    if workflow:
        # Convert existing workflow to visual format
        workflow_data = convert_workflow_to_visual(workflow, form_definition)

    return JsonResponse(
        {
            "success": True,
            "workflow": workflow_data,
            "fields": fields,
            "groups": groups,
            "forms": forms,
            "workflow_id": workflow.id if workflow else None,
            "workflow_tracks": [
                {
                    "id": wf.id,
                    "label": _workflow_display_name(wf, index=idx),
                }
                for idx, wf in enumerate(workflows, start=1)
            ],
            "workflow_targets": workflow_targets,
        }
    )


@staff_member_required
@require_POST
def workflow_builder_save(request):
    """
    API endpoint to save workflow data.
    """
    try:
        data = json.loads(request.body)
        form_id = data.get("form_id")
        workflow_id = data.get("workflow_id")
        workflow_data = data.get("workflow", {})

        logger.info(f"Saving workflow for form {form_id}")
        logger.info(f"Workflow data: {workflow_data}")

        if not form_id:
            return JsonResponse(
                {"success": False, "error": "Form ID is required"}, status=400
            )

        form_definition = get_object_or_404(FormDefinition, id=form_id)
        workflow = None
        if workflow_id not in (None, ""):
            workflow = get_object_or_404(
                WorkflowDefinition, id=workflow_id, form_definition=form_definition
            )

        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Convert visual workflow to model
            workflow = convert_visual_to_workflow(
                workflow_data, form_definition, workflow=workflow
            )
            logger.info(f"Workflow saved successfully: {workflow.id}")

        return JsonResponse(
            {
                "success": True,
                "message": "Workflow saved successfully",
                "workflow_id": workflow.id,
            }
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except ValidationError as exc:
        messages = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        return JsonResponse(
            {
                "success": False,
                "error": "Workflow validation failed.",
                "errors": messages,
            },
            status=400,
        )
    except Exception:
        logger.exception("Error saving workflow in builder")
        return JsonResponse(
            {"success": False, "error": "An internal error occurred."}, status=500
        )


def convert_workflow_to_visual(workflow, form_definition):
    """
    Convert WorkflowDefinition model to visual workflow format.

    Reads WorkflowStage records to build stage nodes.
    """
    stage_defaults = {
        stage.id: {
            "allow_send_back": stage.allow_send_back,
            "allow_reassign": stage.allow_reassign,
            "allow_edit_form_data": stage.allow_edit_form_data,
            "assignee_form_field": stage.assignee_form_field,
            "assignee_lookup_type": stage.assignee_lookup_type,
            "validate_assignee_group": stage.validate_assignee_group,
            "trigger_conditions": stage.trigger_conditions,
            "approval_fields": _serialize_stage_approval_fields(stage),
        }
        for stage in workflow.stages.all()
    }
    settings_defaults = {
        "name_label": workflow.name_label,
        "approval_deadline_days": workflow.approval_deadline_days,
        "send_reminder_after_days": workflow.send_reminder_after_days,
        "auto_approve_after_days": workflow.auto_approve_after_days,
        "notification_cadence": workflow.notification_cadence,
        "notification_cadence_day": workflow.notification_cadence_day,
        "notification_cadence_time": workflow.notification_cadence_time.isoformat()
        if workflow.notification_cadence_time
        else "",
        "notification_cadence_form_field": workflow.notification_cadence_form_field,
        "trigger_conditions": workflow.trigger_conditions,
        "notification_rules": [],
    }
    email_action_defaults = {
        action.id: {
            "email_to": action.email_to or "",
            "email_to_field": action.email_to_field or "",
            "email_cc": action.email_cc or "",
            "email_cc_field": action.email_cc_field or "",
            "email_subject_template": action.email_subject_template or "",
            "email_body_template": action.email_body_template or "",
            "email_template_name": action.email_template_name or "",
        }
        for action in form_definition.post_actions.filter(action_type="email")
    }
    sub_workflow_defaults = None
    if hasattr(workflow, "sub_workflow_definition"):
        sub_wf_config = workflow.sub_workflow_definition
        target_workflow = sub_wf_config.sub_workflow
        sub_workflow_defaults = {
            "sub_workflow_def_id": sub_wf_config.id,
            "sub_workflow_id": target_workflow.id,
            "sub_workflow_form_id": target_workflow.form_definition_id,
            "sub_workflow_name": _workflow_display_name(
                target_workflow, include_form=True
            ),
            "section_label": sub_wf_config.section_label,
            "count_field": sub_wf_config.count_field,
            "label_template": sub_wf_config.label_template,
            "trigger": sub_wf_config.trigger,
            "data_prefix": sub_wf_config.data_prefix,
            "detached": sub_wf_config.detached,
            "reject_parent": sub_wf_config.reject_parent,
        }

    # Check if visual workflow data exists AND has the correct format (nodes array)
    if workflow.visual_workflow_data:
        visual_data = workflow.visual_workflow_data
        # Check if it has the new format with nodes array
        if isinstance(visual_data, dict) and "nodes" in visual_data:
            stage_node_map = {}
            for node in visual_data.get("nodes", []):
                if node.get("type") == "stage":
                    stage_id = node.get("data", {}).get("stage_id")
                    if stage_id:
                        stage_node_map[stage_id] = node.get("id")

            notification_rule_defaults = [
                _serialize_notification_rule(
                    rule,
                    stage_node_id=stage_node_map.get(rule.stage_id),
                )
                for rule in workflow.notification_rules.select_related("stage")
                .prefetch_related("notify_groups")
                .order_by("event", "stage_id", "id")
            ]

            for node in visual_data.get("nodes", []):
                node_type = node.get("type")
                node_data = node.setdefault("data", {})
                if node_type == "stage":
                    stage_id = node_data.get("stage_id")
                    defaults = stage_defaults.get(stage_id)
                    if defaults:
                        for key, value in defaults.items():
                            node_data.setdefault(key, value)
                        if not node_data.get("approval_groups"):
                            node_data["approval_groups"] = (
                                _serialize_stage_approval_groups(
                                    workflow.stages.get(id=stage_id)
                                )
                            )
                elif node_type == "workflow_settings":
                    for key, value in settings_defaults.items():
                        node_data.setdefault(key, value)
                    node_data.setdefault(
                        "notification_rules", notification_rule_defaults
                    )
                elif node_type == "email":
                    action_id = node_data.get("action_id")
                    defaults = email_action_defaults.get(action_id)
                    if defaults:
                        for key, value in defaults.items():
                            node_data.setdefault(key, value)
                elif node_type == "sub_workflow" and sub_workflow_defaults:
                    if (
                        node_data.get("sub_workflow_form_id") in (None, "")
                        and node_data.get("sub_workflow_id")
                        == sub_workflow_defaults["sub_workflow_form_id"]
                    ):
                        node_data["sub_workflow_form_id"] = node_data["sub_workflow_id"]
                        node_data["sub_workflow_id"] = sub_workflow_defaults[
                            "sub_workflow_id"
                        ]
                        node_data["sub_workflow_name"] = sub_workflow_defaults[
                            "sub_workflow_name"
                        ]
                    for key, value in sub_workflow_defaults.items():
                        node_data.setdefault(key, value)
            logger.info("Loading saved visual workflow data (new format)")
            return visual_data
        # Old format (e.g., stages array) - regenerate
        logger.info(
            "Found legacy visual_workflow_data format, regenerating visual layout"
        )

    # Generate default layout from workflow configuration
    logger.info("Generating default visual workflow layout")
    nodes = []
    connections = []
    node_id_counter = 1

    # Layout configuration for better spacing.
    # Keep these values comfortably above the visual builder node widths so
    # generated layouts do not bunch up or overlap before the user edits them.
    horizontal_spacing = 380
    vertical_spacing = 220
    start_x = 120
    start_y = 220
    current_x = start_x
    current_y = start_y

    # Start node (always present)
    start_node = {
        "id": f"node_{node_id_counter}",
        "type": "start",
        "x": current_x,
        "y": current_y,
        "data": {},
    }
    nodes.append(start_node)
    last_node_id = start_node["id"]
    node_id_counter += 1
    current_x += horizontal_spacing

    # Form submission node (always present - represents the actual form)
    form_fields = list(form_definition.fields.all().order_by("order"))

    from django.urls import reverse

    form_builder_url = reverse("admin:form_builder_edit", args=[form_definition.id])

    form_node = {
        "id": f"node_{node_id_counter}",
        "type": "form",
        "x": current_x,
        "y": current_y,
        "data": {
            "form_name": form_definition.name,
            "form_id": form_definition.id,
            "form_builder_url": form_builder_url,
            "field_count": len(form_fields),
            "is_initial": True,
            "enable_multi_step": form_definition.enable_multi_step,
            "form_steps": form_definition.form_steps or [],
            "step_count": len(form_definition.form_steps)
            if form_definition.form_steps
            else 0,
            "fields": [
                {
                    "name": field.field_name,
                    "label": field.field_label,
                    "type": field.field_type,
                    "required": field.required,
                    "prefill_source": field.get_prefill_source_key(),
                }
                for field in form_fields[:10]
            ],
            "has_more_fields": len(form_fields) > 10,
        },
    }
    nodes.append(form_node)
    connections.append({"from": last_node_id, "to": form_node["id"]})
    last_node_id = form_node["id"]
    node_id_counter += 1
    current_x += horizontal_spacing

    # Workflow-level settings node (always present)
    settings_node = {
        "id": f"node_{node_id_counter}",
        "type": "workflow_settings",
        "x": current_x,
        "y": current_y,
        "data": {
            "name_label": workflow.name_label,
            "requires_approval": workflow.requires_approval,
            "approval_deadline_days": workflow.approval_deadline_days,
            "send_reminder_after_days": workflow.send_reminder_after_days,
            "auto_approve_after_days": workflow.auto_approve_after_days,
            "notification_cadence": workflow.notification_cadence,
            "notification_cadence_day": workflow.notification_cadence_day,
            "notification_cadence_time": workflow.notification_cadence_time.isoformat()
            if workflow.notification_cadence_time
            else "",
            "notification_cadence_form_field": workflow.notification_cadence_form_field,
            "trigger_conditions": workflow.trigger_conditions,
        },
    }
    nodes.append(settings_node)
    connections.append({"from": last_node_id, "to": settings_node["id"]})
    last_node_id = settings_node["id"]
    node_id_counter += 1
    current_x += horizontal_spacing

    # ── Stage nodes ──────────────────────────────────────────────────────
    # Group stages by order — stages sharing the same order run in parallel.
    stages = list(workflow.stages.order_by("order", "id"))
    stage_node_map = {}

    if stages:
        from collections import OrderedDict

        order_groups: OrderedDict[int, list] = OrderedDict()
        for stage in stages:
            order_groups.setdefault(stage.order, []).append(stage)

        for _order_val, group in order_groups.items():
            if len(group) == 1:
                # Single stage at this order — render linearly
                stage = group[0]
                stage_groups = _serialize_stage_approval_groups(stage)
                stage_node = {
                    "id": f"node_{node_id_counter}",
                    "type": "stage",
                    "x": current_x,
                    "y": current_y,
                    "data": {
                        "stage_id": stage.id,
                        "name": stage.name,
                        "order": stage.order,
                        "approval_logic": stage.approval_logic,
                        "requires_manager_approval": stage.requires_manager_approval,
                        "allow_send_back": stage.allow_send_back,
                        "allow_reassign": stage.allow_reassign,
                        "allow_edit_form_data": stage.allow_edit_form_data,
                        "approve_label": stage.approve_label or "",
                        "assignee_form_field": stage.assignee_form_field,
                        "assignee_lookup_type": stage.assignee_lookup_type,
                        "validate_assignee_group": stage.validate_assignee_group,
                        "trigger_conditions": stage.trigger_conditions,
                        "approval_fields": _serialize_stage_approval_fields(stage),
                        "approval_groups": stage_groups,
                    },
                }
                nodes.append(stage_node)
                stage_node_map[stage.id] = stage_node["id"]
                connections.append({"from": last_node_id, "to": stage_node["id"]})
                last_node_id = stage_node["id"]
                node_id_counter += 1
                current_x += horizontal_spacing
            else:
                # Multiple stages at this order — render as parallel fork/join
                parallel_node_ids = []
                # Centre the parallel lanes around current_y
                total_height = (len(group) - 1) * vertical_spacing
                start_y = current_y - total_height // 2

                for i, stage in enumerate(group):
                    stage_groups = _serialize_stage_approval_groups(stage)
                    stage_node = {
                        "id": f"node_{node_id_counter}",
                        "type": "stage",
                        "x": current_x,
                        "y": start_y + i * vertical_spacing,
                        "data": {
                            "stage_id": stage.id,
                            "name": stage.name,
                            "order": stage.order,
                            "approval_logic": stage.approval_logic,
                            "requires_manager_approval": stage.requires_manager_approval,
                            "allow_send_back": stage.allow_send_back,
                            "allow_reassign": stage.allow_reassign,
                            "allow_edit_form_data": stage.allow_edit_form_data,
                            "approve_label": stage.approve_label or "",
                            "assignee_form_field": stage.assignee_form_field,
                            "assignee_lookup_type": stage.assignee_lookup_type,
                            "validate_assignee_group": stage.validate_assignee_group,
                            "trigger_conditions": stage.trigger_conditions,
                            "approval_fields": _serialize_stage_approval_fields(stage),
                            "approval_groups": stage_groups,
                        },
                    }
                    nodes.append(stage_node)
                    stage_node_map[stage.id] = stage_node["id"]
                    # Each parallel stage connects FROM the previous node
                    connections.append({"from": last_node_id, "to": stage_node["id"]})
                    parallel_node_ids.append(stage_node["id"])
                    node_id_counter += 1

                current_x += horizontal_spacing

                # Create a join node so all parallel branches merge
                join_node = {
                    "id": f"node_{node_id_counter}",
                    "type": "join",
                    "x": current_x,
                    "y": current_y,
                    "data": {},
                }
                nodes.append(join_node)
                for pid in parallel_node_ids:
                    connections.append({"from": pid, "to": join_node["id"]})
                last_node_id = join_node["id"]
                node_id_counter += 1
                current_x += horizontal_spacing

    settings_node["data"]["notification_rules"] = [
        _serialize_notification_rule(
            rule,
            stage_node_id=stage_node_map.get(rule.stage_id),
        )
        for rule in workflow.notification_rules.select_related("stage")
        .prefetch_related("notify_groups")
        .order_by("event", "stage_id", "id")
    ]
    # Post-submission actions
    actions = form_definition.post_actions.filter(is_active=True).order_by("order")

    # Actions continue on the same horizontal line for a cleaner flow
    for action in actions:
        # Determine node type based on action type
        node_type = "email" if action.action_type == "email" else "action"

        # Build node data
        node_data = {
            "action_id": action.id,
            "name": action.name,
            "action_type": action.action_type,
            "trigger": action.trigger,
        }

        # Add action-type-specific configuration
        if action.action_type == "email":
            # Email actions don't have a dedicated field mapping yet
            # For now, use empty config
            node_data.update(
                {
                    "email_to": action.email_to or "",
                    "email_to_field": action.email_to_field or "",
                    "email_cc": action.email_cc or "",
                    "email_cc_field": action.email_cc_field or "",
                    "email_subject_template": action.email_subject_template or "",
                    "email_body_template": action.email_body_template or "",
                    "email_template_name": action.email_template_name or "",
                }
            )
        elif action.action_type == "database":
            # Include all database configuration for better UI display
            node_data["config"] = {
                "db_alias": action.db_alias or "",
                "db_schema": action.db_schema or "",
                "db_table": action.db_table or "",
                "db_lookup_field": action.db_lookup_field or "ID_NUMBER",
                "db_user_field": action.db_user_field or "employee_id",
                "field_mappings": action.db_field_mappings or [],
            }
        elif action.action_type == "ldap":
            # Include LDAP configuration
            node_data["config"] = {
                "ldap_dn_template": action.ldap_dn_template or "",
                "field_mappings": action.ldap_field_mappings or [],
            }
        elif action.action_type == "api":
            node_data["config"] = {
                "endpoint": action.api_endpoint or "",
                "method": action.api_method or "POST",
                "headers": action.api_headers or {},
                "body_template": action.api_body_template or "",
            }
        elif action.action_type == "custom":
            node_data["config"] = action.custom_handler_config or {}
        else:
            node_data["config"] = {}

        action_node = {
            "id": f"node_{node_id_counter}",
            "type": node_type,
            "x": current_x,
            "y": current_y,
            "data": node_data,
        }
        nodes.append(action_node)
        connections.append(
            {
                "from": last_node_id,
                "to": action_node["id"],
            }
        )
        last_node_id = action_node["id"]
        node_id_counter += 1
        current_x += horizontal_spacing

    # ── Sub-workflow node ──────────────────────────────────────────────
    sub_wf_config = getattr(workflow, "sub_workflow_config", None)
    try:
        sub_wf_config = workflow.sub_workflow_config
    except SubWorkflowDefinition.DoesNotExist:
        sub_wf_config = None

    if sub_wf_config:
        sub_wf = sub_wf_config.sub_workflow
        sub_wf_node = {
            "id": f"node_{node_id_counter}",
            "type": "sub_workflow",
            "x": current_x,
            "y": current_y,
            "data": {
                "sub_workflow_def_id": sub_wf_config.id,
                "sub_workflow_id": sub_wf.id,
                "sub_workflow_form_id": sub_wf.form_definition_id,
                "sub_workflow_name": _workflow_display_name(sub_wf, include_form=True),
                "section_label": sub_wf_config.section_label,
                "count_field": sub_wf_config.count_field,
                "label_template": sub_wf_config.label_template,
                "trigger": sub_wf_config.trigger,
                "data_prefix": sub_wf_config.data_prefix,
                "detached": sub_wf_config.detached,
                "reject_parent": sub_wf_config.reject_parent,
            },
        }
        nodes.append(sub_wf_node)
        connections.append({"from": last_node_id, "to": sub_wf_node["id"]})
        last_node_id = sub_wf_node["id"]
        node_id_counter += 1
        current_x += horizontal_spacing

    # End node
    end_node = {
        "id": f"node_{node_id_counter}",
        "type": "end",
        "x": current_x,
        "y": current_y,
        "data": {
            "status": "approved",
        },
    }
    nodes.append(end_node)
    connections.append(
        {
            "from": last_node_id,
            "to": end_node["id"],
        }
    )

    return {
        "nodes": nodes,
        "connections": connections,
    }


def convert_visual_to_workflow(workflow_data, form_definition, workflow=None):
    """
    Convert visual workflow format to WorkflowDefinition model.

    Stage nodes are persisted as WorkflowStage records.
    """

    _validate_visual_workflow(workflow_data, form_definition, workflow=workflow)

    nodes = workflow_data.get("nodes", [])

    # ── Classify nodes ──────────────────────────────────────────────────
    stage_nodes = []
    action_nodes = []
    email_nodes = []
    sub_workflow_nodes = []
    settings_data = {}

    for node in nodes:
        node_type = node.get("type")
        if node_type == "stage":
            stage_nodes.append(node)
        elif node_type == "action":
            action_nodes.append(node)
        elif node_type == "email":
            email_nodes.append(node)
        elif node_type == "sub_workflow":
            sub_workflow_nodes.append(node)
        elif node_type == "workflow_settings":
            settings_data = node.get("data", {})

    requires_approval = len(stage_nodes) > 0

    # ── Workflow-level settings ──────────────────────────────────────────
    wf_defaults = {
        "name_label": settings_data.get("name_label", ""),
        "requires_approval": settings_data.get("requires_approval", requires_approval),
        "visual_workflow_data": workflow_data,
        "notification_cadence": settings_data.get("notification_cadence", "immediate"),
        "notification_cadence_form_field": settings_data.get(
            "notification_cadence_form_field", ""
        ),
        "trigger_conditions": _normalize_trigger_conditions(
            settings_data.get("trigger_conditions")
        ),
    }

    # Optional numeric fields
    for key in (
        "approval_deadline_days",
        "send_reminder_after_days",
        "auto_approve_after_days",
        "notification_cadence_day",
    ):
        raw = settings_data.get(key)
        wf_defaults[key] = int(raw) if raw not in (None, "") else None
    raw_time = settings_data.get("notification_cadence_time")
    wf_defaults["notification_cadence_time"] = (
        parse_time(raw_time) if raw_time else None
    )

    if workflow is None:
        workflow, _created = WorkflowDefinition.objects.update_or_create(
            form_definition=form_definition,
            defaults=wf_defaults,
        )
    else:
        for key, value in wf_defaults.items():
            setattr(workflow, key, value)
        workflow.form_definition = form_definition
        workflow.save()

    # ── Persist stages ──────────────────────────────────────────────────
    existing_stage_ids = set(workflow.stages.values_list("id", flat=True))
    kept_stage_ids = set()
    stage_node_map = {}
    stage_field_map = {}

    for idx, snode in enumerate(stage_nodes, start=1):
        sdata = snode.get("data", {})
        stage_id = sdata.get("stage_id")
        group_entries = list(sdata.get("approval_groups", []))

        stage_fields = {
            "name": sdata.get("name", f"Stage {idx}"),
            "order": sdata.get("order", idx),
            "approval_logic": sdata.get("approval_logic", "all"),
            "requires_manager_approval": sdata.get("requires_manager_approval", False),
            "allow_send_back": sdata.get("allow_send_back", False),
            "allow_reassign": sdata.get("allow_reassign", False),
            "allow_edit_form_data": sdata.get("allow_edit_form_data", False),
            "approve_label": sdata.get("approve_label", ""),
            "assignee_form_field": sdata.get("assignee_form_field", ""),
            "assignee_lookup_type": sdata.get("assignee_lookup_type", "email"),
            "validate_assignee_group": sdata.get("validate_assignee_group", True),
            "trigger_conditions": _normalize_trigger_conditions(
                sdata.get("trigger_conditions")
            ),
        }

        if stage_id and stage_id in existing_stage_ids:
            WorkflowStage.objects.filter(id=stage_id).update(**stage_fields)
            stage = WorkflowStage.objects.get(id=stage_id)
            kept_stage_ids.add(stage_id)
        else:
            stage = WorkflowStage.objects.create(workflow=workflow, **stage_fields)
            kept_stage_ids.add(stage.id)

        StageApprovalGroup.objects.filter(stage=stage).delete()
        sorted_group_entries = sorted(
            [g for g in group_entries if g.get("id")],
            key=lambda g: g.get("position", 0),
        )
        for pos, group_entry in enumerate(sorted_group_entries):
            StageApprovalGroup.objects.create(
                stage=stage,
                group_id=group_entry["id"],
                position=group_entry.get("position", pos),
            )

        stage_node_map[snode.get("id")] = stage
        stage_field_map[stage.id] = _resolve_form_field_ids(
            form_definition,
            sdata.get("approval_fields", []),
        )

    # Delete stages that were removed in the builder
    workflow.stages.exclude(id__in=kept_stage_ids).delete()

    # Reassign approval-only fields to stages.
    form_definition.fields.filter(workflow_stage__workflow=workflow).update(
        workflow_stage=None
    )
    for stage_id, field_ids in stage_field_map.items():
        if field_ids:
            form_definition.fields.filter(id__in=field_ids).update(
                workflow_stage_id=stage_id
            )

    # ── Notification rules ───────────────────────────────────────────────
    workflow.notification_rules.all().delete()
    for rule_data in settings_data.get("notification_rules", []) or []:
        stage = None
        stage_node_id = rule_data.get("stage_node_id")
        if stage_node_id:
            stage = stage_node_map.get(stage_node_id)
        if stage is None and rule_data.get("stage_id"):
            stage = workflow.stages.filter(id=rule_data.get("stage_id")).first()

        notify_groups = rule_data.get("notify_groups", []) or []
        normalized_group_ids = []
        for group in notify_groups:
            if isinstance(group, dict) and group.get("id"):
                normalized_group_ids.append(group["id"])
            elif isinstance(group, int):
                normalized_group_ids.append(group)

        rule = NotificationRule.objects.create(
            workflow=workflow,
            stage=stage,
            event=rule_data.get("event", "approval_request"),
            conditions=_normalize_trigger_conditions(rule_data.get("conditions")),
            subject_template=rule_data.get("subject_template", ""),
            notify_submitter=rule_data.get("notify_submitter", False),
            email_field=rule_data.get("email_field", ""),
            static_emails=rule_data.get("static_emails", ""),
            notify_stage_assignees=rule_data.get("notify_stage_assignees", False),
            notify_stage_groups=rule_data.get("notify_stage_groups", False),
        )
        if normalized_group_ids:
            rule.notify_groups.set(
                Group.objects.filter(id__in=normalized_group_ids).order_by("name")
            )

    # ── Post-submission actions (unchanged logic) ───────────────────────
    existing_actions = {
        action.name: action for action in form_definition.post_actions.all()
    }
    actions_to_keep = []

    for node in action_nodes:
        data = node.get("data", {})
        action_name = data.get("name", "Unnamed Action")
        action_type = data.get("action_type", "database")

        config = data.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        action_data = {
            "action_type": action_type,
            "trigger": data.get("trigger", "on_approve"),
        }

        if action_type == "database":
            action_data["db_alias"] = config.get("db_alias", "")
            action_data["db_schema"] = config.get("db_schema", "")
            action_data["db_table"] = config.get("db_table", "")
            action_data["db_lookup_field"] = config.get("db_lookup_field", "ID_NUMBER")
            action_data["db_user_field"] = config.get("db_user_field", "employee_id")
            action_data["db_field_mappings"] = config.get(
                "field_mappings", config if isinstance(config, list) else []
            )
        elif action_type == "ldap":
            action_data["ldap_dn_template"] = config.get("ldap_dn_template", "")
            action_data["ldap_field_mappings"] = config.get(
                "field_mappings", config if isinstance(config, list) else []
            )
        elif action_type == "api":
            action_data["api_endpoint"] = config.get("endpoint", "")
            action_data["api_method"] = config.get("method", "POST")
            action_data["api_headers"] = config.get("headers", {})
            action_data["api_body_template"] = config.get("body_template", "")
        elif action_type == "custom":
            action_data["custom_handler_config"] = config

        if action_name in existing_actions:
            action = existing_actions[action_name]
            for key, value in action_data.items():
                setattr(action, key, value)
            action.save()
        else:
            action = PostSubmissionAction.objects.create(
                form_definition=form_definition, name=action_name, **action_data
            )
        actions_to_keep.append(action.id)

    for node in email_nodes:
        data = node.get("data", {})
        action_name = data.get("name", "Email Notification")
        action_data = {
            "action_type": "email",
            "trigger": data.get("trigger", "on_approve"),
            "email_to": data.get("email_to", ""),
            "email_to_field": data.get("email_to_field", ""),
            "email_cc": data.get("email_cc", ""),
            "email_cc_field": data.get("email_cc_field", ""),
            "email_subject_template": data.get("email_subject_template", ""),
            "email_body_template": data.get("email_body_template", ""),
            "email_template_name": data.get("email_template_name", ""),
            "description": data.get(
                "description",
                f"Email to: {data.get('email_to', '') or data.get('email_to_field', '')}, "
                f"Subject: {data.get('email_subject_template', '')}",
            ),
        }
        if action_name in existing_actions:
            action = existing_actions[action_name]
            for key, value in action_data.items():
                setattr(action, key, value)
            action.save()
        else:
            action = PostSubmissionAction.objects.create(
                form_definition=form_definition, name=action_name, **action_data
            )
        actions_to_keep.append(action.id)

    form_definition.post_actions.exclude(id__in=actions_to_keep).delete()

    # ── Sub-workflow definitions ────────────────────────────────────────
    if sub_workflow_nodes:
        # We only support one sub-workflow config per parent workflow (OneToOneField)
        sw_node = sub_workflow_nodes[0]
        sw_data = sw_node.get("data", {})
        target_workflow_id = sw_data.get("sub_workflow_id")

        if target_workflow_id:
            target_workflow = WorkflowDefinition.objects.filter(
                id=target_workflow_id
            ).first()

            if target_workflow is None:
                target_workflow = (
                    WorkflowDefinition.objects.filter(
                        form_definition_id=target_workflow_id
                    )
                    .order_by("id")
                    .first()
                )

            if target_workflow:
                sw_fields = {
                    "sub_workflow": target_workflow,
                    "section_label": sw_data.get("section_label", ""),
                    "count_field": sw_data.get("count_field", ""),
                    "label_template": sw_data.get(
                        "label_template", "Sub-workflow {index}"
                    ),
                    "trigger": sw_data.get("trigger", "on_approval"),
                    "data_prefix": sw_data.get("data_prefix", ""),
                    "detached": sw_data.get("detached", False),
                    "reject_parent": sw_data.get("reject_parent", False),
                }
                SubWorkflowDefinition.objects.update_or_create(
                    parent_workflow=workflow,
                    defaults=sw_fields,
                )
            else:
                logger.warning(
                    "Sub-workflow target %s has no workflow definition",
                    target_workflow_id,
                )
    else:
        # No sub-workflow node — remove any existing config
        SubWorkflowDefinition.objects.filter(parent_workflow=workflow).delete()

    return workflow
