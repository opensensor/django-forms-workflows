"""
Tests for the form builder and workflow builder admin views.
"""

import json
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from django_forms_workflows.form_builder_views import (
    FormBuilderPayloadError,
    save_form_definition_from_builder_data,
)
from django_forms_workflows.models import (
    FormDefinition,
    FormField,
    NotificationRule,
    PostSubmissionAction,
    SharedOptionList,
    StageApprovalGroup,
    SubWorkflowDefinition,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.workflow_builder_views import (
    convert_visual_to_workflow,
    convert_workflow_to_visual,
)

# ── Admin URL helpers ────────────────────────────────────────────────────────
# Builder URLs are registered via FormDefinitionAdmin.get_urls(), so they live
# under /admin/django_forms_workflows/formdefinition/<path>/.

_ADMIN_PREFIX = "/admin/django_forms_workflows/formdefinition"


def _fb_url(path):
    return f"{_ADMIN_PREFIX}/{path}"


def _wf_url(path):
    return f"{_ADMIN_PREFIX}/{path}"


pytestmark = pytest.mark.django_db


# ── convert_workflow_to_visual ───────────────────────────────────────────────


class TestConvertWorkflowToVisual:
    """Tests for converting WorkflowDefinition → visual node graph."""

    def test_returns_saved_visual_data_if_present(self, workflow, form_definition):
        """When visual_workflow_data already has nodes, return it as-is."""
        saved = {"nodes": [{"id": "n1", "type": "start"}], "connections": []}
        workflow.visual_workflow_data = saved
        workflow.save()

        result = convert_workflow_to_visual(workflow, form_definition)
        assert result == saved

    def test_generates_layout_with_stages(
        self, staged_workflow, form_definition, approval_group, second_approval_group
    ):
        """Staged workflow generates stage nodes (not legacy approval_config)."""
        first_stage = staged_workflow.stages.order_by("order").first()
        first_stage.allow_send_back = True
        first_stage.save(update_fields=["allow_send_back"])

        result = convert_workflow_to_visual(staged_workflow, form_definition)
        types = [n["type"] for n in result["nodes"]]

        assert "start" in types
        assert "form" in types
        assert "workflow_settings" in types
        assert "stage" in types
        assert "end" in types
        # Should NOT contain legacy approval_config or approval nodes
        assert "approval_config" not in types

        stage_nodes = [n for n in result["nodes"] if n["type"] == "stage"]
        assert len(stage_nodes) == 2
        assert stage_nodes[0]["data"]["name"] == "Manager Review"
        assert stage_nodes[1]["data"]["name"] == "Finance Review"
        assert stage_nodes[0]["data"]["allow_send_back"] is True

    def test_generated_layout_uses_wider_spacing(
        self, staged_workflow, form_definition
    ):
        """Generated nodes should have enough horizontal room for the builder cards."""
        result = convert_workflow_to_visual(staged_workflow, form_definition)

        same_lane_nodes = sorted(
            [node for node in result["nodes"] if node["y"] == 220],
            key=lambda node: node["x"],
        )

        x_positions = [node["x"] for node in same_lane_nodes]
        assert x_positions[:3] == [120, 500, 880]
        assert all(
            later - earlier >= 380
            for earlier, later in zip(x_positions, x_positions[1:], strict=False)
        )

    def test_parallel_stages_share_a_clean_aligned_column(
        self, form_definition, approval_group, second_approval_group
    ):
        workflow = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        first = workflow.stages.create(
            name="Manager Review", order=1, approval_logic="all"
        )
        first.approval_groups.add(approval_group)
        second = workflow.stages.create(
            name="Finance Review", order=1, approval_logic="all"
        )
        second.approval_groups.add(second_approval_group)

        result = convert_workflow_to_visual(workflow, form_definition)

        stage_nodes = sorted(
            [node for node in result["nodes"] if node["type"] == "stage"],
            key=lambda node: node["y"],
        )
        join_node = next(node for node in result["nodes"] if node["type"] == "join")

        assert len(stage_nodes) == 2
        assert stage_nodes[0]["x"] == stage_nodes[1]["x"]
        assert stage_nodes[1]["y"] - stage_nodes[0]["y"] == 220
        assert join_node["y"] == 220

    def test_backfills_send_back_flag_from_saved_visual_data(
        self, staged_workflow, form_definition
    ):
        stage = staged_workflow.stages.order_by("order").first()
        stage.allow_send_back = True
        stage.save(update_fields=["allow_send_back"])
        staged_workflow.visual_workflow_data = {
            "nodes": [
                {
                    "id": "node_1",
                    "type": "stage",
                    "data": {
                        "stage_id": stage.id,
                        "name": stage.name,
                        "order": stage.order,
                    },
                }
            ],
            "connections": [],
        }
        staged_workflow.save(update_fields=["visual_workflow_data"])

        result = convert_workflow_to_visual(staged_workflow, form_definition)

        assert result["nodes"][0]["data"]["allow_send_back"] is True

    def test_backfills_advanced_stage_fields_from_saved_visual_data(
        self, staged_workflow, form_definition
    ):
        stage = staged_workflow.stages.order_by("order").first()
        stage.allow_reassign = True
        stage.allow_edit_form_data = True
        stage.assignee_form_field = "manager_email"
        stage.assignee_lookup_type = "email"
        stage.validate_assignee_group = False
        stage.save(
            update_fields=[
                "allow_reassign",
                "allow_edit_form_data",
                "assignee_form_field",
                "assignee_lookup_type",
                "validate_assignee_group",
            ]
        )
        staged_workflow.visual_workflow_data = {
            "nodes": [
                {
                    "id": "node_1",
                    "type": "stage",
                    "data": {
                        "stage_id": stage.id,
                        "name": stage.name,
                        "order": stage.order,
                    },
                }
            ],
            "connections": [],
        }
        staged_workflow.save(update_fields=["visual_workflow_data"])

        result = convert_workflow_to_visual(staged_workflow, form_definition)

        assert result["nodes"][0]["data"]["allow_reassign"] is True
        assert result["nodes"][0]["data"]["allow_edit_form_data"] is True
        assert result["nodes"][0]["data"]["assignee_form_field"] == "manager_email"
        assert result["nodes"][0]["data"]["assignee_lookup_type"] == "email"
        assert result["nodes"][0]["data"]["validate_assignee_group"] is False

    def test_workflow_with_no_stages_has_no_stage_nodes(self, form_definition, db):
        """Workflow without stages produces no stage nodes."""
        flat_wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        result = convert_workflow_to_visual(flat_wf, form_definition)

        stage_nodes = [n for n in result["nodes"] if n["type"] == "stage"]
        assert len(stage_nodes) == 0

    def test_workflow_settings_node_populated(self, staged_workflow, form_definition):
        staged_workflow.name_label = "Finance Approval"
        staged_workflow.approval_deadline_days = 7
        staged_workflow.notification_cadence = "form_field_date"
        staged_workflow.notification_cadence_form_field = "review_date"
        staged_workflow.trigger_conditions = {
            "operator": "AND",
            "conditions": [
                {"field": "department", "operator": "equals", "value": "finance"}
            ],
        }
        staged_workflow.save()

        result = convert_workflow_to_visual(staged_workflow, form_definition)
        ws = next(n for n in result["nodes"] if n["type"] == "workflow_settings")
        assert ws["data"]["name_label"] == "Finance Approval"
        assert ws["data"]["approval_deadline_days"] == 7
        assert ws["data"]["notification_cadence"] == "form_field_date"
        assert ws["data"]["notification_cadence_form_field"] == "review_date"
        assert (
            ws["data"]["trigger_conditions"]["conditions"][0]["field"] == "department"
        )

    def test_backfills_stage_trigger_conditions_from_saved_visual_data(
        self, staged_workflow, form_definition
    ):
        stage = staged_workflow.stages.order_by("order").first()
        stage.trigger_conditions = {
            "operator": "OR",
            "conditions": [{"field": "amount", "operator": "gt", "value": "1000"}],
        }
        stage.save(update_fields=["trigger_conditions"])
        staged_workflow.visual_workflow_data = {
            "nodes": [
                {
                    "id": "node_1",
                    "type": "stage",
                    "data": {
                        "stage_id": stage.id,
                        "name": stage.name,
                        "order": stage.order,
                    },
                }
            ],
            "connections": [],
        }
        staged_workflow.save(update_fields=["visual_workflow_data"])

        result = convert_workflow_to_visual(staged_workflow, form_definition)

        assert result["nodes"][0]["data"]["trigger_conditions"] == {
            "operator": "OR",
            "conditions": [{"field": "amount", "operator": "gt", "value": "1000"}],
        }

    def test_backfills_stage_approval_fields_from_saved_visual_data(
        self, form_with_fields, approval_group
    ):
        workflow = WorkflowDefinition.objects.create(
            form_definition=form_with_fields,
            requires_approval=True,
        )
        stage = workflow.stages.create(name="Review", order=1, approval_logic="all")
        stage.approval_groups.add(approval_group)
        target_field = form_with_fields.fields.get(field_name="notes")
        target_field.workflow_stage = stage
        target_field.save(update_fields=["workflow_stage"])
        workflow.visual_workflow_data = {
            "nodes": [
                {
                    "id": "node_1",
                    "type": "stage",
                    "data": {
                        "stage_id": stage.id,
                        "name": stage.name,
                        "order": stage.order,
                    },
                }
            ],
            "connections": [],
        }
        workflow.save(update_fields=["visual_workflow_data"])

        result = convert_workflow_to_visual(workflow, form_with_fields)

        approval_fields = result["nodes"][0]["data"]["approval_fields"]
        assert [field["field_name"] for field in approval_fields] == ["notes"]

    def test_loads_email_action_configuration_into_visual_data(
        self, form_definition, post_action_email
    ):
        workflow = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=False,
        )

        result = convert_workflow_to_visual(workflow, form_definition)

        email_node = next(n for n in result["nodes"] if n["type"] == "email")
        assert email_node["data"]["email_to"] == "admin@example.com"
        assert (
            email_node["data"]["email_subject_template"] == "Form {form_name} approved"
        )

    def test_loads_notification_rules_into_workflow_settings(
        self, staged_workflow, approval_group, second_approval_group, form_definition
    ):
        stage = staged_workflow.stages.order_by("order").first()
        rule = NotificationRule.objects.create(
            workflow=staged_workflow,
            stage=stage,
            event="approval_request",
            subject_template="Approval Needed: {form_name}",
            notify_submitter=True,
            email_field="manager_email",
            static_emails="ops@example.com",
            notify_stage_assignees=True,
            notify_stage_groups=True,
            conditions={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "department",
                        "operator": "equals",
                        "value": "finance",
                    }
                ],
            },
        )
        rule.notify_groups.set([approval_group, second_approval_group])

        result = convert_workflow_to_visual(staged_workflow, form_definition)

        settings_node = next(
            n for n in result["nodes"] if n["type"] == "workflow_settings"
        )
        assert len(settings_node["data"]["notification_rules"]) == 1
        loaded_rule = settings_node["data"]["notification_rules"][0]
        assert loaded_rule["stage_id"] == stage.id
        assert loaded_rule["stage_node_id"]
        assert loaded_rule["email_field"] == "manager_email"
        assert loaded_rule["notify_stage_groups"] is True
        assert {group["id"] for group in loaded_rule["notify_groups"]} == {
            approval_group.id,
            second_approval_group.id,
        }

    def test_loads_stage_approval_group_positions(
        self, staged_workflow, form_definition
    ):
        stage = staged_workflow.stages.order_by("order").first()
        StageApprovalGroup.objects.filter(stage=stage).update(position=3)

        result = convert_workflow_to_visual(staged_workflow, form_definition)

        stage_node = next(
            node
            for node in result["nodes"]
            if node["type"] == "stage" and node["data"]["stage_id"] == stage.id
        )
        assert stage_node["data"]["approval_groups"][0]["position"] == 3


