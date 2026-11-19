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
from django.db.models import Count, Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
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
from .security import builder_permission_required

logger = logging.getLogger(__name__)


class BuilderValidationError(ValidationError):
    """A user-facing error produced by the workflow builder's own validators."""


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
        if isinstance(workflow_id, bool):
            raise Http404("Invalid workflow id.")
        if isinstance(workflow_id, str):
            workflow_id = workflow_id.strip()
            if not workflow_id.isascii() or not workflow_id.isdigit():
                raise Http404("Invalid workflow id.")
            try:
                workflow_id = int(workflow_id)
            except ValueError as exc:
                raise Http404("Invalid workflow id.") from exc
        if not isinstance(workflow_id, int) or not 0 < workflow_id <= 2**63 - 1:
            raise Http404("Invalid workflow id.")
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
    if (
        raw_conditions is None
        or raw_conditions == ""
        or raw_conditions == []
        or raw_conditions == {}
    ):
        return None

    if isinstance(raw_conditions, str):
        try:
            raw_conditions = json.loads(raw_conditions)
        except json.JSONDecodeError as exc:
            raise ValidationError("Trigger conditions must be valid JSON.") from exc
        if (
            raw_conditions is None
            or raw_conditions == ""
            or raw_conditions == []
            or raw_conditions == {}
        ):
            return None

    if isinstance(raw_conditions, list):
        group_operator = "AND"
        condition_list = raw_conditions
    elif isinstance(raw_conditions, dict):
        if not raw_conditions:
            return None
        if isinstance(raw_conditions.get("conditions"), list):
            group_operator = str(raw_conditions.get("operator", "AND")).upper()
            condition_list = raw_conditions.get("conditions", [])
        elif "field" in raw_conditions:
            group_operator = "AND"
            condition_list = [raw_conditions]
        else:
            raise ValidationError(
                "Trigger conditions must be a list, a single condition object, or an object with a 'conditions' list."
            )
    else:
        raise ValidationError(
            "Trigger conditions must be a list, a single condition object, or an object with a 'conditions' list."
        )

    group_operator = str(group_operator).strip().upper()
    if group_operator not in {"AND", "OR"}:
        raise ValidationError(
            f"Unsupported trigger condition group operator: {group_operator}"
        )

    normalized = []
    for condition in condition_list:
        if not isinstance(condition, dict):
            raise ValidationError(
                "Each trigger condition must be an object with 'field' and 'operator'."
            )
        raw_field_name = condition.get("field", "")
        if not isinstance(raw_field_name, str):
            raise ValidationError("Trigger condition field must be a string.")
        field_name = raw_field_name.strip()
        operator = str(condition.get("operator", "equals")).strip()
        if not field_name:
            raise ValidationError("Trigger condition field cannot be empty.")
        if operator not in SUPPORTED_CONDITION_OPERATORS:
            raise ValidationError(f"Unsupported trigger condition operator: {operator}")

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


def _parse_optional_int_setting(field_name, raw_value):
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, bool):
        raise ValidationError({field_name: "Must be an integer."})
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        value = raw_value.strip()
        digits = value.lstrip("+-")
        if digits and digits.isascii() and digits.isdigit():
            try:
                return int(value)
            except ValueError as exc:
                raise ValidationError({field_name: "Must be an integer."}) from exc
    raise ValidationError({field_name: "Must be an integer."})


def _serialize_stage_approval_groups(stage):
    prefetched_groups = getattr(stage, "prefetched_approval_groups", None)
    if prefetched_groups is None:
        prefetched_groups = list(
            stage.stageapprovalgroup_set.select_related("group").order_by(
                "role", "position", "group__name"
            )
        )

    return [
        {
            "id": sag.group_id,
            "name": sag.group.name,
            "position": sag.position,
            "role": sag.role,
        }
        for sag in prefetched_groups
    ]


