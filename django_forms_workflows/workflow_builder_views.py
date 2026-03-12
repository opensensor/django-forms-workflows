"""
Visual Workflow Builder Views

API endpoints for the visual workflow builder interface.
"""

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import (
    FormDefinition,
    PostSubmissionAction,
    SubWorkflowDefinition,
    WorkflowDefinition,
    WorkflowStage,
)

logger = logging.getLogger(__name__)


@staff_member_required
@require_GET
def workflow_builder_view(request, form_id):
    """
    Main workflow builder page.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)

    # Get or create workflow
    workflow, created = WorkflowDefinition.objects.get_or_create(
        form_definition=form_definition, defaults={"requires_approval": False}
    )

    context = {
        "form_definition": form_definition,
        "form_id": form_id,
        "workflow_id": workflow.id,
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

    # Get workflow definition
    workflow = getattr(form_definition, "workflow", None)

    # Get form fields for condition/action configuration
    fields = []
    for field in form_definition.fields.all().order_by("order"):
        fields.append(
            {
                "field_name": field.field_name,
                "field_label": field.field_label,
                "field_type": field.field_type,
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

    # Get all available forms for multi-step workflows
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
        workflow_data = data.get("workflow", {})

        logger.info(f"Saving workflow for form {form_id}")
        logger.info(f"Workflow data: {workflow_data}")

        if not form_id:
            return JsonResponse(
                {"success": False, "error": "Form ID is required"}, status=400
            )

        form_definition = get_object_or_404(FormDefinition, id=form_id)

        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Convert visual workflow to model
            workflow = convert_visual_to_workflow(workflow_data, form_definition)
            logger.info(f"Workflow saved successfully: {workflow.id}")

        return JsonResponse(
            {
                "success": True,
                "message": "Workflow saved successfully",
            }
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception:
        logger.exception("Error saving workflow in builder")
        return JsonResponse(
            {"success": False, "error": "An internal error occurred."}, status=500
        )


def convert_workflow_to_visual(workflow, form_definition):
    """
    Convert WorkflowDefinition model to visual workflow format.

    Reads WorkflowStage records to build stage nodes.  Falls back to the
    deprecated flat approval_groups/approval_logic on WorkflowDefinition
    only when no stages exist.
    """
    # Check if visual workflow data exists AND has the correct format (nodes array)
    if workflow.visual_workflow_data:
        visual_data = workflow.visual_workflow_data
        # Check if it has the new format with nodes array
        if isinstance(visual_data, dict) and "nodes" in visual_data:
            logger.info("Loading saved visual workflow data (new format)")
            return visual_data
        else:
            # Old format (e.g., stages array) - regenerate
            logger.info(
                "Found legacy visual_workflow_data format, regenerating visual layout"
            )

    # Generate default layout from workflow configuration
    logger.info("Generating default visual workflow layout")
    nodes = []
    connections = []
    node_id_counter = 1

    # Layout configuration for better spacing
    horizontal_spacing = 280
    start_x = 120
    start_y = 200
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
            "requires_approval": workflow.requires_approval,
            "approval_deadline_days": workflow.approval_deadline_days,
            "send_reminder_after_days": workflow.send_reminder_after_days,
            "auto_approve_after_days": workflow.auto_approve_after_days,
            "notification_cadence": workflow.notification_cadence,
            "escalation_field": workflow.escalation_field or "",
            "escalation_threshold": str(workflow.escalation_threshold)
            if workflow.escalation_threshold is not None
            else "",
            "escalation_groups": [
                {"id": g.id, "name": g.name} for g in workflow.escalation_groups.all()
            ],
            "notify_on_submission": workflow.notify_on_submission,
            "notify_on_approval": workflow.notify_on_approval,
            "notify_on_rejection": workflow.notify_on_rejection,
            "notify_on_withdrawal": workflow.notify_on_withdrawal,
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

    if stages:
        from collections import OrderedDict

        order_groups: OrderedDict[int, list] = OrderedDict()
        for stage in stages:
            order_groups.setdefault(stage.order, []).append(stage)

        vertical_spacing = 120

        for _order_val, group in order_groups.items():
            if len(group) == 1:
                # Single stage at this order — render linearly
                stage = group[0]
                stage_groups = list(stage.approval_groups.all())
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
                        "approve_label": stage.approve_label or "",
                        "approval_groups": [
                            {"id": g.id, "name": g.name} for g in stage_groups
                        ],
                    },
                }
                nodes.append(stage_node)
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
                    stage_groups = list(stage.approval_groups.all())
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
                            "approve_label": stage.approve_label or "",
                            "approval_groups": [
                                {"id": g.id, "name": g.name} for g in stage_groups
                            ],
                        },
                    }
                    nodes.append(stage_node)
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
    else:
        # Legacy flat fallback — represent as a single stage node
        flat_groups = list(workflow.approval_groups.all())
        has_manager = workflow.requires_manager_approval
        has_groups = len(flat_groups) > 0

        if has_manager or has_groups:
            stage_node = {
                "id": f"node_{node_id_counter}",
                "type": "stage",
                "x": current_x,
                "y": current_y,
                "data": {
                    "stage_id": None,
                    "name": "Approval",
                    "order": 1,
                    "approval_logic": workflow.approval_logic if has_groups else "any",
                    "requires_manager_approval": has_manager,
                    "approve_label": "",
                    "approval_groups": [
                        {"id": g.id, "name": g.name} for g in flat_groups
                    ],
                },
            }
            nodes.append(stage_node)
            connections.append({"from": last_node_id, "to": stage_node["id"]})
            last_node_id = stage_node["id"]
            node_id_counter += 1
            current_x += horizontal_spacing

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
                    "to": "",
                    "subject": "",
                    "template": "",
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
                "sub_workflow_id": sub_wf.form_definition_id,
                "sub_workflow_name": sub_wf.form_definition.name,
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


def convert_visual_to_workflow(workflow_data, form_definition):
    """
    Convert visual workflow format to WorkflowDefinition model.

    Stage nodes are persisted as WorkflowStage records.  The deprecated
    flat ``approval_groups`` / ``approval_logic`` fields on
    WorkflowDefinition are left unchanged (they are ignored when stages
    exist).
    """

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
        # Legacy approval_config node — treat as a single stage
        elif node_type == "approval_config":
            data = node.get("data", {})
            approval_groups = data.get("approval_groups", [])
            has_manager = data.get("requires_manager_approval", False)
            if approval_groups or has_manager:
                stage_nodes.append(
                    {
                        "type": "stage",
                        "data": {
                            "stage_id": None,
                            "name": "Approval",
                            "order": 1,
                            "approval_logic": data.get("approval_logic", "any"),
                            "requires_manager_approval": has_manager,
                            "approve_label": "",
                            "approval_groups": approval_groups,
                        },
                    }
                )

    requires_approval = len(stage_nodes) > 0

    # ── Workflow-level settings ──────────────────────────────────────────
    wf_defaults = {
        "requires_approval": settings_data.get("requires_approval", requires_approval),
        "visual_workflow_data": workflow_data,
        "notify_on_submission": settings_data.get("notify_on_submission", True),
        "notify_on_approval": settings_data.get("notify_on_approval", True),
        "notify_on_rejection": settings_data.get("notify_on_rejection", True),
        "notify_on_withdrawal": settings_data.get("notify_on_withdrawal", True),
        "notification_cadence": settings_data.get("notification_cadence", "immediate"),
        "escalation_field": settings_data.get("escalation_field", ""),
    }

    # Optional numeric fields
    for key in (
        "approval_deadline_days",
        "send_reminder_after_days",
        "auto_approve_after_days",
    ):
        raw = settings_data.get(key)
        wf_defaults[key] = int(raw) if raw not in (None, "") else None

    raw_threshold = settings_data.get("escalation_threshold")
    if raw_threshold not in (None, ""):
        from decimal import Decimal, InvalidOperation

        try:
            wf_defaults["escalation_threshold"] = Decimal(raw_threshold)
        except (InvalidOperation, ValueError):
            wf_defaults["escalation_threshold"] = None
    else:
        wf_defaults["escalation_threshold"] = None

    workflow, _created = WorkflowDefinition.objects.update_or_create(
        form_definition=form_definition,
        defaults=wf_defaults,
    )

    # Escalation groups
    esc_ids = [g["id"] for g in settings_data.get("escalation_groups", [])]
    if esc_ids:
        workflow.escalation_groups.set(esc_ids)
    else:
        workflow.escalation_groups.clear()

    # ── Persist stages ──────────────────────────────────────────────────
    existing_stage_ids = set(workflow.stages.values_list("id", flat=True))
    kept_stage_ids = set()

    for idx, snode in enumerate(stage_nodes, start=1):
        sdata = snode.get("data", {})
        stage_id = sdata.get("stage_id")
        group_ids = [g["id"] for g in sdata.get("approval_groups", [])]

        stage_fields = {
            "name": sdata.get("name", f"Stage {idx}"),
            "order": sdata.get("order", idx),
            "approval_logic": sdata.get("approval_logic", "all"),
            "requires_manager_approval": sdata.get("requires_manager_approval", False),
            "approve_label": sdata.get("approve_label", ""),
        }

        if stage_id and stage_id in existing_stage_ids:
            WorkflowStage.objects.filter(id=stage_id).update(**stage_fields)
            stage = WorkflowStage.objects.get(id=stage_id)
            kept_stage_ids.add(stage_id)
        else:
            stage = WorkflowStage.objects.create(workflow=workflow, **stage_fields)
            kept_stage_ids.add(stage.id)

        stage.approval_groups.set(group_ids)

    # Delete stages that were removed in the builder
    workflow.stages.exclude(id__in=kept_stage_ids).delete()

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
            "description": f"Email to: {data.get('to', '')}, Subject: {data.get('subject', '')}",
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
        sub_wf_form_id = sw_data.get("sub_workflow_id")

        if sub_wf_form_id:
            # Look up the target workflow definition by form_definition_id
            try:
                target_workflow = WorkflowDefinition.objects.get(
                    form_definition_id=sub_wf_form_id
                )
            except WorkflowDefinition.DoesNotExist:
                target_workflow = None

            if target_workflow:
                sw_fields = {
                    "sub_workflow": target_workflow,
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
                    f"Sub-workflow target form {sub_wf_form_id} has no workflow definition"
                )
    else:
        # No sub-workflow node — remove any existing config
        SubWorkflowDefinition.objects.filter(parent_workflow=workflow).delete()

    return workflow