# ── convert_visual_to_workflow ───────────────────────────────────────────────


class TestConvertVisualToWorkflow:
    """Tests for converting visual node graph → WorkflowDefinition + stages."""

    def _make_visual(self, stages=None, settings=None, actions=None):
        nodes = [{"type": "start", "data": {}}]
        if settings:
            nodes.append({"type": "workflow_settings", "data": settings})
        for s in stages or []:
            nodes.append({"type": "stage", "data": s})
        for a in actions or []:
            nodes.append({"type": "action", "data": a})
        nodes.append({"type": "end", "data": {}})
        return {"nodes": nodes, "connections": []}

    def test_creates_stages(
        self, form_with_fields, approval_group, second_approval_group
    ):
        visual = self._make_visual(
            stages=[
                {
                    "stage_id": None,
                    "name": "Review",
                    "order": 1,
                    "approval_logic": "all",
                    "requires_manager_approval": True,
                    "allow_send_back": True,
                    "allow_reassign": True,
                    "allow_edit_form_data": True,
                    "approve_label": "Sign Off",
                    "assignee_form_field": "email",
                    "assignee_lookup_type": "email",
                    "validate_assignee_group": False,
                    "trigger_conditions": {
                        "operator": "AND",
                        "conditions": [
                            {
                                "field": "department",
                                "operator": "equals",
                                "value": "finance",
                            }
                        ],
                    },
                    "approval_groups": [
                        {
                            "id": second_approval_group.id,
                            "name": second_approval_group.name,
                            "position": 0,
                        },
                        {
                            "id": approval_group.id,
                            "name": approval_group.name,
                            "position": 1,
                        },
                    ],
                }
            ]
        )
        wf = convert_visual_to_workflow(visual, form_with_fields)
        assert wf.requires_approval is True
        stages = list(wf.stages.order_by("order"))
        assert len(stages) == 1
        assert stages[0].name == "Review"
        assert stages[0].approval_logic == "all"
        assert stages[0].requires_manager_approval is True
        assert stages[0].allow_send_back is True
        assert stages[0].allow_reassign is True
        assert stages[0].allow_edit_form_data is True
        assert stages[0].approve_label == "Sign Off"
        assert stages[0].assignee_form_field == "email"
        assert stages[0].assignee_lookup_type == "email"
        assert stages[0].validate_assignee_group is False
        assert stages[0].trigger_conditions == {
            "operator": "AND",
            "conditions": [
                {
                    "field": "department",
                    "operator": "equals",
                    "value": "finance",
                }
            ],
        }
        assert list(
            StageApprovalGroup.objects.filter(stage=stages[0])
            .order_by("position")
            .values_list("group_id", flat=True)
        ) == [second_approval_group.id, approval_group.id]

    def test_updates_existing_stages(
        self, staged_workflow, form_definition, approval_group
    ):
        existing_stages = list(staged_workflow.stages.order_by("order"))
        stage1_id = existing_stages[0].id

        visual = self._make_visual(
            stages=[
                {
                    "stage_id": stage1_id,
                    "name": "Renamed",
                    "order": 1,
                    "approval_logic": "any",
                    "requires_manager_approval": False,
                    "approve_label": "",
                    "approval_groups": [
                        {
                            "id": approval_group.id,
                            "name": approval_group.name,
                            "position": 0,
                        }
                    ],
                }
            ]
        )
        wf = convert_visual_to_workflow(visual, form_definition)
        remaining = list(wf.stages.order_by("order"))
        assert len(remaining) == 1
        assert remaining[0].id == stage1_id
        assert remaining[0].name == "Renamed"
        assert remaining[0].approval_logic == "any"
        assert remaining[0].requires_manager_approval is False
        assert remaining[0].approve_label == ""
        stage_groups = list(
            StageApprovalGroup.objects.filter(stage=remaining[0]).order_by("position")
        )
        assert len(stage_groups) == 1
        assert stage_groups[0].group_id == approval_group.id
        assert stage_groups[0].position == 0

    def test_deletes_removed_stages(
        self, staged_workflow, form_definition, approval_group
    ):
        """Stages absent from the visual data are deleted."""
        assert staged_workflow.stages.count() == 2
        visual = self._make_visual(stages=[])
        wf = convert_visual_to_workflow(visual, form_definition)
        assert wf.stages.count() == 0

    def test_saves_workflow_settings(self, form_with_fields):
        visual = self._make_visual(
            settings={
                "name_label": "Finance Approval",
                "requires_approval": True,
                "approval_deadline_days": 14,
                "send_reminder_after_days": 3,
                "auto_approve_after_days": "",
                "notification_cadence": "monthly",
                "notification_cadence_day": 15,
                "notification_cadence_time": "08:30",
                "notification_cadence_form_field": "reminder_date",
                "trigger_conditions": {
                    "operator": "OR",
                    "conditions": [
                        {
                            "field": "department",
                            "operator": "equals",
                            "value": "finance",
                        },
                        {"field": "amount", "operator": "gt", "value": "1000"},
                    ],
                },
                "notification_rules": [
                    {
                        "event": "approval_request",
                        "subject_template": "Approval Needed",
                        "notify_submitter": True,
                        "email_field": "email",
                        "static_emails": "ops@example.com",
                        "notify_stage_assignees": False,
                        "notify_stage_groups": False,
                        "notify_groups": [],
                        "conditions": {
                            "operator": "AND",
                            "conditions": [
                                {
                                    "field": "department",
                                    "operator": "equals",
                                    "value": "finance",
                                }
                            ],
                        },
                    }
                ],
            }
        )
        wf = convert_visual_to_workflow(visual, form_with_fields)
        assert wf.name_label == "Finance Approval"
        assert wf.approval_deadline_days == 14
        assert wf.send_reminder_after_days == 3
        assert wf.auto_approve_after_days is None
        assert wf.notification_cadence == "monthly"
        assert wf.notification_cadence_day == 15
        assert wf.notification_cadence_time.strftime("%H:%M") == "08:30"
        assert wf.notification_cadence_form_field == "reminder_date"
        assert wf.trigger_conditions == {
            "operator": "OR",
            "conditions": [
                {
                    "field": "department",
                    "operator": "equals",
                    "value": "finance",
                },
                {"field": "amount", "operator": "gt", "value": "1000"},
            ],
        }
        rule = wf.notification_rules.get()
        assert rule.event == "approval_request"
        assert rule.notify_submitter is True
        assert rule.email_field == "email"
        assert rule.static_emails == "ops@example.com"
        assert rule.conditions == {
            "operator": "AND",
            "conditions": [
                {
                    "field": "department",
                    "operator": "equals",
                    "value": "finance",
                }
            ],
        }

    def test_updates_specific_workflow_when_passed(self, form_definition):
        first = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        second = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )

        convert_visual_to_workflow(
            self._make_visual(settings={"name_label": "Updated Track B"}),
            form_definition,
            workflow=second,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.name_label == "Track A"
        assert second.name_label == "Updated Track B"

    def test_creates_stage_scoped_notification_rule(
        self, form_definition, approval_group
    ):
        visual = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {
                    "id": "settings_1",
                    "type": "workflow_settings",
                    "data": {
                        "notification_rules": [
                            {
                                "stage_node_id": "stage_1",
                                "event": "approval_request",
                                "subject_template": "Stage approval needed",
                                "notify_stage_assignees": True,
                                "notify_stage_groups": True,
                                "notify_groups": [
                                    {
                                        "id": approval_group.id,
                                        "name": approval_group.name,
                                    }
                                ],
                                "conditions": {
                                    "operator": "AND",
                                    "conditions": [
                                        {
                                            "field": "amount",
                                            "operator": "gt",
                                            "value": "500",
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "id": "stage_1",
                    "type": "stage",
                    "data": {
                        "name": "Review",
                        "order": 1,
                        "approval_logic": "all",
                        "approval_groups": [
                            {
                                "id": approval_group.id,
                                "name": approval_group.name,
                                "position": 0,
                            }
                        ],
                    },
                },
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "connections": [],
        }

        wf = convert_visual_to_workflow(visual, form_definition)

        rule = wf.notification_rules.get()
        stage = wf.stages.get()
        assert rule.stage_id == stage.id
        assert rule.notify_stage_assignees is True
        assert rule.notify_stage_groups is True
        assert list(rule.notify_groups.values_list("id", flat=True)) == [
            approval_group.id
        ]
        assert rule.conditions == {
            "operator": "AND",
            "conditions": [{"field": "amount", "operator": "gt", "value": "500"}],
        }

    def test_creates_stage_approval_fields(self, form_with_fields, approval_group):
        field_email = form_with_fields.fields.get(field_name="email")
        field_notes = form_with_fields.fields.get(field_name="notes")
        visual = self._make_visual(
            stages=[
                {
                    "name": "Review",
                    "order": 1,
                    "approval_logic": "all",
                    "approval_groups": [
                        {
                            "id": approval_group.id,
                            "name": approval_group.name,
                            "position": 0,
                        }
                    ],
                    "approval_fields": [
                        {
                            "id": field_email.id,
                            "field_name": field_email.field_name,
                            "field_label": field_email.field_label,
                        },
                        {
                            "id": field_notes.id,
                            "field_name": field_notes.field_name,
                            "field_label": field_notes.field_label,
                        },
                    ],
                }
            ]
        )

        wf = convert_visual_to_workflow(visual, form_with_fields)
        stage = wf.stages.get()
        field_email.refresh_from_db()
        field_notes.refresh_from_db()
        assert field_email.workflow_stage_id == stage.id
        assert field_notes.workflow_stage_id == stage.id
        assert list(
            stage.approval_fields.order_by("order").values_list("field_name", flat=True)
        ) == [
            "email",
            "notes",
        ]

    def test_clears_stage_approval_fields_when_removed(
        self, form_with_fields, approval_group
    ):
        workflow = WorkflowDefinition.objects.create(
            form_definition=form_with_fields,
            requires_approval=True,
        )
        stage = workflow.stages.create(name="Review", order=1, approval_logic="all")
        stage.approval_groups.add(approval_group)
        notes_field = form_with_fields.fields.get(field_name="notes")
        notes_field.workflow_stage = stage
        notes_field.save(update_fields=["workflow_stage"])

        convert_visual_to_workflow(
            self._make_visual(
                stages=[
                    {
                        "stage_id": stage.id,
                        "name": "Review",
                        "order": 1,
                        "approval_logic": "all",
                        "approval_groups": [
                            {
                                "id": approval_group.id,
                                "name": approval_group.name,
                                "position": 0,
                            }
                        ],
                        "approval_fields": [],
                    }
                ]
            ),
            form_with_fields,
            workflow=workflow,
        )

        notes_field.refresh_from_db()
        assert notes_field.workflow_stage is None

    def test_rejects_stage_without_approver_source(self, form_definition):
        visual = self._make_visual(
            stages=[
                {
                    "name": "Review",
                    "order": 1,
                    "approval_logic": "all",
                    "approval_groups": [],
                    "requires_manager_approval": False,
                    "assignee_form_field": "",
                }
            ]
        )

        with pytest.raises(ValidationError) as exc:
            convert_visual_to_workflow(visual, form_definition)

        assert "approver source" in str(exc.value)

    def test_saves_visual_workflow_data(self, form_definition):
        visual = self._make_visual()
        wf = convert_visual_to_workflow(visual, form_definition)
        assert wf.visual_workflow_data == visual

    def test_creates_actions(self, form_definition):
        visual = self._make_visual(
            actions=[
                {
                    "name": "Update DB",
                    "action_type": "database",
                    "trigger": "on_approve",
                    "config": {"db_alias": "default", "db_table": "users"},
                }
            ]
        )
        convert_visual_to_workflow(visual, form_definition)
        actions = list(form_definition.post_actions.all())
        assert len(actions) == 1
        assert actions[0].name == "Update DB"
        assert actions[0].action_type == "database"

    def test_inactive_action_round_trip_preserves_identity(self, form_definition):
        workflow = WorkflowDefinition.objects.create(form_definition=form_definition)
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Original",
            action_type="database",
            is_active=False,
        )
        visual = convert_workflow_to_visual(workflow, form_definition)
        action_node = next(node for node in visual["nodes"] if node["type"] == "action")
        assert action_node["data"]["action_id"] == action.id
        assert action_node["data"]["is_active"] is False
        action_node["data"]["name"] = "Renamed"

        convert_visual_to_workflow(visual, form_definition, workflow=workflow)

        action.refresh_from_db()
        assert action.name == "Renamed"
        assert action.is_active is False
        assert list(form_definition.post_actions.values_list("id", flat=True)) == [
            action.id
        ]

    def test_action_id_from_another_form_is_rejected(self, form_definition):
        other_form = FormDefinition.objects.create(name="Other", slug="other")
        foreign_action = PostSubmissionAction.objects.create(
            form_definition=other_form,
            name="Foreign",
            action_type="database",
        )
        visual = self._make_visual(
            actions=[
                {
                    "action_id": foreign_action.id,
                    "name": "Foreign",
                    "action_type": "database",
                    "config": {},
                }
            ]
        )

        with pytest.raises(ValidationError, match="does not belong"):
            convert_visual_to_workflow(visual, form_definition)
        assert not form_definition.post_actions.exists()

    def test_action_with_null_config_uses_empty_defaults(self, form_definition):
        visual = self._make_visual(
            actions=[
                {
                    "name": "Update DB",
                    "action_type": "database",
                    "config": None,
                }
            ]
        )

        convert_visual_to_workflow(visual, form_definition)

        assert form_definition.post_actions.get(name="Update DB").db_alias == ""

    @pytest.mark.parametrize("target_id_type", ["workflow", "form"])
    def test_sub_workflow_target_id_type(self, form_definition, target_id_type):
        target_form = FormDefinition.objects.create(
            name="Child Form", slug="child-form"
        )
        target_workflow = WorkflowDefinition.objects.create(form_definition=target_form)

        # Ensure IDs are distinct so this test really exercises sub_workflow_id_type.
        if target_form.id == target_workflow.id:
            FormDefinition.objects.create(name="ID spacer", slug="id-spacer")
            target_form = FormDefinition.objects.create(
                name="Child Form 2", slug="child-form-2"
            )
            target_workflow = WorkflowDefinition.objects.create(
                form_definition=target_form
            )

        assert target_form.id != target_workflow.id

        target_id = (
            target_workflow.id if target_id_type == "workflow" else target_form.id
        )
        visual = self._make_visual()
        visual["nodes"].insert(
            1,
            {
                "type": "sub_workflow",
                "data": {
                    "sub_workflow_id": target_id,
                    "sub_workflow_id_type": target_id_type,
                },
            },
        )

        workflow = convert_visual_to_workflow(visual, form_definition)

        assert (
            SubWorkflowDefinition.objects.get(parent_workflow=workflow).sub_workflow_id
            == target_workflow.id
        )

    def test_sub_workflow_rejects_malformed_target_id(self, form_definition):
        visual = self._make_visual()
        visual["nodes"].insert(
            1,
            {
                "type": "sub_workflow",
                "data": {"sub_workflow_id": "not-an-id"},
            },
        )

        with pytest.raises(ValidationError, match="positive integer"):
            convert_visual_to_workflow(visual, form_definition)

    def test_creates_email_actions_with_email_configuration(self, form_with_fields):
        visual = {
            "nodes": [
                {"type": "start", "data": {}},
                {
                    "type": "email",
                    "data": {
                        "name": "Notify Submitter",
                        "trigger": "on_submit",
                        "email_to": "ops@example.com",
                        "email_to_field": "email",
                        "email_cc": "manager@example.com",
                        "email_cc_field": "email",
                        "email_subject_template": "Submitted {form_name}",
                        "email_body_template": "Submission #{submission_id}",
                        "email_template_name": "emails/submission.html",
                    },
                },
                {"type": "end", "data": {}},
            ],
            "connections": [],
        }

        convert_visual_to_workflow(visual, form_with_fields)

        action = PostSubmissionAction.objects.get(name="Notify Submitter")
        assert action.action_type == "email"
        assert action.email_to == "ops@example.com"
        assert action.email_to_field == "email"
        assert action.email_cc == "manager@example.com"
        assert action.email_cc_field == "email"
        assert action.email_subject_template == "Submitted {form_name}"
        assert action.email_body_template == "Submission #{submission_id}"
        assert action.email_template_name == "emails/submission.html"


# ── Workflow builder view tests ──────────────────────────────────────────────


class TestWorkflowBuilderViews:
    """Integration tests for the workflow builder HTTP endpoints."""

    def test_builder_view_requires_staff(self, client, form_definition, user):
        client.force_login(user)
        url = _wf_url(f"{form_definition.id}/workflow/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_builder_view_accessible_to_superuser(
        self, client, form_definition, superuser
    ):
        client.login(username="admin", password="testpass123")
        url = _wf_url(f"{form_definition.id}/workflow/")
        resp = client.get(url)
        assert resp.status_code == 200

    def test_form_admin_change_template_has_analytics_shortcut(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "django_forms_workflows/templates/admin/django_forms_workflows/formdef_change_form.html"
        )

        content = template_path.read_text()

        assert "View Analytics" in content
        assert (
            "{% url 'forms_workflows:analytics_dashboard' %}?form={{ original.slug|urlencode }}"
            in content
        )

    def test_builder_view_selects_requested_workflow_track(
        self, client, superuser, form_definition
    ):
        WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        second = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )

        client.login(username="admin", password="testpass123")
        url = _wf_url(f"{form_definition.id}/workflow/?workflow_id={second.id}")
        resp = client.get(url)

        assert resp.status_code == 200
        assert resp.context["workflow_id"] == second.id
        assert any(
            track["id"] == second.id for track in resp.context["workflow_tracks"]
        )

    def test_load_returns_json(self, client, superuser, staged_workflow):
        client.login(username="admin", password="testpass123")
        fid = staged_workflow.form_definition.id
        url = _wf_url(f"workflow/api/load/{fid}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow" in data
        assert "nodes" in data["workflow"]

    def test_load_and_save_require_staff(self, client, user, form_definition):
        load_url = _wf_url(f"workflow/api/load/{form_definition.id}/")
        save_url = _wf_url("workflow/api/save/")
        payload = {"form_id": form_definition.id, "workflow": {"nodes": []}}

        assert client.get(load_url).status_code in (302, 403)
        assert client.post(
            save_url, data=json.dumps(payload), content_type="application/json"
        ).status_code in (302, 403)

        client.force_login(user)
        assert client.get(load_url).status_code in (302, 403)
        assert client.post(
            save_url, data=json.dumps(payload), content_type="application/json"
        ).status_code in (302, 403)
        assert not WorkflowDefinition.objects.filter(
            form_definition=form_definition
        ).exists()

    def test_load_returns_requested_workflow_track(
        self, client, superuser, form_definition
    ):
        first = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        second = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )
        first.stages.create(name="A Stage", order=1, approval_logic="all")
        second.stages.create(name="B Stage", order=1, approval_logic="all")

        client.login(username="admin", password="testpass123")
        url = _wf_url(
            f"workflow/api/load/{form_definition.id}/?workflow_id={second.id}"
        )
        resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        stage_names = [
            node["data"].get("name")
            for node in data["workflow"]["nodes"]
            if node["type"] == "stage"
        ]
        assert stage_names == ["B Stage"]
        assert data["workflow_id"] == second.id

    def test_save_creates_stages(
        self, client, superuser, form_definition, approval_group
    ):
        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_definition.id,
            "workflow": {
                "nodes": [
                    {"type": "start", "data": {}},
                    {
                        "type": "stage",
                        "data": {
                            "stage_id": None,
                            "name": "Sign Off",
                            "order": 1,
                            "approval_logic": "all",
                            "requires_manager_approval": False,
                            "allow_send_back": True,
                            "approve_label": "Confirm",
                            "approval_groups": [
                                {
                                    "id": approval_group.id,
                                    "name": approval_group.name,
                                }
                            ],
                        },
                    },
                    {"type": "end", "data": {}},
                ],
                "connections": [],
            },
        }
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        wf = WorkflowDefinition.objects.get(form_definition=form_definition)
        stages = list(wf.stages.order_by("order"))
        assert len(stages) == 1
        assert stages[0].name == "Sign Off"
        assert stages[0].allow_send_back is True
        assert wf.visual_workflow_data["nodes"][1]["data"]["stage_id"] == stages[0].id

    @pytest.mark.parametrize(
        "workflow_data",
        [
            None,
            {"nodes": None},
            {"nodes": [None]},
            {"nodes": [{"type": "start", "data": None}]},
        ],
    )
    def test_save_rejects_malformed_workflow_graph(
        self, client, superuser, form_definition, workflow_data
    ):
        client.force_login(superuser)
        response = client.post(
            _wf_url("workflow/api/save/"),
            data=json.dumps({"form_id": form_definition.id, "workflow": workflow_data}),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert not WorkflowDefinition.objects.filter(
            form_definition=form_definition
        ).exists()

    def test_save_assigns_stage_approval_fields(
        self, client, superuser, form_with_fields, approval_group
    ):
        email_field = form_with_fields.fields.get(field_name="email")
        notes_field = form_with_fields.fields.get(field_name="notes")

        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_with_fields.id,
            "workflow": {
                "nodes": [
                    {"type": "start", "data": {}},
                    {
                        "id": "stage_1",
                        "type": "stage",
                        "data": {
                            "stage_id": None,
                            "name": "Sign Off",
                            "order": 1,
                            "approval_logic": "all",
                            "approval_groups": [
                                {
                                    "id": approval_group.id,
                                    "name": approval_group.name,
                                    "position": 0,
                                }
                            ],
                            "approval_fields": [
                                {
                                    "id": email_field.id,
                                    "field_name": email_field.field_name,
                                    "field_label": email_field.field_label,
                                },
                                {
                                    "id": notes_field.id,
                                    "field_name": notes_field.field_name,
                                    "field_label": notes_field.field_label,
                                },
                            ],
                        },
                    },
                    {"type": "end", "data": {}},
                ],
                "connections": [],
            },
        }
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert resp.status_code == 200
        wf = WorkflowDefinition.objects.get(form_definition=form_with_fields)
        stage = wf.stages.get(name="Sign Off")
        email_field.refresh_from_db()
        notes_field.refresh_from_db()
        assert email_field.workflow_stage_id == stage.id
        assert notes_field.workflow_stage_id == stage.id

    def test_save_rejects_duplicate_stage_approval_fields(
        self, client, superuser, form_with_fields, approval_group
    ):
        notes_field = form_with_fields.fields.get(field_name="notes")
        notes_field.refresh_from_db()
        initial_notes_workflow_stage_id = notes_field.workflow_stage_id
        initial_workflow_count = WorkflowDefinition.objects.count()
        initial_stage_count = WorkflowStage.objects.count()

        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_with_fields.id,
            "workflow": {
                "nodes": [
                    {"type": "start", "data": {}},
                    {
                        "id": "stage_1",
                        "type": "stage",
                        "data": {
                            "name": "Review A",
                            "order": 1,
                            "approval_logic": "all",
                            "approval_groups": [
                                {
                                    "id": approval_group.id,
                                    "name": approval_group.name,
                                    "position": 0,
                                }
                            ],
                            "approval_fields": [
                                {
                                    "id": notes_field.id,
                                    "field_name": notes_field.field_name,
                                }
                            ],
                        },
                    },
                    {
                        "id": "stage_2",
                        "type": "stage",
                        "data": {
                            "name": "Review B",
                            "order": 2,
                            "approval_logic": "all",
                            "approval_groups": [
                                {
                                    "id": approval_group.id,
                                    "name": approval_group.name,
                                    "position": 0,
                                }
                            ],
                            "approval_fields": [
                                {
                                    "field_name": notes_field.field_name,
                                }
                            ],
                        },
                    },
                    {"type": "end", "data": {}},
                ],
                "connections": [],
            },
        }

        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "validation failed" in data["error"].lower()
        assert WorkflowDefinition.objects.count() == initial_workflow_count
        assert WorkflowStage.objects.count() == initial_stage_count
        notes_field.refresh_from_db()
        assert notes_field.workflow_stage_id == initial_notes_workflow_stage_id

    def test_save_rejects_invalid_notification_cadence_configuration(
        self, client, superuser, form_definition
    ):
        workflow = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            name_label="Existing track",
            notification_cadence="daily",
        )
        stage = workflow.stages.create(name="Existing stage", order=1)
        rule = NotificationRule.objects.create(
            workflow=workflow, event="approval_request", subject_template="Original"
        )
        initial_workflow_count = WorkflowDefinition.objects.count()
        initial_stage_count = WorkflowStage.objects.count()

        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_definition.id,
            "workflow_id": workflow.id,
            "workflow": {
                "nodes": [
                    {"type": "start", "data": {}},
                    {
                        "id": "settings_1",
                        "type": "workflow_settings",
                        "data": {
                            "notification_cadence": "weekly",
                            "notification_cadence_day": 8,
                        },
                    },
                    {"type": "end", "data": {}},
                ],
                "connections": [],
            },
        }

        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "validation failed" in data["error"].lower()
        assert WorkflowDefinition.objects.count() == initial_workflow_count
        assert WorkflowStage.objects.count() == initial_stage_count
        workflow.refresh_from_db()
        stage.refresh_from_db()
        rule.refresh_from_db()
        assert workflow.name_label == "Existing track"
        assert workflow.notification_cadence == "daily"
        assert stage.name == "Existing stage"
        assert rule.subject_template == "Original"

    def test_save_updates_selected_workflow_track_only(
        self, client, superuser, form_definition, approval_group
    ):
        first = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        second = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )
        first.stages.create(name="Stage A", order=1, approval_logic="all")

        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_definition.id,
            "workflow_id": second.id,
            "workflow": {
                "nodes": [
                    {"type": "start", "data": {}},
                    {
                        "type": "workflow_settings",
                        "data": {
                            "name_label": "Track B Updated",
                            "trigger_conditions": {
                                "operator": "AND",
                                "conditions": [
                                    {
                                        "field": "department",
                                        "operator": "equals",
                                        "value": "finance",
                                    }
                                ],
                            },
                        },
                    },
                    {
                        "type": "stage",
                        "data": {
                            "name": "Stage B",
                            "order": 1,
                            "approval_logic": "all",
                            "approval_groups": [
                                {"id": approval_group.id, "name": approval_group.name}
                            ],
                            "trigger_conditions": {
                                "operator": "OR",
                                "conditions": [
                                    {
                                        "field": "amount",
                                        "operator": "gt",
                                        "value": "500",
                                    }
                                ],
                            },
                        },
                    },
                    {"type": "end", "data": {}},
                ],
                "connections": [],
            },
        }
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert resp.status_code == 200
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.name_label == "Track A"
        assert list(first.stages.values_list("name", flat=True)) == ["Stage A"]
        assert second.name_label == "Track B Updated"
        assert second.trigger_conditions == {
            "operator": "AND",
            "conditions": [
                {
                    "field": "department",
                    "operator": "equals",
                    "value": "finance",
                }
            ],
        }
        second_stage = second.stages.get(name="Stage B")
        assert second_stage.trigger_conditions == {
            "operator": "OR",
            "conditions": [{"field": "amount", "operator": "gt", "value": "500"}],
        }

    def test_save_requires_track_id_when_form_has_multiple_workflows(
        self, client, superuser, form_definition
    ):
        first = WorkflowDefinition.objects.create(
            form_definition=form_definition, name_label="Track A"
        )
        second = WorkflowDefinition.objects.create(
            form_definition=form_definition, name_label="Track B"
        )
        client.force_login(superuser)

        response = client.post(
            _wf_url("workflow/api/save/"),
            data=json.dumps(
                {
                    "form_id": form_definition.id,
                    "workflow": {
                        "nodes": [
                            {"type": "start", "data": {}},
                            {"type": "end", "data": {}},
                        ],
                        "connections": [],
                    },
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert (
            WorkflowDefinition.objects.filter(form_definition=form_definition).count()
            == 2
        )
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.name_label == "Track A"
        assert second.name_label == "Track B"

    def test_foreign_workflow_id_is_rejected(self, client, superuser, form_definition):
        other_form = FormDefinition.objects.create(name="Other form", slug="other-form")
        local = WorkflowDefinition.objects.create(
            form_definition=form_definition, name_label="Local"
        )
        foreign = WorkflowDefinition.objects.create(
            form_definition=other_form, name_label="Foreign"
        )
        client.force_login(superuser)

        load = client.get(
            _wf_url(f"workflow/api/load/{form_definition.id}/"),
            {"workflow_id": foreign.id},
        )
        save = client.post(
            _wf_url("workflow/api/save/"),
            data=json.dumps(
                {
                    "form_id": form_definition.id,
                    "workflow_id": foreign.id,
                    "workflow": {"nodes": []},
                }
            ),
            content_type="application/json",
        )

        assert load.status_code == 404
        assert save.status_code == 404
        local.refresh_from_db()
        foreign.refresh_from_db()
        assert local.name_label == "Local"
        assert foreign.name_label == "Foreign"


# ── save_form_definition_from_builder_data ──────────────────────────────────


class TestSaveFormDefinitionFromBuilderData:
    """Tests for the form builder's save logic, factored out of
    form_builder_save so it can be called directly — mirrors the
    convert_visual_to_workflow/form_builder_save split above."""

    def test_creates_a_new_form_definition(self, user):
        data = {
            "name": "New Form",
            "slug": "new-form",
            "description": "A brand new form",
            "fields": [],
        }
        form_definition, field_id_mapping = save_form_definition_from_builder_data(
            data, user
        )
        assert form_definition.pk is not None
        assert form_definition.name == "New Form"
        assert form_definition.slug == "new-form"
        assert form_definition.description == "A brand new form"
        assert form_definition.created_by == user
        assert field_id_mapping == {}

    def test_updates_an_existing_form_definition_in_place(self, user, form_definition):
        data = {
            "name": "Renamed Form",
            "slug": form_definition.slug,
            "description": "Updated description",
            "fields": [],
        }
        result, _ = save_form_definition_from_builder_data(
            data, user, form_definition=form_definition
        )
        assert result.pk == form_definition.pk
        assert result.name == "Renamed Form"
        assert result.description == "Updated description"

    def test_increments_version_on_update_but_not_on_create(
        self, user, form_definition
    ):
        assert form_definition.version == 1
        data = {
            "name": form_definition.name,
            "slug": form_definition.slug,
            "fields": [],
        }
        updated, _ = save_form_definition_from_builder_data(
            data, user, form_definition=form_definition
        )
        assert updated.version == 2

        created, _ = save_form_definition_from_builder_data(
            {"name": "Another Form", "slug": "another-form", "fields": []}, user
        )
        assert created.version == 1

    def test_creates_new_fields(self, user, form_definition):
        data = {
            "name": form_definition.name,
            "slug": form_definition.slug,
            "fields": [
                {
                    "id": "temp-1",
                    "field_name": "new_field",
                    "field_label": "New Field",
                    "field_type": "text",
                    "order": 1,
                    "required": True,
                }
            ],
        }
        result, field_id_mapping = save_form_definition_from_builder_data(
            data, user, form_definition=form_definition
        )
        new_field = result.fields.get(field_name="new_field")
        assert new_field.field_label == "New Field"
        assert new_field.required is True
        assert field_id_mapping == {"temp-1": new_field.id}

    def test_creates_field_with_builder_temporary_id(self, user, form_definition):
        data = {
            "name": form_definition.name,
            "slug": form_definition.slug,
            "fields": [
                {
                    "id": "new_1",
                    "field_name": "new_field",
                    "field_label": "New Field",
                    "field_type": "text",
                }
            ],
        }

        result, mapping = save_form_definition_from_builder_data(
            data, user, form_definition=form_definition
        )

        assert mapping == {"new_1": result.fields.get(field_name="new_field").id}

    def test_updates_an_existing_field(self, user, form_with_fields):
        field = form_with_fields.fields.get(field_name="full_name")
        data = {
            "name": form_with_fields.name,
            "slug": form_with_fields.slug,
            "fields": [
                {
                    "id": field.id,
                    "field_name": "full_name",
                    "field_label": "Renamed Label",
                    "field_type": "text",
                    "order": 1,
                    "required": True,
                }
            ],
        }
        save_form_definition_from_builder_data(
            data, user, form_definition=form_with_fields
        )
        field.refresh_from_db()
        assert field.field_label == "Renamed Label"

    def test_direct_save_rolls_back_form_and_fields_on_invalid_id(
        self, user, form_with_fields
    ):
        first = form_with_fields.fields.get(field_name="full_name")
        second = form_with_fields.fields.get(field_name="email")
        original_label = first.field_label
        original_version = form_with_fields.version
        data = {
            "name": "Changed form",
            "slug": form_with_fields.slug,
            "fields": [
                {
                    "id": first.id,
                    "field_name": first.field_name,
                    "field_label": "Changed label",
                    "field_type": first.field_type,
                    "order": first.order,
                },
                {
                    "id": True,
                    "field_name": second.field_name,
                    "field_label": second.field_label,
                    "field_type": second.field_type,
                    "order": second.order,
                },
            ],
        }

        with pytest.raises(FormBuilderPayloadError):
            save_form_definition_from_builder_data(
                data, user, form_definition=form_with_fields
            )

        form_with_fields.refresh_from_db()
        first.refresh_from_db()
        assert form_with_fields.name != "Changed form"
        assert form_with_fields.version == original_version
        assert first.field_label == original_label

    def test_deletes_fields_absent_from_the_payload(self, user, form_with_fields):
        assert form_with_fields.fields.count() == 5
        data = {
            "name": form_with_fields.name,
            "slug": form_with_fields.slug,
            "fields": [],
        }
        save_form_definition_from_builder_data(
            data, user, form_definition=form_with_fields
        )
        assert form_with_fields.fields.count() == 0

    def test_keeps_fields_present_in_the_payload_by_id(self, user, form_with_fields):
        keep = form_with_fields.fields.get(field_name="email")
        data = {
            "name": form_with_fields.name,
            "slug": form_with_fields.slug,
            "fields": [
                {
                    "id": keep.id,
                    "field_name": keep.field_name,
                    "field_label": keep.field_label,
                    "field_type": keep.field_type,
                    "order": keep.order,
                }
            ],
        }
        save_form_definition_from_builder_data(
            data, user, form_definition=form_with_fields
        )
        assert form_with_fields.fields.count() == 1
        assert form_with_fields.fields.get().pk == keep.pk


# ── Form builder view tests ─────────────────────────────────────────────────


class TestFormBuilderSavePayloadValidation:
    """form_builder_save must keep fields and stages scoped to the form being
    saved, and reject bad references without persisting any of the save."""

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {"name": "Form", "slug": "form", "fields": {}},
            {"name": "Form", "slug": "form", "fields": [1]},
            {"name": 123, "slug": "form", "fields": []},
            {"name": "Form", "slug": None, "fields": []},
            {"id": True, "name": "Form", "slug": "form", "fields": []},
            {"id": -1, "name": "Form", "slug": "form", "fields": []},
            {"id": "²", "name": "Form", "slug": "form", "fields": []},
        ],
    )
    def test_rejects_invalid_payload_types(self, client, superuser, payload):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert not FormDefinition.objects.filter(slug="form").exists()

    @pytest.mark.parametrize("field_ids", [[[], []], ["new_1", "new_1"], [1, 1]])
    def test_rejects_malformed_or_duplicate_field_ids(
        self, client, superuser, field_ids
    ):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {
                    "name": "Form",
                    "slug": "form",
                    "fields": [
                        {"id": field_id, "field_name": f"field_{index}"}
                        for index, field_id in enumerate(field_ids)
                    ],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert not FormDefinition.objects.filter(slug="form").exists()

    @pytest.mark.parametrize(
        "field_name",
        ["description", "instructions", "success_message", "success_redirect_url"],
    )
    def test_rejects_non_string_optional_text(self, client, superuser, field_name):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {"name": "Form", "slug": "form", "fields": [], field_name: []}
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert not FormDefinition.objects.filter(slug="form").exists()

    @staticmethod
    def _save(client, form, fields):
        return client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {
                    "id": form.id,
                    "name": form.name,
                    "slug": form.slug,
                    "fields": fields,
                }
            ),
            content_type="application/json",
        )

    @staticmethod
    def _field_payload(field, **overrides):
        return {
            "id": field.id,
            "field_name": field.field_name,
            "field_label": "Changed Label",
            "field_type": field.field_type,
            "order": field.order,
            **overrides,
        }

    @pytest.fixture
    def other_form(self, db):
        return FormDefinition.objects.create(
            name="Other Form", slug="other-form", description="", instructions=""
        )

    @pytest.fixture
    def field(self, form_with_fields):
        return form_with_fields.fields.get(field_name="full_name")

    def test_assigns_stage_from_same_form(
        self, client, superuser, form_with_fields, field
    ):
        wf = WorkflowDefinition.objects.create(form_definition=form_with_fields)
        stage = WorkflowStage.objects.create(workflow=wf, name="Review", order=1)
        client.force_login(superuser)

        resp = self._save(
            client,
            form_with_fields,
            [self._field_payload(field, workflow_stage_id=str(stage.id))],
        )

        assert resp.status_code == 200
        field.refresh_from_db()
        assert field.workflow_stage_id == stage.id

    def test_clears_stage_when_blank(self, client, superuser, form_with_fields, field):
        wf = WorkflowDefinition.objects.create(form_definition=form_with_fields)
        field.workflow_stage = WorkflowStage.objects.create(
            workflow=wf, name="Review", order=1
        )
        field.save()
        client.force_login(superuser)

        resp = self._save(
            client, form_with_fields, [self._field_payload(field, workflow_stage_id="")]
        )

        assert resp.status_code == 200
        field.refresh_from_db()
        assert field.workflow_stage_id is None

    def test_rejects_stage_from_another_form_and_rolls_back(
        self, client, superuser, form_with_fields, field, other_form
    ):
        wf = WorkflowDefinition.objects.create(form_definition=other_form)
        foreign_stage = WorkflowStage.objects.create(
            workflow=wf, name="Foreign", order=1
        )
        second_field = FormField.objects.create(
            form_definition=form_with_fields,
            field_name="rollback_target",
            field_label="Rollback Target",
            field_type="text",
            order=(field.order or 0) + 1,
        )
        original_version = form_with_fields.version
        original_label = field.field_label
        original_second_label = second_field.field_label
        client.force_login(superuser)

        resp = self._save(
            client,
            form_with_fields,
            [
                self._field_payload(field, field_label="Updated Before Failure"),
                self._field_payload(second_field, workflow_stage_id=foreign_stage.id),
            ],
        )

        assert resp.status_code == 400
        assert resp.json()["success"] is False
        assert "not valid for this form" in resp.json()["error"]
        form_with_fields.refresh_from_db()
        field.refresh_from_db()
        second_field.refresh_from_db()
        assert form_with_fields.version == original_version
        assert field.field_label == original_label
        assert second_field.field_label == original_second_label
        assert second_field.workflow_stage_id is None

    @pytest.mark.parametrize("stage_id", ["not-a-number", True, 1.5, "++1"])
    def test_rejects_malformed_stage_id(
        self, client, superuser, form_with_fields, field, stage_id
    ):
        client.force_login(superuser)

        resp = self._save(
            client,
            form_with_fields,
            [self._field_payload(field, workflow_stage_id=stage_id)],
        )

        assert resp.status_code == 400
        assert "Invalid workflow_stage_id" in resp.json()["error"]

    def test_rejects_field_from_another_form_and_rolls_back(
        self, client, superuser, form_with_fields, field, other_form
    ):
        foreign_field = FormField.objects.create(
            form_definition=other_form,
            field_name="foreign",
            field_label="Foreign Label",
            field_type="text",
            order=1,
        )
        original_field_count = form_with_fields.fields.count()
        client.force_login(superuser)

        resp = self._save(
            client, form_with_fields, [self._field_payload(foreign_field)]
        )

        assert resp.status_code == 400
        assert "Invalid field id" in resp.json()["error"]
        foreign_field.refresh_from_db()
        assert foreign_field.form_definition_id == other_form.id
        assert foreign_field.field_label == "Foreign Label"
        # The removal of this form's own fields must be rolled back as well.
        assert form_with_fields.fields.count() == original_field_count


