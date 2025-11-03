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

from .models import FormDefinition, PostSubmissionAction, WorkflowDefinition

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
    except Exception as e:
        logger.exception("Error saving workflow in builder")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def convert_workflow_to_visual(workflow, form_definition):
    """
    Convert WorkflowDefinition model to visual workflow format.
    """
    # If visual workflow data exists, return it directly
    if workflow.visual_workflow_data:
        logger.info("Loading saved visual workflow data")
        return workflow.visual_workflow_data

    # Otherwise, generate default layout from workflow configuration
    logger.info("Generating default visual workflow layout")
    nodes = []
    connections = []
    node_id_counter = 1

    # Layout configuration for better spacing
    horizontal_spacing = 280  # Increased from 200 for better readability
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

    # Build form builder URL
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
            "is_initial": True,  # Mark as the initial form node (not deletable)
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
                for field in form_fields[:10]  # Limit to first 10 for performance
            ],
            "has_more_fields": len(form_fields) > 10,
        },
    }
    nodes.append(form_node)
    connections.append(
        {
            "from": last_node_id,
            "to": form_node["id"],
        }
    )
    last_node_id = form_node["id"]
    node_id_counter += 1
    current_x += horizontal_spacing

    # Approval configuration node (always present - shows approval requirements)
    approval_groups = list(workflow.approval_groups.all())
    has_manager_approval = workflow.requires_manager_approval
    has_group_approvals = len(approval_groups) > 0
    is_implicit_approval = not has_manager_approval and not has_group_approvals

    approval_config_node = {
        "id": f"node_{node_id_counter}",
        "type": "approval_config",
        "x": current_x,
        "y": current_y,
        "data": {
            "is_implicit": is_implicit_approval,
            "requires_manager_approval": has_manager_approval,
            "approval_groups": [
                {
                    "id": group.id,
                    "name": group.name,
                }
                for group in approval_groups
            ],
            "approval_logic": workflow.approval_logic if has_group_approvals else None,
        },
    }
    nodes.append(approval_config_node)
    connections.append(
        {
            "from": last_node_id,
            "to": approval_config_node["id"],
        }
    )
    last_node_id = approval_config_node["id"]
    node_id_counter += 1
    current_x += horizontal_spacing

    # Manager approval node (if enabled)
    if workflow.requires_manager_approval:
        manager_node = {
            "id": f"node_{node_id_counter}",
            "type": "approval",
            "x": current_x,
            "y": current_y,
            "data": {
                "approval_type": "manager",
                "step_name": "Manager Approval",
            },
        }
        nodes.append(manager_node)
        connections.append(
            {
                "from": last_node_id,
                "to": manager_node["id"],
            }
        )
        last_node_id = manager_node["id"]
        node_id_counter += 1
        current_x += horizontal_spacing

    # Group approval nodes (already fetched above)
    if approval_groups:
        if workflow.approval_logic == "sequence":
            # Sequential nodes - horizontal flow
            for group in approval_groups:
                group_node = {
                    "id": f"node_{node_id_counter}",
                    "type": "approval",
                    "x": current_x,
                    "y": current_y,
                    "data": {
                        "approval_type": "group",
                        "group_id": group.id,
                        "group_name": group.name,
                        "step_name": f"{group.name} Approval",
                    },
                }
                nodes.append(group_node)
                connections.append(
                    {
                        "from": last_node_id,
                        "to": group_node["id"],
                    }
                )
                last_node_id = group_node["id"]
                node_id_counter += 1
                current_x += horizontal_spacing
        else:
            # Parallel nodes (all/any)
            parallel_node = {
                "id": f"node_{node_id_counter}",
                "type": "approval",
                "x": current_x,
                "y": current_y,
                "data": {
                    "approval_type": "parallel",
                    "logic": workflow.approval_logic,
                    "groups": [{"id": g.id, "name": g.name} for g in approval_groups],
                    "step_name": f"Parallel Approval ({workflow.approval_logic.upper()})",
                },
            }
            nodes.append(parallel_node)
            connections.append(
                {
                    "from": last_node_id,
                    "to": parallel_node["id"],
                }
            )
            last_node_id = parallel_node["id"]
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
    """

    nodes = workflow_data.get("nodes", [])

    # Extract workflow configuration from nodes
    requires_approval = False
    requires_manager_approval = False
    approval_groups = []
    approval_logic = "any"
    action_nodes = []
    email_nodes = []

    for node in nodes:
        if node["type"] == "approval_config":
            # Extract approval configuration from the approval_config node
            data = node.get("data", {})
            requires_manager_approval = data.get("requires_manager_approval", False)
            approval_groups_data = data.get("approval_groups", [])
            approval_logic = data.get("approval_logic", "any")

            # Extract group IDs
            for group_data in approval_groups_data:
                approval_groups.append(group_data["id"])

            # Set requires_approval if any approval is configured
            requires_approval = requires_manager_approval or len(approval_groups) > 0

        elif node["type"] == "approval":
            requires_approval = True
            data = node.get("data", {})

            if data.get("approval_type") == "manager":
                requires_manager_approval = True
            elif data.get("approval_type") == "group":
                group_id = data.get("group_id")
                if group_id:
                    approval_groups.append(group_id)
            elif data.get("approval_type") == "parallel":
                approval_logic = data.get("logic", "any")
                for group_data in data.get("groups", []):
                    approval_groups.append(group_data["id"])

        elif node["type"] == "action":
            action_nodes.append(node)

        elif node["type"] == "email":
            email_nodes.append(node)

    # Create or update workflow
    workflow, created = WorkflowDefinition.objects.update_or_create(
        form_definition=form_definition,
        defaults={
            "requires_approval": requires_approval,
            "requires_manager_approval": requires_manager_approval,
            "approval_logic": approval_logic,
            "visual_workflow_data": workflow_data,  # Store the visual layout
        },
    )

    # Update approval groups
    if approval_groups:
        workflow.approval_groups.set(approval_groups)
    else:
        workflow.approval_groups.clear()

    # Handle post-submission actions - clear existing and recreate
    # Get existing actions to preserve IDs where possible
    existing_actions = {
        action.name: action for action in form_definition.post_actions.all()
    }

    # Track which actions we're keeping
    actions_to_keep = []

    # Create/update action nodes
    for node in action_nodes:
        data = node.get("data", {})
        action_name = data.get("name", "Unnamed Action")
        action_type = data.get("action_type", "database")

        # Parse config JSON if it's a string
        config = data.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        # Prepare action data based on action type
        action_data = {
            "action_type": action_type,
            "trigger": data.get("trigger", "on_approve"),
        }

        # Set the appropriate field mapping based on action type
        if action_type == "database":
            # Handle new structured config format
            action_data["db_alias"] = config.get("db_alias", "")
            action_data["db_schema"] = config.get("db_schema", "")
            action_data["db_table"] = config.get("db_table", "")
            action_data["db_lookup_field"] = config.get("db_lookup_field", "ID_NUMBER")
            action_data["db_user_field"] = config.get("db_user_field", "employee_id")
            action_data["db_field_mappings"] = config.get(
                "field_mappings", config if isinstance(config, list) else []
            )
        elif action_type == "ldap":
            # Handle new structured config format
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

        # Update existing or create new
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

    # Create/update email nodes as actions
    for node in email_nodes:
        data = node.get("data", {})
        action_name = data.get("name", "Email Notification")

        # Note: Email actions don't have dedicated fields in PostSubmissionAction yet
        # For now, we just create the action with basic info
        # TODO: Add email-specific fields to PostSubmissionAction model

        action_data = {
            "action_type": "email",
            "trigger": data.get("trigger", "on_approve"),
            "description": f"Email to: {data.get('to', '')}, Subject: {data.get('subject', '')}",
        }

        # Update existing or create new
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

    # Delete actions that are no longer in the workflow
    form_definition.post_actions.exclude(id__in=actions_to_keep).delete()

    return workflow
