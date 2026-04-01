"""
Tests for the form builder and workflow builder admin views.
"""

import json

import pytest

from django_forms_workflows.models import (
    FormDefinition,
    PostSubmissionAction,
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
        staged_workflow.approval_deadline_days = 7
        staged_workflow.notification_cadence = "form_field_date"
        staged_workflow.notification_cadence_form_field = "review_date"
        staged_workflow.save()

        result = convert_workflow_to_visual(staged_workflow, form_definition)
        ws = next(n for n in result["nodes"] if n["type"] == "workflow_settings")
        assert ws["data"]["approval_deadline_days"] == 7
        assert ws["data"]["notification_cadence"] == "form_field_date"
        assert ws["data"]["notification_cadence_form_field"] == "review_date"

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

    def test_creates_stages(self, form_definition, approval_group):
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
                    "assignee_form_field": "manager_email",
                    "assignee_lookup_type": "email",
                    "validate_assignee_group": False,
                    "approval_groups": [
                        {"id": approval_group.id, "name": approval_group.name}
                    ],
                }
            ]
        )
        wf = convert_visual_to_workflow(visual, form_definition)
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
        assert stages[0].assignee_form_field == "manager_email"
        assert stages[0].assignee_lookup_type == "email"
        assert stages[0].validate_assignee_group is False
        assert list(stages[0].approval_groups.values_list("id", flat=True)) == [
            approval_group.id
        ]

    def test_updates_existing_stages(self, staged_workflow, form_definition):
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
                    "approval_groups": [],
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

    def test_saves_workflow_settings(self, form_definition):
        visual = self._make_visual(
            settings={
                "requires_approval": True,
                "approval_deadline_days": 14,
                "send_reminder_after_days": 3,
                "auto_approve_after_days": "",
                "notification_cadence": "monthly",
                "notification_cadence_day": 15,
                "notification_cadence_time": "08:30",
                "notification_cadence_form_field": "reminder_date",
            }
        )
        wf = convert_visual_to_workflow(visual, form_definition)
        assert wf.approval_deadline_days == 14
        assert wf.send_reminder_after_days == 3
        assert wf.auto_approve_after_days is None
        assert wf.notification_cadence == "monthly"
        assert wf.notification_cadence_day == 15
        assert wf.notification_cadence_time.strftime("%H:%M") == "08:30"
        assert wf.notification_cadence_form_field == "reminder_date"

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

    def test_creates_email_actions_with_email_configuration(self, form_definition):
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
                        "email_cc_field": "manager_email",
                        "email_subject_template": "Submitted {form_name}",
                        "email_body_template": "Submission #{submission_id}",
                        "email_template_name": "emails/submission.html",
                    },
                },
                {"type": "end", "data": {}},
            ],
            "connections": [],
        }

        convert_visual_to_workflow(visual, form_definition)

        action = PostSubmissionAction.objects.get(name="Notify Submitter")
        assert action.action_type == "email"
        assert action.email_to == "ops@example.com"
        assert action.email_to_field == "email"
        assert action.email_cc == "manager@example.com"
        assert action.email_cc_field == "manager_email"
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

    def test_load_returns_json(self, client, superuser, staged_workflow):
        client.login(username="admin", password="testpass123")
        fid = staged_workflow.form_definition.id
        url = _wf_url(f"workflow/api/load/{fid}/")
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow" in data
        assert "nodes" in data["workflow"]

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