@pytest.mark.django_db
class TestFormBuilderViews:
    """Integration tests for the form builder HTTP endpoints."""

    def test_builder_view_requires_staff(self, client, form_definition, user):
        client.force_login(user)
        url = _fb_url(f"builder/{form_definition.id}/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_builder_view_accessible_to_superuser(
        self, client, form_definition, superuser
    ):
        client.login(username="admin", password="testpass123")
        url = _fb_url(f"builder/{form_definition.id}/")
        resp = client.get(url)
        assert resp.status_code == 200

    def test_builder_new_view_requires_staff(self, client, user):
        client.force_login(user)
        url = _fb_url("builder/new/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_load_returns_json(self, client, superuser, form_with_fields):
        client.login(username="admin", password="testpass123")
        url = _fb_url(f"builder/api/load/{form_with_fields.id}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        # form_builder_load returns form data at top level
        assert "fields" in data
        assert len(data["fields"]) == 5

    def test_load_preserves_zero_payment_amount(
        self, client, superuser, form_definition
    ):
        form_definition.payment_fixed_amount = 0
        form_definition.save(update_fields=["payment_fixed_amount"])
        client.force_login(superuser)

        response = client.get(_fb_url(f"builder/api/load/{form_definition.id}/"))

        assert response.status_code == 200
        assert response.json()["payment_fixed_amount"] == "0.00"

    def test_save_preserves_zero_payment_amount(
        self, client, superuser, form_definition
    ):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {
                    "id": form_definition.id,
                    "name": form_definition.name,
                    "slug": form_definition.slug,
                    "payment_fixed_amount": 0,
                    "fields": [],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        form_definition.refresh_from_db()
        assert form_definition.payment_fixed_amount == 0

    def test_file_settings_survive_builder_load_and_save(
        self, client, superuser, form_definition
    ):
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="attachment",
            field_label="Attachment",
            field_type="file",
            allowed_extensions="pdf,docx",
            max_file_size_mb=12,
        )
        client.force_login(superuser)
        loaded = client.get(_fb_url(f"builder/api/load/{form_definition.pk}/"))
        assert loaded.status_code == 200
        field_data = loaded.json()["fields"][0]
        assert field_data["allowed_extensions"] == "pdf,docx"
        assert field_data["max_file_size_mb"] == 12

        saved = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {
                    "id": form_definition.pk,
                    "name": form_definition.name,
                    "slug": form_definition.slug,
                    "fields": [field_data],
                }
            ),
            content_type="application/json",
        )
        assert saved.status_code == 200
        field.refresh_from_db()
        assert field.allowed_extensions == "pdf,docx"
        assert field.max_file_size_mb == 12

    def test_save_missing_form_returns_404(self, client, superuser):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/save/"),
            data=json.dumps(
                {"id": 999999, "name": "Missing", "slug": "missing", "fields": []}
            ),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_load_requires_staff(self, client, user, form_with_fields):
        client.force_login(user)
        url = _fb_url(f"builder/api/load/{form_with_fields.id}/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_save_creates_fields(self, client, superuser, form_definition):
        client.login(username="admin", password="testpass123")
        url = _fb_url("builder/api/save/")
        payload = {
            "id": form_definition.id,
            "name": form_definition.name,
            "slug": form_definition.slug,
            "description": form_definition.description,
            "instructions": form_definition.instructions,
            "fields": [
                {
                    "field_name": "new_field",
                    "field_label": "New Field",
                    "field_type": "text",
                    "order": 1,
                    "required": True,
                }
            ],
        }
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert form_definition.fields.filter(field_name="new_field").exists()

    def test_save_requires_staff(self, client, user, form_definition):
        client.force_login(user)
        url = _fb_url("builder/api/save/")
        payload = {
            "id": form_definition.id,
            "name": form_definition.name,
            "slug": form_definition.slug,
            "description": form_definition.description,
            "instructions": form_definition.instructions,
            "fields": [
                {
                    "field_name": "denied_field",
                    "field_label": "Denied Field",
                    "field_type": "text",
                    "order": 1,
                    "required": True,
                }
            ],
        }
        before_count = form_definition.fields.count()
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)
        form_definition.refresh_from_db()
        assert form_definition.fields.count() == before_count
        assert not form_definition.fields.filter(field_name="denied_field").exists()

    def test_save_staff_requires_model_permission(
        self, client, django_user_model, form_definition
    ):
        staff_user = django_user_model.objects.create_user(
            username="builder_staff",
            password="testpass123",
            is_staff=True,
            is_superuser=False,
        )
        client.force_login(staff_user)
        url = _fb_url("builder/api/save/")
        payload = {
            "id": form_definition.id,
            "name": form_definition.name,
            "slug": form_definition.slug,
            "description": form_definition.description,
            "instructions": form_definition.instructions,
            "fields": [
                {
                    "field_name": "staff_perm_field",
                    "field_label": "Staff Perm Field",
                    "field_type": "text",
                    "order": 1,
                    "required": True,
                }
            ],
        }

        before_count = form_definition.fields.count()
        denied = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert denied.status_code in (302, 403)
        form_definition.refresh_from_db()
        assert form_definition.fields.count() == before_count
        assert not form_definition.fields.filter(field_name="staff_perm_field").exists()

        from django.contrib.auth.models import Permission

        change_perm = Permission.objects.get(
            content_type__app_label=FormDefinition._meta.app_label,
            codename=f"change_{FormDefinition._meta.model_name}",
        )
        staff_user.user_permissions.add(change_perm)

        allowed = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert allowed.status_code == 200
        assert allowed.json()["success"] is True
        assert form_definition.fields.filter(field_name="staff_perm_field").exists()

    def test_clone_form(self, client, superuser, form_with_fields):
        client.login(username="admin", password="testpass123")
        url = _fb_url(f"builder/api/clone/{form_with_fields.id}/")
        resp = client.post(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        cloned = FormDefinition.objects.get(id=data["form_id"])
        assert cloned.name.startswith(form_with_fields.name)
        assert cloned.id != form_with_fields.id
        assert cloned.fields.count() == form_with_fields.fields.count()

    def test_clone_copies_automation_and_settings(
        self, client, superuser, form_with_fields, approval_group
    ):
        form_with_fields.api_enabled = True
        form_with_fields.allow_resubmit = True
        form_with_fields.save(update_fields=["api_enabled", "allow_resubmit"])
        workflow = WorkflowDefinition.objects.create(form_definition=form_with_fields)
        stage = WorkflowStage.objects.create(workflow=workflow, name="Review", order=1)
        rule = NotificationRule.objects.create(
            workflow=workflow,
            stage=stage,
            event="approval_request",
            static_emails="review@example.com",
        )
        rule.notify_groups.add(approval_group)
        PostSubmissionAction.objects.create(
            form_definition=form_with_fields,
            name="Follow up",
            action_type="email",
            trigger="on_submit",
            email_to="owner@example.com",
        )
        client.force_login(superuser)

        response = client.post(_fb_url(f"builder/api/clone/{form_with_fields.id}/"))

        assert response.status_code == 200
        cloned = FormDefinition.objects.get(pk=response.json()["form_id"])
        assert cloned.uuid != form_with_fields.uuid
        assert cloned.api_enabled is True
        assert cloned.allow_resubmit is True
        cloned_workflow = cloned.workflows.get()
        cloned_rule = cloned_workflow.notification_rules.get()
        assert cloned_rule.stage == cloned_workflow.stages.get()
        assert cloned_rule.static_emails == rule.static_emails
        assert list(cloned_rule.notify_groups.all()) == [approval_group]
        cloned_action = cloned.post_actions.get()
        assert cloned_action.email_to == "owner@example.com"
        assert cloned_action.trigger == "on_submit"

    def test_clone_preserves_field_settings_without_stale_workflow_layout(
        self, client, superuser, form_with_fields
    ):
        field = form_with_fields.fields.first()
        options = SharedOptionList.objects.create(
            name="Departments", slug="departments", items=["Engineering"]
        )
        field.shared_option_list = options
        field.validation_rules = [{"type": "required", "message": "Required"}]
        field.field_dependencies = [{"sourceField": "source"}]
        field.step_number = 2
        field.save(
            update_fields=[
                "shared_option_list",
                "validation_rules",
                "field_dependencies",
                "step_number",
            ]
        )
        workflow = WorkflowDefinition.objects.create(form_definition=form_with_fields)
        stage = WorkflowStage.objects.create(workflow=workflow, name="Review", order=1)
        stage.allow_send_back = True
        stage.allow_reassign = True
        stage.assignee_form_field = "reviewer_email"
        stage.assignee_lookup_type = "email"
        stage.save()
        field.workflow_stage = stage
        field.save(update_fields=["workflow_stage"])
        workflow.visual_workflow_data = {
            "nodes": [
                {"id": "stage_1", "type": "stage", "data": {"stage_id": stage.id}}
            ],
            "connections": [],
        }
        workflow.save(update_fields=["visual_workflow_data"])
        client.force_login(superuser)

        response = client.post(_fb_url(f"builder/api/clone/{form_with_fields.id}/"))

        assert response.status_code == 200
        cloned = FormDefinition.objects.get(id=response.json()["form_id"])
        cloned_field = cloned.fields.get(field_name=field.field_name)
        assert cloned_field.shared_option_list == options
        assert cloned_field.validation_rules == field.validation_rules
        assert cloned_field.field_dependencies == field.field_dependencies
        assert cloned_field.step_number == field.step_number
        cloned_workflow = cloned.workflows.get()
        assert cloned_workflow.visual_workflow_data is None
        cloned_stage = cloned_workflow.stages.get()
        assert cloned_stage.id != stage.id
        assert cloned_field.workflow_stage == cloned_stage
        assert cloned_stage.allow_send_back is True
        assert cloned_stage.allow_reassign is True
        assert cloned_stage.assignee_form_field == "reviewer_email"
        assert cloned_stage.assignee_lookup_type == "email"

        loaded = client.get(_fb_url(f"builder/api/load/{cloned.id}/"))
        assert loaded.status_code == 200
        loaded_field = next(
            item for item in loaded.json()["fields"] if item["id"] == cloned_field.id
        )
        assert loaded_field["workflow_stage_id"] == cloned_stage.id
        assert loaded_field["validation_rules"] == field.validation_rules
        assert loaded_field["field_dependencies"] == field.field_dependencies
        assert loaded_field["step_number"] == field.step_number

    def test_clone_copies_all_permission_groups(
        self, client, superuser, form_with_fields, approval_group
    ):
        for groups in (
            form_with_fields.submit_groups,
            form_with_fields.view_groups,
            form_with_fields.reviewer_groups,
            form_with_fields.admin_groups,
        ):
            groups.set([approval_group])
        client.force_login(superuser)

        resp = client.post(_fb_url(f"builder/api/clone/{form_with_fields.id}/"))

        assert resp.status_code == 200
        cloned = FormDefinition.objects.get(id=resp.json()["form_id"])
        assert list(cloned.submit_groups.all()) == [approval_group]
        assert list(cloned.view_groups.all()) == [approval_group]
        assert list(cloned.reviewer_groups.all()) == [approval_group]
        assert list(cloned.admin_groups.all()) == [approval_group]

    def test_clone_requires_staff(self, client, user, form_with_fields):
        client.force_login(user)
        before_count = FormDefinition.objects.count()
        url = _fb_url(f"builder/api/clone/{form_with_fields.id}/")
        resp = client.post(url)
        assert resp.status_code in (302, 403)
        assert FormDefinition.objects.count() == before_count

    def test_preview_form(self, client, superuser, form_with_fields):
        client.login(username="admin", password="testpass123")
        url = _fb_url("builder/api/preview/")
        form_count_before = FormDefinition.objects.count()
        field_count_before = FormField.objects.count()
        field_label = "Preview Test Field"
        resp = client.post(
            url,
            data=json.dumps(
                {
                    "name": "Preview Form",
                    "fields": [
                        {
                            "field_name": "preview_test_field",
                            "field_type": "text",
                            "field_label": field_label,
                            "required": False,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert field_label in resp.json()["html"]
        assert FormDefinition.objects.count() == form_count_before
        assert FormField.objects.count() == field_count_before

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {"fields": {}},
            {"fields": [1]},
            {"fields": [{"field_name": "answer", "validation": []}]},
            {"fields": [{"field_name": "answer", "conditional": "bad"}]},
            {"form_steps": {}},
        ],
    )
    def test_preview_rejects_invalid_payload_types(self, client, superuser, payload):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/preview/"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_preview_escapes_form_name_and_instructions(self, client, superuser):
        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/preview/"),
            data=json.dumps(
                {
                    "name": "<script>alert(1)</script>",
                    "instructions": "<img src=x onerror=alert(1)>",
                    "fields": [
                        {
                            "field_name": "answer",
                            "field_label": "Answer",
                            "field_type": "text",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        html = response.json()["html"]
        assert "<script>" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;" in html
        assert "&lt;img src=x" in html

    def test_preview_requires_staff(self, client, user, form_with_fields):
        client.force_login(user)
        url = _fb_url("builder/api/preview/")
        resp = client.post(
            url,
            data=json.dumps({"form_id": form_with_fields.id}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)


# ── Document Template API endpoints ─────────────────────────────────────────


class TestDocumentTemplateAPI:
    """Tests for the document template CRUD API endpoints."""

    def test_list_templates_empty(self, client, superuser, form_definition):
        client.force_login(superuser)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["templates"] == []

    def test_save_new_template(self, client, superuser, form_definition):
        client.force_login(superuser)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/save/")
        resp = client.post(
            url,
            data=json.dumps(
                {
                    "name": "Test Cert",
                    "html_content": "<h1>{form_name}</h1>",
                    "page_size": "a4",
                    "is_default": True,
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["id"] is not None

    def test_save_requires_staff(self, client, user, form_definition):
        from django_forms_workflows.models import DocumentTemplate

        client.force_login(user)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/save/")
        resp = client.post(
            url,
            data=json.dumps({"name": "Guarded", "html_content": "<p>guarded</p>"}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)
        assert not DocumentTemplate.objects.filter(name="Guarded").exists()

    def test_save_template_requires_name(self, client, superuser, form_definition):
        client.force_login(superuser)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/save/")
        resp = client.post(
            url,
            data=json.dumps({"name": "", "html_content": "<p>Hi</p>"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_update_template(self, client, superuser, form_definition):
        from django_forms_workflows.models import DocumentTemplate

        client.force_login(superuser)
        tpl = DocumentTemplate.objects.create(
            form_definition=form_definition,
            name="Original",
            html_content="<p>old</p>",
        )
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/save/")
        resp = client.post(
            url,
            data=json.dumps(
                {
                    "id": tpl.id,
                    "name": "Updated",
                    "html_content": "<p>new</p>",
                    "page_size": "legal",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        tpl.refresh_from_db()
        assert tpl.name == "Updated"
        assert tpl.page_size == "legal"

    def test_delete_template(self, client, superuser, form_definition):
        from django_forms_workflows.models import DocumentTemplate

        client.force_login(superuser)
        tpl = DocumentTemplate.objects.create(
            form_definition=form_definition,
            name="To Delete",
            html_content="<p>bye</p>",
        )
        url = _fb_url(
            f"builder/api/doc-templates/{form_definition.id}/delete/{tpl.id}/"
        )
        resp = client.post(url)
        assert resp.status_code == 200
        assert not DocumentTemplate.objects.filter(id=tpl.id).exists()

    def test_delete_requires_staff(self, client, user, form_definition):
        from django_forms_workflows.models import DocumentTemplate

        tpl = DocumentTemplate.objects.create(
            form_definition=form_definition,
            name="Guarded",
            html_content="<p>guarded</p>",
        )
        client.force_login(user)
        url = _fb_url(
            f"builder/api/doc-templates/{form_definition.id}/delete/{tpl.id}/"
        )
        resp = client.post(url)
        assert resp.status_code in (302, 403)
        assert DocumentTemplate.objects.filter(id=tpl.id).exists()

    def test_set_default_clears_previous_default(
        self, client, superuser, form_definition
    ):
        from django_forms_workflows.models import DocumentTemplate

        client.force_login(superuser)
        t1 = DocumentTemplate.objects.create(
            form_definition=form_definition,
            name="First",
            html_content="<p>1</p>",
            is_default=True,
        )
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/save/")
        resp = client.post(
            url,
            data=json.dumps(
                {
                    "name": "Second",
                    "html_content": "<p>2</p>",
                    "is_default": True,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        payload = resp.json()
        t2 = DocumentTemplate.objects.get(id=payload["id"])
        t1.refresh_from_db()
        assert t1.is_default is False
        assert t2.is_default is True
        assert (
            DocumentTemplate.objects.filter(
                form_definition=form_definition, is_default=True
            ).count()
            == 1
        )

    def test_non_staff_cannot_access(self, client, user, form_definition):
        client.force_login(user)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/")
        resp = client.get(url)
        # staff_member_required redirects non-staff
        assert resp.status_code == 302


# ── Prebuilt form template API endpoints ────────────────────────────────────


class TestFormBuilderTemplateAPI:
    """Tests for the prebuilt form template list/load API endpoints."""

    def test_list_requires_staff(self, client, user):
        client.force_login(user)
        url = _fb_url("builder/api/templates/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_list_returns_active_templates(self, client, superuser):
        from django_forms_workflows.models import FormTemplate

        FormTemplate.objects.create(
            name="Contact Form",
            slug="contact-form",
            description="A simple contact form",
            template_data={"fields": []},
        )
        FormTemplate.objects.create(
            name="Inactive Contact Form",
            slug="inactive-contact-form",
            template_data={"fields": []},
            is_active=False,
        )
        client.force_login(superuser)
        url = _fb_url("builder/api/templates/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert [t["slug"] for t in data["templates"]] == ["contact-form"]

    def test_load_template_requires_staff(self, client, user):
        from django_forms_workflows.models import FormTemplate

        template = FormTemplate.objects.create(
            name="Contact Form",
            slug="contact-form-guarded",
            description="A simple contact form",
            template_data={"fields": []},
        )
        client.force_login(user)
        url = _fb_url(f"builder/api/templates/{template.id}/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)
        template.refresh_from_db()
        assert template.usage_count == 0

    def test_load_template_returns_data_and_increments_usage(self, client, superuser):
        from django_forms_workflows.models import FormTemplate

        template = FormTemplate.objects.create(
            name="Contact Form",
            slug="contact-form-load",
            description="A simple contact form",
            template_data={"fields": [{"field_name": "email"}]},
        )
        client.force_login(superuser)
        url = _fb_url(f"builder/api/templates/{template.id}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["template_data"] == {"fields": [{"field_name": "email"}]}
        template.refresh_from_db()
        assert template.usage_count == 1


# ── Shared option list API endpoints ────────────────────────────────────────


class TestSharedOptionListAPI:
    """Tests for the centrally managed shared option list CRUD API endpoints."""

    def test_list_requires_staff(self, client, user):
        client.force_login(user)
        url = _fb_url("builder/api/shared-lists/")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_list_returns_active_lists(self, client, superuser):
        from django_forms_workflows.models import SharedOptionList

        ol = SharedOptionList.objects.create(
            name="Departments", slug="departments", items=["HR", "IT"]
        )
        SharedOptionList.objects.create(
            name="Inactive Departments",
            slug="inactive-departments",
            items=["Old"],
            is_active=False,
        )
        client.force_login(superuser)
        url = _fb_url("builder/api/shared-lists/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["lists"]) == 1
        assert data["lists"][0]["id"] == ol.id
        assert data["lists"][0]["name"] == "Departments"
        assert data["lists"][0]["slug"] == "departments"
        assert data["lists"][0]["item_count"] == 2

    def test_save_requires_staff(self, client, user):
        from django_forms_workflows.models import SharedOptionList

        client.force_login(user)
        url = _fb_url("builder/api/shared-lists/save/")
        resp = client.post(
            url,
            data=json.dumps({"name": "Guarded", "items": ["a"]}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)
        assert not SharedOptionList.objects.filter(name="Guarded").exists()

    def test_save_creates_list(self, client, superuser):
        from django_forms_workflows.models import SharedOptionList

        client.force_login(superuser)
        url = _fb_url("builder/api/shared-lists/save/")
        resp = client.post(
            url,
            data=json.dumps({"name": "Locations", "items": ["HQ", "Annex"]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        ol = SharedOptionList.objects.get(id=data["id"])
        assert ol.slug == "locations"
        assert ol.items == ["HQ", "Annex"]

    @pytest.mark.parametrize(
        "items",
        [{"value": "a"}, [1], [""], [{"label": "Missing value"}]],
    )
    def test_save_rejects_invalid_items(self, client, superuser, items):
        from django_forms_workflows.models import SharedOptionList

        client.force_login(superuser)
        response = client.post(
            _fb_url("builder/api/shared-lists/save/"),
            data=json.dumps({"name": "Invalid", "items": items}),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert not SharedOptionList.objects.filter(name="Invalid").exists()

    def test_delete_requires_staff(self, client, user):
        from django_forms_workflows.models import SharedOptionList

        ol = SharedOptionList.objects.create(
            name="Guarded", slug="guarded", items=["a"]
        )
        client.force_login(user)
        url = _fb_url(f"builder/api/shared-lists/delete/{ol.id}/")
        resp = client.post(url)
        assert resp.status_code in (302, 403)
        assert SharedOptionList.objects.filter(id=ol.id).exists()

    def test_delete_removes_list(self, client, superuser):
        from django_forms_workflows.models import SharedOptionList

        ol = SharedOptionList.objects.create(
            name="Temp Locations", slug="temp-locations", items=["a"]
        )
        client.force_login(superuser)
        url = _fb_url(f"builder/api/shared-lists/delete/{ol.id}/")
        resp = client.post(url)
        assert resp.status_code == 200
        assert not SharedOptionList.objects.filter(id=ol.id).exists()


@pytest.mark.parametrize(
    "path,payload",
    [
        ("builder/api/clone/999999/", {}),
        ("builder/api/doc-templates/999999/save/", {"name": "Missing"}),
        (
            "builder/api/shared-lists/save/",
            {"id": 999999, "name": "Missing", "slug": "missing"},
        ),
    ],
)
def test_missing_builder_objects_return_404(client, superuser, path, payload):
    client.force_login(superuser)
    response = client.post(
        _fb_url(path), data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 404