def _serialize_stage_approval_fields(stage):
    prefetched_fields = getattr(stage, "prefetched_approval_fields", None)
    if prefetched_fields is None:
        prefetched_fields = list(stage.approval_fields.all())

    ordered_fields = sorted(
        prefetched_fields,
        key=lambda field: ((field.order if field.order is not None else 0), field.id),
    )

    return [
        {
            "id": field.id,
            "field_name": field.field_name,
            "field_label": field.field_label,
            "field_type": field.field_type,
            "order": field.order,
        }
        for field in ordered_fields
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
    field_name_to_id = {
        field["field_name"].strip(): field["id"] for field in field_records
    }
    group_ids = set(Group.objects.values_list("id", flat=True))
    existing_stage_ids = (
        set(workflow.stages.values_list("id", flat=True))
        if workflow is not None
        else set()
    )
    errors = []
    canonical_node_ids = {
        str(node_id).strip()
        for node_id in (node.get("id") for node in nodes)
        if isinstance(node_id, str | int)
        and not isinstance(node_id, bool)
        and str(node_id).strip()
    }
    for connection_index, connection in enumerate(
        workflow_data.get("connections", []) or [], start=1
    ):
        if not isinstance(connection, dict):
            errors.append(f"Connection {connection_index} must be an object.")
            continue
        for endpoint, legacy_endpoint in (("from", "source"), ("to", "target")):
            node_id = connection.get(endpoint, connection.get(legacy_endpoint))
            if (
                isinstance(node_id, bool)
                or not isinstance(node_id, str | int)
                or str(node_id).strip() not in canonical_node_ids
            ):
                errors.append(
                    f"Connection {connection_index} references an unknown {endpoint} node."
                )
    stage_node_ids = set()
    for node in stage_nodes:
        raw_node_id = node.get("id")
        if raw_node_id in (None, ""):
            continue
        if isinstance(raw_node_id, int) and not isinstance(raw_node_id, bool):
            stage_node_ids.add(raw_node_id)
            continue
        if isinstance(raw_node_id, str):
            normalized_node_id = raw_node_id.strip()
            if normalized_node_id:
                stage_node_ids.add(normalized_node_id)
                continue
        errors.append("Each stage node must include a valid scalar 'id'.")
    stage_ids_in_payload = set()
    for node in stage_nodes:
        raw_stage_id = node.get("data", {}).get("stage_id")
        if raw_stage_id in (None, ""):
            continue
        if isinstance(raw_stage_id, int) and not isinstance(raw_stage_id, bool):
            stage_ids_in_payload.add(raw_stage_id)
        elif isinstance(raw_stage_id, str):
            normalized_stage_id = raw_stage_id.strip()
            if normalized_stage_id.isascii() and normalized_stage_id.isdigit():
                try:
                    stage_ids_in_payload.add(int(normalized_stage_id))
                except ValueError:
                    pass  # The converter reports malformed stage IDs.
    field_assignments = {}

    def add_error(message):
        errors.append(message)

    def field_reference_exists(value):
        if value in (None, ""):
            return True
        if not isinstance(value, str):
            add_error("Field references must be strings.")
            return False
        return value in field_names

    def normalize_stage_field_refs(raw_entries):
        resolved_keys = []
        invalid_refs = []

        def is_valid_ref_id(value):
            return isinstance(value, int) and not isinstance(value, bool) and value > 0

        def is_valid_field_name(value):
            return isinstance(value, str)

        if raw_entries is None:
            raw_entries = []
        elif not isinstance(raw_entries, list):
            raise ValidationError("approval_fields must be a list.")
        for entry in raw_entries:
            if isinstance(entry, dict):
                has_id = "id" in entry
                has_field_name = "field_name" in entry
                entry_id = entry.get("id")
                entry_field_name = entry.get("field_name")

                if has_id:
                    if not is_valid_ref_id(entry_id):
                        raise ValidationError(
                            "approval_fields id values must be positive integers."
                        )
                    if entry_id in field_ids:
                        resolved_keys.append(
                            ("id", entry_id, entry_field_name or str(entry_id))
                        )
                    else:
                        invalid_refs.append(entry_id)
                elif has_field_name:
                    if not is_valid_field_name(entry_field_name):
                        raise ValidationError(
                            "approval_fields field_name values must be strings."
                        )
                    if entry_field_name in field_names:
                        resolved_keys.append(
                            ("field_name", entry_field_name, entry_field_name)
                        )
                    else:
                        invalid_refs.append(entry_field_name)
                else:
                    invalid_refs.append(entry)
            elif isinstance(entry, int) and not isinstance(entry, bool):
                if entry <= 0:
                    raise ValidationError(
                        "approval_fields id values must be positive integers."
                    )
                if entry in field_ids:
                    resolved_keys.append(("id", entry, str(entry)))
                else:
                    invalid_refs.append(entry)
            elif isinstance(entry, str):
                if entry in field_names:
                    resolved_keys.append(("field_name", entry, entry))
                else:
                    invalid_refs.append(entry)
            else:
                invalid_refs.append(entry)
        return resolved_keys, invalid_refs

    seen_stage_node_ids = set()
    for index, stage_node in enumerate(stage_nodes, start=1):
        stage_data = stage_node.get("data", {})
        stage_label = stage_data.get("name") or f"Stage {index}"
        stage_identity = index
        node_id = stage_node.get("id")
        canonical_node_id = None
        if node_id not in (None, ""):
            if isinstance(node_id, bool) or not isinstance(node_id, str | int):
                add_error(
                    f"{stage_label} uses an invalid node ID '{node_id}'. Stage node IDs must be non-empty strings or integers."
                )
            else:
                canonical_node_id = (
                    node_id.strip() if isinstance(node_id, str) else str(node_id)
                )
                if canonical_node_id == "":
                    add_error(
                        f"{stage_label} uses an invalid node ID '{node_id}'. Stage node IDs must be non-empty strings or integers."
                    )
                    canonical_node_id = None
        if canonical_node_id is not None:
            if canonical_node_id in seen_stage_node_ids:
                add_error(
                    f"{stage_label} uses a duplicate node ID '{node_id}'. Stage node IDs must be unique."
                )
            else:
                seen_stage_node_ids.add(canonical_node_id)
        raw_group_entries = stage_data.get("approval_groups", [])
        if not isinstance(raw_group_entries, list):
            add_error(f"{stage_label} approval groups must be a list.")
            raw_group_entries = []
        group_entries = []
        malformed_group_ids = []
        for g in raw_group_entries:
            if not isinstance(g, dict):
                malformed_group_ids.append(g)
                continue
            group_id_raw = g.get("id")
            if group_id_raw in (None, ""):
                continue
            if isinstance(group_id_raw, bool):
                malformed_group_ids.append(group_id_raw)
                continue
            if isinstance(group_id_raw, int):
                group_id = group_id_raw
            elif (
                isinstance(group_id_raw, str)
                and group_id_raw.isascii()
                and group_id_raw.isdigit()
            ):
                try:
                    group_id = int(group_id_raw)
                except ValueError:
                    malformed_group_ids.append(group_id_raw)
                    continue
            else:
                malformed_group_ids.append(group_id_raw)
                continue
            if group_id <= 0:
                malformed_group_ids.append(group_id_raw)
                continue

            normalized_group = dict(g)
            normalized_group["id"] = group_id
            group_entries.append(normalized_group)
        requires_manager_approval_raw = stage_data.get("requires_manager_approval")
        if requires_manager_approval_raw is not None and not isinstance(
            requires_manager_approval_raw, bool
        ):
            add_error(
                f"{stage_label} has invalid requires_manager_approval value; expected a boolean."
            )
        requires_manager_approval_flag = requires_manager_approval_raw is True
        has_approval_group_source = any(
            (entry.get("role") or "approval") == "approval" for entry in group_entries
        )
        has_approver_source = bool(
            has_approval_group_source
            or requires_manager_approval_flag
            or stage_data.get("assignee_form_field")
        )

        stage_name = stage_data.get("name")
        if not isinstance(stage_name, str) or not stage_name.strip():
            add_error(f"Stage {index} is missing a name.")
        if malformed_group_ids:
            add_error(
                f"{stage_label} contains invalid approval group IDs (must be positive integers): {', '.join(str(gid) for gid in malformed_group_ids)}."
            )
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
            if key_type == "id":
                canonical_field_id = key_value
            else:
                canonical_field_id = field_name_to_id.get(str(key_value).strip())

            if not canonical_field_id:
                continue

            previous_assignment = field_assignments.get(canonical_field_id)
            if (
                previous_assignment
                and previous_assignment["stage_identity"] != stage_identity
            ):
                add_error(
                    f"Approval-only field '{label}' is assigned to multiple stages: {previous_assignment['stage_label']} and {stage_label}."
                )
            else:
                field_assignments[canonical_field_id] = {
                    "stage_identity": stage_identity,
                    "stage_label": stage_label,
                }

    if len(settings_nodes) > 1:
        add_error("Only one workflow settings node is allowed.")

    settings_data = settings_nodes[0].get("data", {}) if settings_nodes else {}
    supported_cadences = {
        "immediate",
        "weekly",
        "monthly",
        "form_field_date",
    }
    cadence_raw = settings_data.get("notification_cadence")
    if cadence_raw in (None, ""):
        cadence = "immediate"
    elif not isinstance(cadence_raw, str):
        add_error("Notification cadence must be a string value.")
        cadence = "immediate"
    elif cadence_raw not in supported_cadences:
        add_error(f"Unsupported notification cadence: {cadence_raw}.")
        cadence = "immediate"
    else:
        cadence = cadence_raw

    cadence_day_raw = settings_data.get("notification_cadence_day")
    cadence_field = settings_data.get("notification_cadence_form_field")

    cadence_day = None
    if cadence in {"weekly", "monthly"}:
        try:
            cadence_day = _parse_optional_int_setting(
                "notification_cadence_day", cadence_day_raw
            )
        except ValidationError:
            add_error("Notification cadence day must be an integer value.")

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
        elif not isinstance(cadence_field, str):
            add_error(
                "Notification cadence form field reference must be a string value."
            )
        elif cadence_field not in field_names:
            add_error(
                f"Notification cadence references an unknown date field: {cadence_field}."
            )

    notification_rules = settings_data.get("notification_rules", [])
    if notification_rules is None:
        notification_rules = []
    elif not isinstance(notification_rules, list):
        add_error("Workflow settings 'notification_rules' must be a list.")
        notification_rules = []

    canonical_stage_node_ids = {str(node_id).strip() for node_id in stage_node_ids}

    for rule_index, rule_data in enumerate(notification_rules, start=1):
        if not isinstance(rule_data, dict):
            add_error(f"Notification rule {rule_index} must be an object.")
            continue

        stage_node_id = rule_data.get("stage_node_id")
        normalized_stage_node_id = None
        if stage_node_id not in (None, ""):
            if isinstance(stage_node_id, bool):
                add_error(
                    f"Notification rule {rule_index} has an invalid stage node reference."
                )
            elif isinstance(stage_node_id, int):
                normalized_stage_node_id = str(stage_node_id)
            elif isinstance(stage_node_id, str):
                value = stage_node_id.strip()
                if value:
                    normalized_stage_node_id = value
                else:
                    add_error(
                        f"Notification rule {rule_index} has an invalid stage node reference."
                    )
            else:
                add_error(
                    f"Notification rule {rule_index} has an invalid stage node reference."
                )

        stage_id = rule_data.get("stage_id")
        if (
            normalized_stage_node_id is not None
            and normalized_stage_node_id not in canonical_stage_node_ids
        ):
            add_error(
                f"Notification rule {rule_index} references a stage that is not present in the builder graph."
            )

        normalized_stage_id = None
        if stage_id not in (None, ""):
            if isinstance(stage_id, int) and not isinstance(stage_id, bool):
                normalized_stage_id = stage_id
            elif isinstance(stage_id, str):
                value = stage_id.strip()
                if value.isascii() and value.isdigit():
                    try:
                        normalized_stage_id = int(value)
                    except ValueError:
                        normalized_stage_id = None
            if normalized_stage_id is None or normalized_stage_id <= 0:
                add_error(f"Notification rule {rule_index} has an invalid stage ID.")

        if normalized_stage_id is not None and normalized_stage_id > 0:
            if normalized_stage_id not in existing_stage_ids:
                add_error(
                    f"Notification rule {rule_index} references an unknown workflow stage ID: {stage_id}."
                )
            elif (
                normalized_stage_id not in stage_ids_in_payload
                and normalized_stage_node_id is None
            ):
                add_error(
                    f"Notification rule {rule_index} references workflow stage ID {stage_id}, but that stage is not present in the submitted builder graph."
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
        notify_groups = rule_data.get("notify_groups", [])
        if notify_groups is None:
            notify_groups = []
        if not isinstance(notify_groups, list):
            add_error(
                f"Notification rule {rule_index} has invalid notify_groups; expected a list."
            )
            notify_groups = []
        for group in notify_groups:
            group_id = group.get("id") if isinstance(group, dict) else group
            if isinstance(group_id, bool):
                add_error(
                    f"Notification rule {rule_index} has an invalid notify-group ID."
                )
                continue
            if isinstance(group_id, str):
                value = group_id.strip()
                if not value.isascii() or not value.isdigit():
                    add_error(
                        f"Notification rule {rule_index} has an invalid notify-group ID."
                    )
                    continue
                try:
                    group_id = int(value)
                except ValueError:
                    add_error(
                        f"Notification rule {rule_index} has an invalid notify-group ID."
                    )
                    continue
            if not isinstance(group_id, int) or group_id <= 0:
                add_error(
                    f"Notification rule {rule_index} has an invalid notify-group ID."
                )
            elif group_id not in group_ids:
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
        normalized_config = config
        if isinstance(config, str):
            if config.strip():
                try:
                    normalized_config = json.loads(config)
                except json.JSONDecodeError:
                    add_error(f"Action {action_index} has invalid JSON configuration.")
                    continue
            else:
                normalized_config = None

        if normalized_config is None:
            normalized_config = {}

        if not isinstance(normalized_config, dict):
            add_error(f"Action {action_index} configuration must be a JSON object.")

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
        raise BuilderValidationError(errors)


def _serialize_notification_rule(rule, stage_node_id=None):
    return {
        "rule_id": rule.id,
        "stage_id": rule.stage_id,
        "stage_node_id": stage_node_id,
        "event": rule.event,
        "conditions": rule.conditions,
        "subject_template": rule.subject_template,
        "body_template": rule.body_template,
        "notify_submitter": rule.notify_submitter,
        "email_field": rule.email_field,
        "static_emails": rule.static_emails,
        "cc_email_field": rule.cc_email_field,
        "cc_static_emails": rule.cc_static_emails,
        "notify_stage_assignees": rule.notify_stage_assignees,
        "notify_stage_groups": rule.notify_stage_groups,
        "use_triggering_stage": rule.use_triggering_stage,
        "notify_groups": [
            {"id": group.id, "name": group.name}
            for group in sorted(rule.notify_groups.all(), key=lambda group: group.name)
        ],
    }


@staff_member_required
@require_GET
@builder_permission_required("view_formdefinition", "view_workflowdefinition")
def workflow_builder_view(request, form_id):
    """
    Main workflow builder page.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)
    workflow_id = request.GET.get("workflow_id")
    workflow, workflows = _resolve_builder_workflow(
        form_definition, workflow_id=workflow_id
    )
    workflow_tracks = [
        {
            "id": wf.id,
            "label": _workflow_display_name(wf, index=idx),
        }
        for idx, wf in enumerate(workflows, start=1)
    ]
    selected_index = next(
        (
            idx
            for idx, wf in enumerate(workflows, start=1)
            if workflow and wf.id == workflow.id
        ),
        None,
    )

    context = {
        "form_definition": form_definition,
        "form_id": form_id,
        "workflow_id": workflow.id if workflow else None,
        "workflow_count": len(workflows),
        "workflow_tracks": workflow_tracks,
        "selected_workflow_label": _workflow_display_name(
            workflow, index=selected_index
        )
        if workflow
        else "New workflow",
    }

    return render(
        request, "admin/django_forms_workflows/workflow_builder.html", context
    )


@staff_member_required
@require_GET
@builder_permission_required("view_formdefinition", "view_workflowdefinition")
def workflow_builder_load(request, form_id):
    """
    API endpoint to load workflow data as JSON.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)
    workflow_id = request.GET.get("workflow_id")
    workflow, workflows = _resolve_builder_workflow(
        form_definition, workflow_id=workflow_id
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
    active_forms = (
        FormDefinition.objects.filter(is_active=True)
        .annotate(field_count=Count("fields"))
        .order_by("name")
    )
    for form in active_forms:
        forms.append(
            {
                "id": form.id,
                "name": form.name,
                "slug": form.slug,
                "field_count": form.field_count,
            }
        )

    workflow_targets = []
    eligible_workflows = (
        WorkflowDefinition.objects.select_related("form_definition")
        .filter(form_definition__is_active=True)
        .exclude(form_definition_id=form_definition.id)
        .annotate(form_field_count=Count("form_definition__fields"))
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
                "field_count": target_workflow.form_field_count,
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
@builder_permission_required("change_formdefinition", "save_workflowdefinition")
def workflow_builder_save(request):
    """
    API endpoint to save workflow data.
    """
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValidationError(
                "Malformed payload: top-level JSON must be an object."
            )

        form_id = data.get("form_id")
        workflow_id = data.get("workflow_id")
        if "workflow" not in data:
            raise ValidationError("Missing workflow payload.")
        workflow_data = data["workflow"]
        if not isinstance(workflow_data, dict) or not isinstance(
            workflow_data.get("nodes"), list
        ):
            raise ValidationError("Malformed workflow payload: nodes must be a list.")
        if not isinstance(workflow_data.get("connections", []), list):
            raise ValidationError(
                "Malformed workflow payload: connections must be a list."
            )
        for idx, connection in enumerate(workflow_data.get("connections", [])):
            if not isinstance(connection, dict):
                raise ValidationError(
                    f"Malformed workflow payload: connection at index {idx} must be an object."
                )
            for endpoint_key, legacy_key in (("from", "source"), ("to", "target")):
                endpoint_value = connection.get(
                    endpoint_key, connection.get(legacy_key)
                )
                if endpoint_value is None:
                    raise ValidationError(
                        f"Malformed workflow payload: connection at index {idx} is missing '{endpoint_key}'."
                    )
                if isinstance(endpoint_value, bool) or not isinstance(
                    endpoint_value, str | int
                ):
                    raise ValidationError(
                        f"Malformed workflow payload: connection at index {idx} has invalid '{endpoint_key}'."
                    )
                if isinstance(endpoint_value, str) and not endpoint_value.strip():
                    raise ValidationError(
                        f"Malformed workflow payload: connection at index {idx} has empty '{endpoint_key}'."
                    )

        def parse_positive_pk(value, field_name, *, allow_empty=False):
            if allow_empty and value in (None, ""):
                return None
            if isinstance(value, bool):
                raise ValidationError(f"Invalid {field_name}.")
            if isinstance(value, int):
                parsed = value
            elif isinstance(value, str):
                digits = value.strip()
                if not digits.isascii() or not digits.isdigit():
                    raise ValidationError(f"Invalid {field_name}.")
                try:
                    parsed = int(digits)
                except ValueError as exc:
                    raise ValidationError(f"Invalid {field_name}.") from exc
            else:
                raise ValidationError(f"Invalid {field_name}.")
            if not 0 < parsed <= 2**63 - 1:
                raise ValidationError(f"Invalid {field_name}.")
            return parsed

        if not isinstance(workflow_data, dict):
            raise ValidationError("Malformed payload: 'workflow' must be an object.")

        nodes = workflow_data.get("nodes", [])
        if not isinstance(nodes, list):
            raise ValidationError("Malformed payload: 'workflow.nodes' must be a list.")
        allowed_node_types = {
            "start",
            "form",
            "workflow_settings",
            "stage",
            "approval",
            "approval_config",
            "condition",
            "action",
            "email",
            "sub_workflow",
            "join",
            "end",
        }
        if nodes:
            seen_node_ids = {}
            for idx, node in enumerate(nodes):
                if not isinstance(node, dict):
                    raise ValidationError(
                        f"Malformed payload: node at index {idx} must be an object."
                    )
                node_id = node.get("id")
                if node_id is not None and (
                    isinstance(node_id, bool) or not isinstance(node_id, str | int)
                ):
                    raise ValidationError(
                        f"Malformed payload: node.id at index {idx} must be a string or integer."
                    )
                if isinstance(node_id, str) and not node_id.strip():
                    raise ValidationError(
                        f"Malformed payload: node.id at index {idx} must not be empty."
                    )
                node_type = node.get("type")
                if isinstance(node_type, bool) or not isinstance(node_type, str):
                    raise ValidationError(
                        f"Malformed payload: node.type at index {idx} must be a string."
                    )
                if not node_type.strip():
                    raise ValidationError(
                        f"Malformed payload: node.type at index {idx} must not be empty."
                    )
                if node_type not in allowed_node_types:
                    raise ValidationError(
                        f"Malformed payload: node.type at index {idx} is invalid."
                    )
                if node_id is not None:
                    normalized_node_id = str(node_id).strip()
                    if normalized_node_id in seen_node_ids:
                        prev_idx, prev_type = seen_node_ids[normalized_node_id]
                        raise ValidationError(
                            f"Malformed payload: duplicate node.id '{normalized_node_id}' found at indexes "
                            f"{prev_idx} ({prev_type}) and {idx} ({node_type})."
                        )
                    seen_node_ids[normalized_node_id] = (idx, node_type)
                if "data" in node and not isinstance(node["data"], dict):
                    raise ValidationError(
                        f"Malformed payload: node.data at index {idx} must be an object."
                    )
                node_data = node.get("data", {})
                if "approval_groups" in node_data:
                    approval_groups = node_data["approval_groups"]
                    if not isinstance(approval_groups, list):
                        raise ValidationError(
                            f"Malformed payload: node.data.approval_groups at index {idx} must be a list."
                        )
                    for g_idx, group in enumerate(approval_groups):
                        if not isinstance(group, dict):
                            raise ValidationError(
                                f"Malformed payload: node.data.approval_groups[{g_idx}] at node index {idx} must be an object."
                            )

        logger.info(f"Saving workflow for form {form_id}")
        edge_data = workflow_data.get("edges", [])
        node_count = len(nodes) if isinstance(nodes, list) else 0
        edge_count = len(edge_data) if isinstance(edge_data, list) else 0
        logger.info(
            "Workflow payload metadata: form_id=%s workflow_id=%s node_count=%s edge_count=%s",
            form_id,
            workflow_id,
            node_count,
            edge_count,
        )

        if not form_id:
            return JsonResponse(
                {"success": False, "error": "Form ID is required"}, status=400
            )

        form_id = parse_positive_pk(form_id, "form_id")
        workflow_id = parse_positive_pk(workflow_id, "workflow_id", allow_empty=True)

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
                "workflow_id": workflow.id if workflow else None,
            }
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except BuilderValidationError as exc:
        logger.info("Workflow validation failed: %s", exc)
        return JsonResponse(
            {
                "success": False,
                "error": "Workflow validation failed.",
                "errors": exc.messages,
            },
            status=400,
        )
    except ValidationError as exc:
        logger.warning("Workflow validation failed: %s", exc)
        return JsonResponse(
            {
                "success": False,
                "error": "Workflow validation failed.",
                "errors": ["Invalid workflow configuration."],
            },
            status=400,
        )
    except Http404:
        raise
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
    _stages_cache = None
    _stages_by_id_cache = None
    _serialized_stage_approval_fields_cache = None
    _stage_defaults_cache = None

    def _get_stage_defaults():
        nonlocal \
            _stages_cache, \
            _stages_by_id_cache, \
            _serialized_stage_approval_fields_cache, \
            _stage_defaults_cache
        if _stage_defaults_cache is not None:
            return _stage_defaults_cache

        # Load once in deterministic order and reuse in all layout paths.
        # Prefetch approval-fields relation to avoid per-stage queries during serialization.
        _stages_cache = list(
            workflow.stages.all()
            .order_by("order")
            .prefetch_related(
                "approval_fields",
                Prefetch(
                    "stageapprovalgroup_set",
                    queryset=StageApprovalGroup.objects.select_related(
                        "group"
                    ).order_by("role", "position", "group__name"),
                    to_attr="prefetched_approval_groups",
                ),
            )
        )
        _stages_by_id_cache = {stage.id: stage for stage in _stages_cache}
        _serialized_stage_approval_fields_cache = {
            stage.id: _serialize_stage_approval_fields(stage) for stage in _stages_cache
        }
        _stage_defaults_cache = {
            stage.id: {
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
                "approval_fields": _serialized_stage_approval_fields_cache.get(
                    stage.id, []
                ),
                "approval_groups": _serialize_stage_approval_groups(stage),
            }
            for stage in _stages_cache
        }
        return _stage_defaults_cache

    stage_defaults = _get_stage_defaults()
    settings_defaults = {
        "name_label": workflow.name_label,
        "start_trigger": workflow.start_trigger,
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
        "notification_rules": [],
    }
    email_action_defaults = {
        action.id: {
            "name": action.name,
            "trigger": action.trigger,
            "is_active": action.is_active,
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
    if hasattr(workflow, "sub_workflow_config"):
        sub_wf_config = workflow.sub_workflow_config
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
            has_workflow_settings_node = False
            has_sub_workflow_node = False
            form_node_defaults = None
            if any(node.get("type") == "form" for node in visual_data.get("nodes", [])):
                form_fields = list(form_definition.fields.all().order_by("order"))
                form_steps = form_definition.form_steps or []
                form_node_defaults = {
                    "form_id": form_definition.id,
                    "form_name": form_definition.name,
                    "form_builder_url": reverse(
                        "admin:form_builder_edit", args=[form_definition.id]
                    ),
                    "field_count": len(form_fields),
                    "enable_multi_step": form_definition.enable_multi_step,
                    "form_steps": form_steps,
                    "step_count": len(form_steps),
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
                }

            for node in visual_data.get("nodes", []):
                node_type = node.get("type")
                node_data = node.setdefault("data", {})
                if node_type == "stage":
                    raw_stage_id = node_data.get("stage_id")
                    stage_id = None
                    if isinstance(raw_stage_id, int) and not isinstance(
                        raw_stage_id, bool
                    ):
                        stage_id = raw_stage_id
                    elif isinstance(raw_stage_id, str):
                        normalized_stage_id = raw_stage_id.strip()
                        if (
                            normalized_stage_id.isascii()
                            and normalized_stage_id.isdigit()
                        ):
                            try:
                                stage_id = int(normalized_stage_id)
                            except ValueError:
                                stage_id = None
                    if stage_id is not None:
                        node_data["stage_id"] = stage_id
                    else:
                        node_data.pop("stage_id", None)

                    defaults = (
                        stage_defaults.get(stage_id) if stage_id is not None else None
                    )
                    if defaults:
                        for key, value in defaults.items():
                            node_data[key] = value
                elif node_type == "workflow_settings":
                    has_workflow_settings_node = True
                    for key, value in settings_defaults.items():
                        if key == "notification_rules":
                            continue
                        node_data[key] = value
                elif node_type == "email":
                    action_id = node_data.get("action_id")
                    defaults = email_action_defaults.get(action_id)
                    if defaults:
                        for key, value in defaults.items():
                            node_data[key] = value
                elif node_type == "form":
                    if str(node_data.get("form_id", "")).strip() == str(
                        form_definition.id
                    ):
                        for key, value in form_node_defaults.items():
                            node_data[key] = value
                elif node_type == "sub_workflow" and sub_workflow_defaults:
                    has_sub_workflow_node = True
                    if (
                        node_data.get("sub_workflow_form_id") in (None, "")
                        and node_data.get("sub_workflow_id")
                        == sub_workflow_defaults["sub_workflow_form_id"]
                    ):
                        node_data["sub_workflow_form_id"] = node_data["sub_workflow_id"]
                        node_data["sub_workflow_id"] = sub_workflow_defaults[
                            "sub_workflow_id"
                        ]
                        node_data["sub_workflow_id_type"] = "workflow"
                        node_data["sub_workflow_name"] = sub_workflow_defaults[
                            "sub_workflow_name"
                        ]
                    for key, value in sub_workflow_defaults.items():
                        node_data[key] = value
                    node_data["sub_workflow_id_type"] = "workflow"

            existing_nodes = visual_data.get("nodes", [])
            used_node_ids = {
                str(node_id).strip()
                for node_id in (node.get("id") for node in existing_nodes)
                if node_id is not None and str(node_id).strip()
            }

            def allocate_unique_node_id(base_node_id):
                candidate = str(base_node_id).strip()
                canonical_candidate = candidate
                while canonical_candidate in used_node_ids:
                    candidate += "-new"
                    canonical_candidate = candidate.strip()
                used_node_ids.add(canonical_candidate)
                return candidate

            if sub_workflow_defaults and not has_sub_workflow_node:
                sub_workflow_node_id = allocate_unique_node_id(
                    f"sub-workflow-{workflow.id}"
                )
                visual_data.setdefault("nodes", []).append(
                    {
                        "id": sub_workflow_node_id,
                        "type": "sub_workflow",
                        "x": 0,
                        "y": 0,
                        "data": {
                            **sub_workflow_defaults,
                            "sub_workflow_id_type": "workflow",
                        },
                    }
                )

            if not has_workflow_settings_node:
                settings_node_id = allocate_unique_node_id(
                    f"workflow-settings-{workflow.id}"
                )
                visual_data.setdefault("nodes", []).append(
                    {
                        "id": settings_node_id,
                        "type": "workflow_settings",
                        "x": 0,
                        "y": 0,
                        "data": {
                            **settings_defaults,
                        },
                    }
                )

            def normalize_action_id(action_id):
                if isinstance(action_id, bool):
                    return None
                if isinstance(action_id, str):
                    value = action_id.strip()
                    if not value.isascii() or not value.isdigit():
                        return None
                    try:
                        action_id = int(value)
                    except ValueError:
                        return None
                if isinstance(action_id, int) and 0 < action_id <= 2**63 - 1:
                    return action_id
                return None

            existing_email_nodes_by_action_id = {
                normalize_action_id(node.get("data", {}).get("action_id")): node
                for node in visual_data.get("nodes", [])
                if node.get("type") == "email"
                and normalize_action_id(node.get("data", {}).get("action_id"))
                is not None
            }
            email_nodes_in_order = []
            for index, (action_id, defaults) in enumerate(
                email_action_defaults.items()
            ):
                normalized_action_id = normalize_action_id(action_id)
                existing_node = existing_email_nodes_by_action_id.get(
                    normalized_action_id
                )
                if existing_node:
                    existing_node_data = existing_node.setdefault("data", {})
                    existing_node_data["action_id"] = normalized_action_id
                    for key, value in defaults.items():
                        existing_node_data[key] = value
                    email_nodes_in_order.append(existing_node)
                    continue
                email_nodes_in_order.append(
                    {
                        "id": allocate_unique_node_id(
                            f"email-action-{normalized_action_id}"
                        ),
                        "type": "email",
                        "x": 0,
                        "y": index * 120,
                        "data": {
                            "action_id": normalized_action_id,
                            **defaults,
                        },
                    }
                )
            updated_email_nodes_by_action_id = {
                node.get("data", {}).get("action_id"): node
                for node in email_nodes_in_order
                if node.get("data", {}).get("action_id")
            }
            existing_stage_nodes_by_stage_id = {}
            for node in existing_nodes:
                if node.get("type") != "stage":
                    continue
                node_data = node.get("data", {})
                raw_stage_id = node_data.get("stage_id")
                if isinstance(raw_stage_id, bool) or raw_stage_id in (None, ""):
                    continue
                if isinstance(raw_stage_id, int):
                    normalized_stage_id = raw_stage_id
                elif isinstance(raw_stage_id, str):
                    if not raw_stage_id.isascii() or not raw_stage_id.isdigit():
                        continue
                    try:
                        normalized_stage_id = int(raw_stage_id)
                    except ValueError:
                        continue
                else:
                    continue
                if normalized_stage_id <= 0:
                    continue
                node_data["stage_id"] = normalized_stage_id
                existing_stage_nodes_by_stage_id[normalized_stage_id] = node
            stage_ids_in_order = [stage.id for stage in _stages_cache]
            valid_stage_ids = set(stage_ids_in_order)
            stage_nodes_in_order = []
            for index, stage_id in enumerate(stage_ids_in_order):
                existing_stage_node = existing_stage_nodes_by_stage_id.get(stage_id)
                if existing_stage_node:
                    stage_node_data = existing_stage_node.setdefault("data", {})
                    stage_node_data["stage_id"] = stage_id
                    for key, value in stage_defaults[stage_id].items():
                        stage_node_data[key] = value
                    stage_nodes_in_order.append(existing_stage_node)
                    continue
                generated_stage_node_id = allocate_unique_node_id(f"stage-{stage_id}")
                stage_nodes_in_order.append(
                    {
                        "id": generated_stage_node_id,
                        "type": "stage",
                        "x": 0,
                        "y": index * 140,
                        "data": {"stage_id": stage_id, **stage_defaults[stage_id]},
                    }
                )
            updated_stage_nodes_by_stage_id = {
                node.get("data", {}).get("stage_id"): node
                for node in stage_nodes_in_order
                if node.get("data", {}).get("stage_id")
            }
            existing_action_nodes_by_action_id = {
                normalize_action_id(node.get("data", {}).get("action_id")): node
                for node in existing_nodes
                if node.get("type") == "action"
                and normalize_action_id(node.get("data", {}).get("action_id"))
                is not None
            }
            action_nodes_in_order = []
            for index, action in enumerate(
                form_definition.post_actions.exclude(action_type="email").order_by(
                    "order", "id"
                )
            ):
                data = {
                    "action_id": action.id,
                    "name": action.name,
                    "action_type": action.action_type,
                    "trigger": action.trigger,
                    "is_active": action.is_active,
                }
                if action.action_type == "database":
                    data["config"] = {
                        "db_alias": action.db_alias or "",
                        "db_schema": action.db_schema or "",
                        "db_table": action.db_table or "",
                        "db_lookup_field": action.db_lookup_field or "ID_NUMBER",
                        "db_user_field": action.db_user_field or "employee_id",
                        "field_mappings": action.db_field_mappings or [],
                    }
                elif action.action_type == "ldap":
                    data["config"] = {
                        "ldap_dn_template": action.ldap_dn_template or "",
                        "field_mappings": action.ldap_field_mappings or [],
                    }
                elif action.action_type == "api":
                    data["config"] = {
                        "endpoint": action.api_endpoint or "",
                        "method": action.api_method or "POST",
                        "headers": action.api_headers or {},
                        "body_template": action.api_body_template or "",
                    }
                elif action.action_type == "custom":
                    data["config"] = action.custom_handler_config or {}
                else:
                    data["config"] = {}
                action_node = existing_action_nodes_by_action_id.get(action.id)
                if action_node:
                    action_node.setdefault("data", {}).update(data)
                else:
                    action_node = {
                        "id": allocate_unique_node_id(f"action-{action.id}"),
                        "type": "action",
                        "x": 0,
                        "y": index * 120,
                        "data": data,
                    }
                action_nodes_in_order.append(action_node)
            updated_action_nodes_by_action_id = {
                node.get("data", {}).get("action_id"): node
                for node in action_nodes_in_order
                if node.get("data", {}).get("action_id")
            }
            used_email_action_ids = set()
            used_action_ids = set()
            used_stage_ids = set()
            used_sub_workflow = False
            merged_nodes = []
            for node in existing_nodes:
                if node.get("type") == "email":
                    action_id = node.get("data", {}).get("action_id")
                    replacement_node = updated_email_nodes_by_action_id.get(action_id)
                    if replacement_node and action_id not in used_email_action_ids:
                        merged_nodes.append(replacement_node)
                        used_email_action_ids.add(action_id)
                elif node.get("type") == "stage":
                    stage_id = node.get("data", {}).get("stage_id")
                    replacement_node = updated_stage_nodes_by_stage_id.get(stage_id)
                    if (
                        replacement_node
                        and stage_id in valid_stage_ids
                        and stage_id not in used_stage_ids
                    ):
                        merged_nodes.append(replacement_node)
                        used_stage_ids.add(stage_id)
                elif node.get("type") == "action":
                    action_id = node.get("data", {}).get("action_id")
                    replacement_node = updated_action_nodes_by_action_id.get(action_id)
                    if replacement_node and action_id not in used_action_ids:
                        merged_nodes.append(replacement_node)
                        used_action_ids.add(action_id)
                    elif not action_id:
                        merged_nodes.append(node)
                elif node.get("type") == "sub_workflow":
                    sub_workflow_id = node.get("data", {}).get("sub_workflow_id")
                    if (
                        sub_workflow_defaults
                        and sub_workflow_id == sub_workflow_defaults["sub_workflow_id"]
                        and not used_sub_workflow
                    ):
                        merged_nodes.append(node)
                        used_sub_workflow = True
                else:
                    merged_nodes.append(node)

            missing_email_nodes = [
                node
                for action_id, node in updated_email_nodes_by_action_id.items()
                if action_id not in used_email_action_ids
            ]
            missing_action_nodes = [
                node
                for action_id, node in updated_action_nodes_by_action_id.items()
                if action_id not in used_action_ids
                and action_id not in used_email_action_ids
            ]
            missing_stage_nodes = [
                node
                for stage_id, node in updated_stage_nodes_by_stage_id.items()
                if stage_id not in used_stage_ids
            ]
            action_order_by_id = dict(
                form_definition.post_actions.values_list("id", "order")
            )
            missing_mixed_action_nodes = sorted(
                missing_email_nodes + missing_action_nodes,
                key=lambda node: (
                    action_order_by_id.get(node.get("data", {}).get("action_id"), 0),
                    node.get("data", {}).get("action_id", 0),
                ),
            )
            visual_data["nodes"] = (
                merged_nodes + missing_mixed_action_nodes + missing_stage_nodes
            )

            stage_node_map = {
                stage_id: node["id"]
                for stage_id, node in updated_stage_nodes_by_stage_id.items()
            }
            notification_rule_defaults = [
                _serialize_notification_rule(
                    rule,
                    stage_node_id=stage_node_map.get(rule.stage_id),
                )
                for rule in workflow.notification_rules.select_related("stage")
                .prefetch_related("notify_groups")
                .order_by("event", "stage_id", "id")
            ]
            for node in visual_data["nodes"]:
                if node.get("type") == "workflow_settings":
                    node.setdefault("data", {})["notification_rules"] = (
                        notification_rule_defaults
                    )

            def _canonical_node_id(node_id):
                if node_id is None:
                    return None
                canonical = str(node_id).strip()
                return canonical if canonical != "" else None

            email_node_ids = {node.get("id") for node in email_nodes_in_order}
            node_ids_by_canonical = {
                canonical_id: node.get("id")
                for node in visual_data["nodes"]
                if (canonical_id := _canonical_node_id(node.get("id"))) is not None
            }
            existing_connections = visual_data.get("connections", [])
            normalized_connections = []
            for connection in existing_connections:
                from_id = node_ids_by_canonical.get(
                    _canonical_node_id(connection.get("from", connection.get("source")))
                )
                to_id = node_ids_by_canonical.get(
                    _canonical_node_id(connection.get("to", connection.get("target")))
                )
                if from_id is not None and to_id is not None:
                    normalized_connections.append(
                        {
                            "from": from_id,
                            "to": to_id,
                        }
                    )
            non_email_connections = [
                connection
                for connection in normalized_connections
                if not (
                    connection.get("from") in email_node_ids
                    and connection.get("to") in email_node_ids
                )
            ]
            existing_email_connections = [
                connection
                for connection in normalized_connections
                if (
                    connection.get("from") in email_node_ids
                    and connection.get("to") in email_node_ids
                )
            ]
            # Preserve saved topology: do not synthesize a chain across email nodes
            # when no direct email-to-email connections were saved.
            visual_data["connections"] = (
                non_email_connections + existing_email_connections
            )

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
            "start_trigger": workflow.start_trigger,
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
    stages = sorted(_stages_cache, key=lambda stage: (stage.order, stage.id))
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
                        "approval_fields": _serialized_stage_approval_fields_cache[
                            stage.id
                        ],
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
                            "approval_fields": _serialized_stage_approval_fields_cache[
                                stage.id
                            ],
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
    # Include both active and inactive actions so load/save round-trips do not
    # accidentally delete inactive actions omitted from the visual model.
    actions = form_definition.post_actions.order_by("order")

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
            "is_active": action.is_active,
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


@transaction.atomic
def convert_visual_to_workflow(workflow_data, form_definition, workflow=None):
    """
    Convert visual workflow format to WorkflowDefinition model.

    Stage nodes are persisted as WorkflowStage records.
    """

    with transaction.atomic():
        form_definition = FormDefinition.objects.select_for_update().get(
            pk=form_definition.pk
        )

        resolved_workflow = workflow
        if resolved_workflow is None:
            form_workflows = WorkflowDefinition.objects.filter(
                form_definition=form_definition
            )
            if form_workflows.count() == 1:
                resolved_workflow = form_workflows.first()

        _validate_visual_workflow(
            workflow_data, form_definition, workflow=resolved_workflow
        )

        def graph_action_ids(graph):
            if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
                return set()
            result = set()
            for graph_node in graph["nodes"]:
                if not isinstance(graph_node, dict) or graph_node.get("type") not in {
                    "action",
                    "email",
                }:
                    continue
                raw_id = (graph_node.get("data") or {}).get("action_id")
                if (
                    isinstance(raw_id, int)
                    and not isinstance(raw_id, bool)
                    and raw_id > 0
                ):
                    result.add(raw_id)
                elif isinstance(raw_id, str):
                    normalized_raw_id = raw_id.strip()
                    if normalized_raw_id.isascii() and normalized_raw_id.isdigit():
                        try:
                            result.add(int(normalized_raw_id))
                        except ValueError:
                            continue
            return result

        previous_action_ids = graph_action_ids(
            resolved_workflow.visual_workflow_data if resolved_workflow else None
        )
        other_workflow_action_ids = set()
        for other_graph in form_definition.workflows.exclude(
            pk=resolved_workflow.pk if resolved_workflow else None
        ).values_list("visual_workflow_data", flat=True):
            other_workflow_action_ids.update(graph_action_ids(other_graph))

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
    normalized_notification_cadence = (
        settings_data.get("notification_cadence") or "immediate"
    )
    start_trigger_value = settings_data.get("start_trigger", "on_submission")
    valid_start_triggers = {
        choice[0]
        for choice in WorkflowDefinition._meta.get_field("start_trigger").choices
    }
    if (
        not isinstance(start_trigger_value, str)
        or start_trigger_value not in valid_start_triggers
    ):
        raise ValidationError({"start_trigger": "Unsupported start trigger."})

    # ── Workflow-level settings ──────────────────────────────────────────
    wf_defaults = {
        "name_label": settings_data.get("name_label", ""),
        "start_trigger": start_trigger_value,
        "requires_approval": settings_data.get("requires_approval", requires_approval),
        "visual_workflow_data": workflow_data,
        "notification_cadence": normalized_notification_cadence,
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
        parsed_value = _parse_optional_int_setting(key, raw)
        if parsed_value is not None:
            try:
                WorkflowDefinition._meta.get_field(key).clean(parsed_value, None)
            except ValidationError as exc:
                raise ValidationError(
                    {key: exc.messages or ["Must be within the allowed range."]}
                ) from exc
        wf_defaults[key] = parsed_value
    raw_time = settings_data.get("notification_cadence_time")
    if raw_time in (None, ""):
        wf_defaults["notification_cadence_time"] = None
    else:
        if not isinstance(raw_time, str):
            raise ValidationError(
                {"notification_cadence_time": "Must be a valid time string."}
            )
        time_value = raw_time.strip()
        if not time_value:
            wf_defaults["notification_cadence_time"] = None
        else:
            try:
                parsed_time = parse_time(time_value)
            except ValueError as exc:
                raise ValidationError(
                    {"notification_cadence_time": "Must be a valid time."}
                ) from exc
            if parsed_time is None:
                raise ValidationError(
                    {"notification_cadence_time": "Must be a valid time."}
                )
            wf_defaults["notification_cadence_time"] = parsed_time

    if workflow is None:
        candidate_workflows = WorkflowDefinition.objects.filter(
            form_definition=form_definition
        )
        workflow_count = candidate_workflows.count()

        if workflow_count == 0:
            workflow = WorkflowDefinition.objects.create(
                form_definition=form_definition,
                **wf_defaults,
            )
        elif workflow_count == 1:
            workflow = candidate_workflows.first()
            for key, value in wf_defaults.items():
                setattr(workflow, key, value)
            workflow.form_definition = form_definition
            workflow.save()
        else:
            raise ValidationError(
                "Multiple workflow tracks exist for this form. Please select a workflow ID."
            )
    else:
        if workflow.form_definition_id != form_definition.id:
            raise ValidationError(
                "Provided workflow does not belong to the selected form_definition."
            )
        for key, value in wf_defaults.items():
            setattr(workflow, key, value)
        workflow.form_definition = form_definition
        workflow.save()

    # ── Persist stages ──────────────────────────────────────────────────
    existing_stage_ids = set(workflow.stages.values_list("id", flat=True))
    kept_stage_ids = set()
    stage_node_map = {}
    stage_field_map = {}

    submitted_stage_ids = set()
    duplicate_stage_ids = set()
    for snode in stage_nodes:
        sdata = snode.get("data", {})
        raw_stage_id = sdata.get("stage_id")
        if raw_stage_id in (None, ""):
            continue
        if isinstance(raw_stage_id, bool):
            raise ValidationError("Invalid stage_id.")
        if isinstance(raw_stage_id, int):
            stage_id = raw_stage_id
        elif isinstance(raw_stage_id, str):
            value = raw_stage_id.strip()
            if not value.isascii() or not value.isdigit():
                raise ValidationError("Invalid stage_id.")
            try:
                stage_id = int(value)
            except ValueError as exc:
                raise ValidationError("Invalid stage_id.") from exc
        else:
            raise ValidationError("Invalid stage_id.")
        if stage_id <= 0:
            raise ValidationError("Invalid stage_id.")
        sdata["stage_id"] = stage_id
        if stage_id in submitted_stage_ids:
            duplicate_stage_ids.add(stage_id)
        else:
            submitted_stage_ids.add(stage_id)

    if duplicate_stage_ids:
        duplicate_ids_display = ", ".join(
            str(sid) for sid in sorted(duplicate_stage_ids)
        )
        raise ValidationError(
            f"Duplicate stage_id values in workflow data are not allowed: {duplicate_ids_display}."
        )

    for idx, snode in enumerate(stage_nodes, start=1):
        sdata = snode.get("data", {})
        stage_id = sdata.get("stage_id")
        group_entries = list(sdata.get("approval_groups", []))

        raw_order = sdata.get("order", idx)
        if isinstance(raw_order, bool):
            raise ValidationError("Invalid stage order.")
        if isinstance(raw_order, int):
            stage_order = raw_order
        elif isinstance(raw_order, str):
            order_text = raw_order.strip()
            if not order_text.isascii() or not order_text.isdigit():
                raise ValidationError("Invalid stage order.")
            try:
                stage_order = int(order_text)
            except ValueError as exc:
                raise ValidationError("Invalid stage order.") from exc
        else:
            raise ValidationError("Invalid stage order.")
        if not 0 <= stage_order <= 2**31 - 1:
            raise ValidationError("Invalid stage order.")

        raw_approval_logic = sdata.get("approval_logic", "all")
        if not isinstance(raw_approval_logic, str):
            raise ValidationError("Invalid approval logic.")
        approval_logic = raw_approval_logic.strip()
        allowed_approval_logic = {
            value
            for value, _ in WorkflowStage._meta.get_field("approval_logic").choices
        }
        if approval_logic not in allowed_approval_logic:
            raise ValidationError("Invalid approval logic.")

        raw_assignee_lookup_type = sdata.get("assignee_lookup_type", "email")
        if not isinstance(raw_assignee_lookup_type, str):
            raise ValidationError("Invalid assignee lookup type.")
        assignee_lookup_type = raw_assignee_lookup_type.strip()
        allowed_assignee_lookup_types = {
            value
            for value, _ in WorkflowStage._meta.get_field(
                "assignee_lookup_type"
            ).choices
        }
        if assignee_lookup_type not in allowed_assignee_lookup_types:
            raise ValidationError("Invalid assignee lookup type.")

        stage_fields = {
            "name": sdata.get("name", f"Stage {idx}"),
            "order": stage_order,
            "approval_logic": approval_logic,
            "requires_manager_approval": sdata.get("requires_manager_approval", False),
            "allow_send_back": sdata.get("allow_send_back", False),
            "allow_reassign": sdata.get("allow_reassign", False),
            "allow_edit_form_data": sdata.get("allow_edit_form_data", False),
            "approve_label": sdata.get("approve_label", ""),
            "assignee_form_field": sdata.get("assignee_form_field", ""),
            "assignee_lookup_type": assignee_lookup_type,
            "validate_assignee_group": sdata.get("validate_assignee_group", True),
            "trigger_conditions": _normalize_trigger_conditions(
                sdata.get("trigger_conditions")
            ),
        }

        if stage_id:
            if stage_id in existing_stage_ids:
                WorkflowStage.objects.filter(id=stage_id).update(**stage_fields)
                stage = WorkflowStage.objects.get(id=stage_id)
                kept_stage_ids.add(stage_id)
            else:
                raise ValidationError(
                    f"Invalid stage_id '{stage_id}' for this workflow."
                )
        else:
            stage = WorkflowStage.objects.create(workflow=workflow, **stage_fields)
            kept_stage_ids.add(stage.id)

        sdata["stage_id"] = stage.id
        snode["data"] = sdata

        StageApprovalGroup.objects.filter(stage=stage).delete()
        normalized_group_entries = []
        for group_entry in group_entries:
            raw_group_id = group_entry.get("id")
            if raw_group_id in (None, ""):
                continue
            if isinstance(raw_group_id, bool):
                raise ValidationError("Approval group id must be an integer.")
            if isinstance(raw_group_id, int):
                group_id = raw_group_id
            elif isinstance(raw_group_id, str):
                group_id_digits = raw_group_id.strip()
                if not group_id_digits.isascii() or not group_id_digits.isdigit():
                    raise ValidationError("Approval group id must be an integer.")
                try:
                    group_id = int(group_id_digits)
                except ValueError as exc:
                    raise ValidationError(
                        "Approval group id must be an integer."
                    ) from exc
            else:
                raise ValidationError("Approval group id must be an integer.")
            if not 0 < group_id <= 2**63 - 1:
                raise ValidationError("Approval group id must be an integer.")

            raw_position = group_entry.get("position", 0)
            if isinstance(raw_position, bool):
                raise ValidationError("Approval group position must be an integer.")
            if isinstance(raw_position, int):
                position = raw_position
            elif isinstance(raw_position, str):
                digits = raw_position.strip()
                if not digits.isascii() or not digits.isdigit():
                    raise ValidationError("Approval group position must be an integer.")
                try:
                    position = int(digits)
                except ValueError as exc:
                    raise ValidationError(
                        "Approval group position must be an integer."
                    ) from exc
            else:
                raise ValidationError("Approval group position must be an integer.")
            if not 0 <= position <= 2**63 - 1:
                raise ValidationError("Approval group position must be an integer.")

            raw_role = group_entry.get("role", "approval")
            if not isinstance(raw_role, str):
                raise ValidationError("Approval group role must be a string.")
            role = raw_role.strip()
            if not role:
                raise ValidationError("Approval group role must be a non-empty string.")
            valid_roles = {
                choice[0]
                for choice in StageApprovalGroup._meta.get_field("role").choices
            }
            if role not in valid_roles:
                raise ValidationError("Approval group role is invalid.")

            normalized_group_entries.append(
                {**group_entry, "id": group_id, "position": position, "role": role}
            )
        sorted_group_entries = sorted(
            normalized_group_entries,
            key=lambda g: g["position"],
        )
        seen_group_role_pairs = set()
        for pos, group_entry in enumerate(sorted_group_entries):
            role = group_entry["role"]
            assignment_key = (group_entry["id"], role)
            if assignment_key in seen_group_role_pairs:
                raise ValidationError(
                    "Duplicate approval-group assignment for the same group and role is not allowed."
                )
            seen_group_role_pairs.add(assignment_key)
            StageApprovalGroup.objects.create(
                stage=stage,
                group_id=group_entry["id"],
                position=group_entry.get("position", pos),
                role=role,
            )

        raw_node_id = snode.get("id")
        stage_node_map[str(raw_node_id).strip()] = stage
        stage_field_map[stage.id] = _resolve_form_field_ids(
            form_definition,
            sdata.get("approval_fields", []),
        )

    selected_field_ids = {
        field_id for field_ids in stage_field_map.values() for field_id in field_ids
    }
    if selected_field_ids:
        conflicting_field_ids = list(
            form_definition.fields.filter(
                id__in=selected_field_ids,
                workflow_stage__isnull=False,
            )
            .exclude(workflow_stage__workflow=workflow)
            .values_list("id", flat=True)
        )
        if conflicting_field_ids:
            conflicting_ids_display = ", ".join(
                str(fid) for fid in sorted(conflicting_field_ids)
            )
            raise BuilderValidationError(
                "Approval fields already assigned to another workflow track "
                f"cannot be reused here: {conflicting_ids_display}."
            )

    workflow.visual_workflow_data = workflow_data
    workflow.save(update_fields=["visual_workflow_data"])

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
    existing_notification_rules = {
        rule.id: rule for rule in workflow.notification_rules.all()
    }
    kept_notification_rule_ids = set()

    for rule_data in settings_data.get("notification_rules", []) or []:
        stage = None
        raw_stage_node_id = rule_data.get("stage_node_id")
        stage_node_id = (
            raw_stage_node_id.strip()
            if isinstance(raw_stage_node_id, str)
            else raw_stage_node_id
        )
        stage_id = rule_data.get("stage_id")
        has_stage_node_id = stage_node_id is not None and stage_node_id != ""
        has_stage_id = stage_id is not None and stage_id != ""
        explicit_stage_reference = has_stage_node_id or has_stage_id

        raw_rule_id = rule_data.get("rule_id")
        if raw_rule_id in ("", None):
            rule_obj = None
        else:
            if isinstance(raw_rule_id, bool) or not isinstance(raw_rule_id, int | str):
                raise ValidationError("Invalid notification rule identifier.")
            rule_id_text = str(raw_rule_id).strip()
            if not rule_id_text.isascii() or not rule_id_text.isdigit():
                raise ValidationError("Invalid notification rule identifier.")
            normalized_rule_id = int(rule_id_text)
            if not 0 < normalized_rule_id <= 2**63 - 1:
                raise ValidationError("Invalid notification rule identifier.")
            rule_obj = existing_notification_rules.get(normalized_rule_id)
            if rule_obj is None:
                raise ValidationError(
                    "Notification rule does not belong to this workflow."
                )
            if normalized_rule_id in kept_notification_rule_ids:
                raise ValidationError("Duplicate notification rule identifier.")

        if has_stage_node_id:
            if isinstance(stage_node_id, bool) or not isinstance(
                stage_node_id, str | int
            ):
                raise ValidationError("Invalid stage reference in notification rule.")
            stage = stage_node_map.get(str(stage_node_id).strip())
        if stage is None and has_stage_id:
            if isinstance(stage_id, bool):
                raise ValidationError("Invalid stage reference in notification rule.")
            if isinstance(stage_id, str):
                stage_id = stage_id.strip()
                if not stage_id.isascii() or not stage_id.isdigit():
                    raise ValidationError(
                        "Invalid stage reference in notification rule."
                    )
                try:
                    stage_id = int(stage_id)
                except ValueError as exc:
                    raise ValidationError(
                        "Invalid stage reference in notification rule."
                    ) from exc
            if not isinstance(stage_id, int) or not 0 < stage_id <= 2**63 - 1:
                raise ValidationError("Invalid stage reference in notification rule.")
            stage = workflow.stages.filter(id=stage_id).first()
        if stage is None and explicit_stage_reference:
            raise ValidationError("Invalid stage reference in notification rule.")

        notify_groups = rule_data.get("notify_groups", []) or []
        normalized_group_ids = []
        for group in notify_groups:
            if isinstance(group, dict) and group.get("id"):
                normalized_group_ids.append(group["id"])
            elif isinstance(group, int):
                normalized_group_ids.append(group)
            elif isinstance(group, str):
                group_id = group.strip()
                if group_id.isascii() and group_id.isdigit():
                    try:
                        parsed_group_id = int(group_id)
                    except ValueError:
                        continue
                    if 0 < parsed_group_id <= 2**63 - 1:
                        normalized_group_ids.append(parsed_group_id)

        raw_event = rule_data.get("event", "approval_request")
        if not isinstance(raw_event, str):
            raise ValidationError("Invalid notification event.")
        event = raw_event.strip()
        supported_events = {
            value for value, _ in NotificationRule._meta.get_field("event").choices
        }
        if event not in supported_events:
            raise ValidationError("Invalid notification event.")

        rule_values = {
            "stage": stage,
            "event": event,
            "conditions": _normalize_trigger_conditions(rule_data.get("conditions")),
            "subject_template": rule_data.get("subject_template", ""),
            "body_template": rule_data.get(
                "body_template", rule_obj.body_template if rule_obj else ""
            ),
            "notify_submitter": rule_data.get("notify_submitter", False),
            "email_field": rule_data.get("email_field", ""),
            "static_emails": rule_data.get("static_emails", ""),
            "cc_email_field": rule_data.get(
                "cc_email_field", rule_obj.cc_email_field if rule_obj else ""
            ),
            "cc_static_emails": rule_data.get(
                "cc_static_emails", rule_obj.cc_static_emails if rule_obj else ""
            ),
            "notify_stage_assignees": rule_data.get("notify_stage_assignees", False),
            "notify_stage_groups": rule_data.get("notify_stage_groups", False),
            "use_triggering_stage": rule_data.get(
                "use_triggering_stage",
                rule_obj.use_triggering_stage if rule_obj else False,
            ),
        }
        if rule_obj is None:
            rule = NotificationRule.objects.create(workflow=workflow, **rule_values)
        else:
            rule = rule_obj
            for field_name, value in rule_values.items():
                setattr(rule, field_name, value)
            rule.save(update_fields=list(rule_values))
        rule.notify_groups.set(
            Group.objects.filter(id__in=normalized_group_ids).order_by("name")
        )
        kept_notification_rule_ids.add(rule.id)

    workflow.notification_rules.exclude(id__in=kept_notification_rule_ids).delete()

    # ── Post-submission actions (unchanged logic) ───────────────────────
    existing_actions_by_id = {
        action.id: action for action in form_definition.post_actions.all()
    }
    # Legacy fallback for payloads that don't yet send action_id.
    existing_actions_by_name = {
        action.name: action for action in form_definition.post_actions.all()
    }
    actions_to_keep = []

    def save_action(node_data, action_name, action_data):
        if not isinstance(action_name, str):
            raise ValidationError("Invalid action name.")
        action_name = action_name.strip()
        if not action_name:
            raise ValidationError("Invalid action name.")

        raw_action_id = node_data.get("action_id")
        if raw_action_id not in (None, ""):
            if isinstance(raw_action_id, bool):
                raise ValidationError("Invalid action ID.")
            if isinstance(raw_action_id, int):
                action_id = raw_action_id
            elif isinstance(raw_action_id, str):
                action_id_str = raw_action_id.strip()
                if not action_id_str.isascii() or not action_id_str.isdigit():
                    raise ValidationError("Invalid action ID.")
                try:
                    action_id = int(action_id_str)
                except ValueError as exc:
                    raise ValidationError("Invalid action ID.") from exc
            else:
                raise ValidationError("Invalid action ID.")

            if action_id <= 0:
                raise ValidationError("Invalid action ID.")

            action = existing_actions_by_id.get(action_id)
            if action is None:
                raise ValidationError("Action ID does not belong to this form.")
        else:
            action = existing_actions_by_name.get(action_name)

        if action and action.id in actions_to_keep:
            raise ValidationError(
                "An action appears more than once in the builder graph."
            )

        if action:
            action.name = action_name
            action.is_active = node_data.get("is_active", action.is_active)
            for key, value in action_data.items():
                setattr(action, key, value)
            action.save()
        else:
            action = PostSubmissionAction.objects.create(
                form_definition=form_definition,
                name=action_name,
                is_active=node_data.get("is_active", True),
                **action_data,
            )

        # Persist linkage between graph node and DB action so future loads
        # can resolve this node without creating duplicate actions.
        node_data["action_id"] = action.id
        actions_to_keep.append(action.id)

    ordered_nodes = [
        node
        for node in workflow_data.get("nodes", [])
        if node.get("type") in {"action", "email"}
    ]

    for order, node in enumerate(ordered_nodes):
        node_type = node["type"]
        if node_type == "action":
            data = node.setdefault("data", {})
            action_name = data.get("name", "Unnamed Action")
            action_type = data.get("action_type", "database")
            valid_action_types = {
                choice[0]
                for choice in PostSubmissionAction._meta.get_field(
                    "action_type"
                ).choices
            } - {"email"}
            if not isinstance(action_type, str):
                raise ValidationError(
                    "Unsupported action_type type. "
                    f"Expected string, got {type(action_type).__name__}. "
                    f"Supported values are: {sorted(valid_action_types)}"
                )
            if action_type not in valid_action_types:
                raise ValidationError(
                    f"Unsupported action_type '{action_type}'. "
                    f"Supported values are: {sorted(valid_action_types)}"
                )

            config = data.get("config") or {}
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}

            if config is None:
                config = {}
            elif not isinstance(config, dict | list):
                config = {}

            trigger = data.get("trigger", "on_approve")
            valid_triggers = {
                choice[0]
                for choice in PostSubmissionAction._meta.get_field("trigger").choices
            }
            if not isinstance(trigger, str):
                raise ValidationError(
                    "Unsupported trigger type. "
                    f"Expected string, got {type(trigger).__name__}. "
                    f"Supported values are: {sorted(valid_triggers)}"
                )
            if trigger not in valid_triggers:
                raise ValidationError(
                    f"Unsupported trigger '{trigger}'. "
                    f"Supported values are: {sorted(valid_triggers)}"
                )

            action_data = {
                "action_type": action_type,
                "trigger": trigger,
                "order": order,
            }

            if action_type == "database":
                action_data["db_alias"] = config.get("db_alias", "")
                action_data["db_schema"] = config.get("db_schema", "")
                action_data["db_table"] = config.get("db_table", "")
                action_data["db_lookup_field"] = config.get(
                    "db_lookup_field", "ID_NUMBER"
                )
                action_data["db_user_field"] = config.get(
                    "db_user_field", "employee_id"
                )
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

            save_action(data, action_name, action_data)
            continue

        data = node.get("data", {})
        action_name = data.get("name", "Email Notification")
        if not isinstance(action_name, str):
            raise ValidationError("Email action name must be a string.")
        normalized_action_name = action_name.strip()
        if not normalized_action_name:
            raise ValidationError("Email action name cannot be blank.")
        generated_description = (
            f"Email to: {data.get('email_to', '') or data.get('email_to_field', '')}, "
            f"Subject: {data.get('email_subject_template', '')}"
        )
        if "description" in data:
            description_value = data.get("description")
        else:
            description_value = None
            existing_action = None
            raw_action_id = data.get("action_id")
            try:
                action_id = int(raw_action_id)
            except (TypeError, ValueError):
                action_id = None
            if action_id is not None:
                existing_action = existing_actions_by_id.get(action_id)
            if existing_action is None:
                existing_action = existing_actions_by_name.get(normalized_action_name)
            if existing_action is not None:
                description_value = existing_action.description
            if description_value is None:
                description_value = generated_description

        trigger = data.get("trigger", "on_approve")
        valid_triggers = {
            choice[0]
            for choice in PostSubmissionAction._meta.get_field("trigger").choices
        }
        if not isinstance(trigger, str) or trigger not in valid_triggers:
            raise ValidationError("Unsupported trigger for email action.")

        action_data = {
            "action_type": "email",
            "trigger": trigger,
            "order": order,
            "email_to": data.get("email_to", ""),
            "email_to_field": data.get("email_to_field", ""),
            "email_cc": data.get("email_cc", ""),
            "email_cc_field": data.get("email_cc_field", ""),
            "email_subject_template": data.get("email_subject_template", ""),
            "email_body_template": data.get("email_body_template", ""),
            "email_template_name": data.get("email_template_name", ""),
            "description": description_value,
        }
        save_action(data, normalized_action_name, action_data)

    # Explicit deletion only: preserve cross-track actions unless the client
    # requests specific action IDs to remove.
    deleted_action_ids = workflow_data.get("deleted_action_ids", [])
    if deleted_action_ids is None:
        deleted_action_ids = []
    if not isinstance(deleted_action_ids, list):
        raise ValidationError(
            {"deleted_action_ids": "Must be a list of action IDs to delete."}
        )

    normalized_deleted_ids = set()
    max_primary_key_value = (2**63) - 1
    for raw_id in deleted_action_ids:
        if isinstance(raw_id, bool):
            raise ValidationError({"deleted_action_ids": "Invalid action ID."})
        if isinstance(raw_id, int):
            action_id = raw_id
        elif isinstance(raw_id, str) and raw_id.isascii() and raw_id.isdigit():
            try:
                action_id = int(raw_id)
            except ValueError as exc:
                raise ValidationError(
                    {"deleted_action_ids": "Invalid action ID."}
                ) from exc
        else:
            raise ValidationError({"deleted_action_ids": "Invalid action ID."})
        if action_id <= 0 or action_id > max_primary_key_value:
            raise ValidationError({"deleted_action_ids": "Invalid action ID."})
        normalized_deleted_ids.add(action_id)

    # The loader can add missing form-owned actions to the graph.
    # Allow the builder to delete those generated nodes as well as saved ones.
    allowed_deleted_action_ids = set(previous_action_ids) | set(
        PostSubmissionAction.objects.filter(
            form_definition=form_definition
        ).values_list("id", flat=True)
    )

    if normalized_deleted_ids - allowed_deleted_action_ids:
        raise ValidationError(
            {
                "deleted_action_ids": "Actions must belong to the saved workflow graph or be form actions."
            }
        )
    if normalized_deleted_ids & other_workflow_action_ids:
        raise ValidationError(
            {"deleted_action_ids": "An action is still used by another workflow."}
        )
    if normalized_deleted_ids & set(actions_to_keep):
        raise ValidationError(
            {"deleted_action_ids": "An action cannot be kept and deleted together."}
        )
    if normalized_deleted_ids:
        PostSubmissionAction.objects.filter(
            form_definition=form_definition,
            id__in=normalized_deleted_ids,
        ).delete()
    workflow_data.pop("deleted_action_ids", None)
    workflow.visual_workflow_data = workflow_data
    workflow.save(update_fields=["visual_workflow_data"])

    # ── Sub-workflow definitions ────────────────────────────────────────
    if len(sub_workflow_nodes) > 1:
        raise ValidationError(
            {
                "sub_workflow_nodes": (
                    "Only one sub-workflow node is allowed per workflow graph."
                )
            }
        )

    if sub_workflow_nodes:
        # We only support one sub-workflow config per parent workflow (OneToOneField)
        sw_node = sub_workflow_nodes[0]
        sw_data = sw_node.get("data", {})
        target_workflow_id = sw_data.get("sub_workflow_id")
        target_id_type = sw_data.get("sub_workflow_id_type", "workflow")

        if target_workflow_id:
            if isinstance(target_workflow_id, bool):
                raise ValidationError(
                    {"sub_workflow_id": "Target ID must be a positive integer."}
                )
            if isinstance(target_workflow_id, int):
                target_workflow_pk = target_workflow_id
            elif (
                isinstance(target_workflow_id, str)
                and target_workflow_id.isascii()
                and target_workflow_id.isdigit()
            ):
                try:
                    target_workflow_pk = int(target_workflow_id)
                except ValueError as exc:
                    raise ValidationError(
                        {"sub_workflow_id": "Target ID must be a positive integer."}
                    ) from exc
            else:
                raise ValidationError(
                    {"sub_workflow_id": "Target ID must be a positive integer."}
                )
            if target_workflow_pk <= 0 or target_workflow_pk > 9223372036854775807:
                raise ValidationError(
                    {"sub_workflow_id": "Target ID must be a positive integer."}
                )
            if target_id_type == "workflow":
                target_workflow = WorkflowDefinition.objects.filter(
                    id=target_workflow_pk
                ).first()
            elif target_id_type == "form":
                target_workflow = (
                    WorkflowDefinition.objects.filter(
                        form_definition_id=target_workflow_pk
                    )
                    .order_by("id")
                    .first()
                )
            else:
                raise ValidationError(
                    {
                        "sub_workflow_id_type": (
                            "Invalid sub_workflow_id_type. "
                            "Expected 'workflow' or 'form'."
                        )
                    }
                )

            if not target_workflow:
                if target_id_type == "workflow":
                    raise ValidationError(
                        {
                            "sub_workflow_id": (
                                f"WorkflowDefinition with id '{target_workflow_id}' does not exist."
                            )
                        }
                    )
                raise ValidationError(
                    {
                        "sub_workflow_id": (
                            f"No workflow definition found for form_definition_id '{target_workflow_id}'."
                        )
                    }
                )

            sw_fields = {
                "sub_workflow": target_workflow,
                "section_label": sw_data.get("section_label", ""),
                "count_field": sw_data.get("count_field", ""),
                "label_template": sw_data.get("label_template", "Sub-workflow {index}"),
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
        # No sub-workflow node — remove any existing config
        SubWorkflowDefinition.objects.filter(parent_workflow=workflow).delete()

    return workflow
