"""
Tests for the form builder and workflow builder admin views.
"""

import json
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from django_forms_workflows.models import (
    FormDefinition,
    NotificationRule,
    PostSubmissionAction,
    StageApprovalGroup,
    WorkflowDefinition,
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
        client.login(username="testuser", password="testpass123")
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
                                    "id": notes_field.id,
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

    def test_save_rejects_invalid_notification_cadence_configuration(
        self, client, superuser, form_definition
    ):
        client.login(username="admin", password="testpass123")
        url = _wf_url("workflow/api/save/")
        payload = {
            "form_id": form_definition.id,
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


# ── Form builder view tests ─────────────────────────────────────────────────


class TestFormBuilderViews:
    """Integration tests for the form builder HTTP endpoints."""

    def test_builder_view_requires_staff(self, client, form_definition, user):
        client.login(username="testuser", password="testpass123")
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

    def test_load_returns_json(self, client, superuser, form_with_fields):
        client.login(username="admin", password="testpass123")
        url = _fb_url(f"builder/api/load/{form_with_fields.id}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        # form_builder_load returns form data at top level
        assert "fields" in data
        assert len(data["fields"]) == 5

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

    def test_preview_form(self, client, superuser, form_with_fields):
        client.login(username="admin", password="testpass123")
        url = _fb_url("builder/api/preview/")
        resp = client.post(
            url,
            data=json.dumps({"form_id": form_with_fields.id}),
            content_type="application/json",
        )
        assert resp.status_code == 200


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
        t1.refresh_from_db()
        assert t1.is_default is False

    def test_non_staff_cannot_access(self, client, user, form_definition):
        client.force_login(user)
        url = _fb_url(f"builder/api/doc-templates/{form_definition.id}/")
        resp = client.get(url)
        # staff_member_required redirects non-staff
        assert resp.status_code == 302
